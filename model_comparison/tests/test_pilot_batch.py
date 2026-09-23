"""Batch plumbing only: no model/network, CAD build or runtime acceptance rerun."""
import base64
import contextlib
import copy
import datetime as dt
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pilot_batch as b
import pilot_restored as p
import pilot_evaluate as evaluation
import pilot_run


class BatchPlumbing(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="batch_plumbing_", dir=b.ROOT / "results")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.batch = self.root.name
        rel = self.root.relative_to(b.ROOT).as_posix()
        self.spec_path = self.root / "spec.json"
        self.plan_path = self.root / "records/plan.json"
        self.admission = self.root / "records/admission.json"
        (self.root / "addendum.md").write_text("Synthetic public process addendum; no design.\n")
        config = {"provider":"smart_agi_gateway", "model":"deepseek-v4-pro",
                  "base_url":"https://big-model.smart-agi.com/v1", "api_path":"/chat/completions",
                  "api_key_env":"PILOT_BATCH_TEST_KEY", "request":{"timeout_s":120,
                  "max_retries":0,"stream":False,"temperature":0,"max_tokens":1024}}
        self.spec = {"schema_version":b.SCHEMA,"batch_id":self.batch,"mode":"OFFLINE_PLUMBING_TEST",
            "paths":{"kit":rel+"/kit","output_root":rel+"/outputs","results_root":rel+"/runtime",
                     "record_root":rel+"/records","addendum":rel+"/records/PROMPT_ADDENDUM.md"},
            "addendum_source":rel+"/addendum.md","models":{"model_A":config},
            "run_names":{"model_A":"different_run_name"},"serial_order":["model_A"],
            "runtime":{"client_python":".tools/pilot-client/bin/python","cad_venv":".tools/cad-runtime",
                       "cache":".tools/tiktoken-cache","evidence":{"path":"model_comparison/records/runtime_restore_20260923_v1/restoration.json",
                       "sha256":b.sha(b.ROOT/"model_comparison/records/runtime_restore_20260923_v1/restoration.json")}},
            "deadline":(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=2)).isoformat(),
            "authorization":{"robot_generation":True,"source":"SYNTHETIC_OFFLINE_TEST_ONLY"},
            "budget":{"scope":"per_run","wall_time_s":60,"max_queries":2,"cost_limit":0.1,
                      "cost_limit_semantics":"library_estimate_usd_not_billing_cap",
                      "max_consecutive_format_errors":2,"provider_retries":0,"human_design_edits":0}}
        b.write_new(self.spec_path,self.spec)
        self.plan = b.prepare(self.spec_path,self.plan_path)
        self.bind_admission()
        self.env = patch.dict(os.environ,{"PILOT_BATCH_TEST_KEY":"SYNTHETIC_OFFLINE_ONLY"})
        self.env.start(); self.addCleanup(self.env.stop)
        runtime = patch.object(b,"runtime_gate",return_value=True)
        runtime.start(); self.addCleanup(runtime.stop)
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__(); self.addCleanup(quiet.__exit__,None,None,None)

    def bind_admission(self):
        case={"slot":"model_A","scope":"HARNESS_PROTOCOL_IMAGE_ADMISSION",
              "model_config_sha256":b.config_hash(self.plan["models"]["model_A"]),
              "request_model_id":"deepseek-v4-pro","image_sha256":b.sha(self.root/"kit/inputs/assets/reference.png"),
              "finish_reason":"stop","parser_pass":True,"nonempty_completion":True,
              "image_url_in_completion_messages":True,"image_content_review_pass":True}
        self.admission.write_text(json.dumps({"batch_id":self.batch,"plan_sha256":b.sha(self.plan_path),"cases":[case]}))

    def replace_plan(self):
        self.plan_path.write_text(json.dumps(self.plan))
        self.bind_admission()

    def test_positive_gate_and_existing_evidence_not_overwritten(self):
        target=self.root/"preflight.json"
        self.assertEqual(p.preflight_batch(self.plan_path,self.admission,target),0)
        before=target.read_bytes()
        result=json.loads(before)
        self.assertTrue(result["generation_ready"])
        self.assertTrue(result["runtime_available"])
        self.assertTrue(result["experiment_authorized"])
        with self.assertRaises(FileExistsError):
            p.preflight_batch(self.plan_path,self.admission,target)
        self.assertEqual(before,target.read_bytes())
        with self.assertRaises(ValueError):b.prepare(self.spec_path,self.plan_path)

    def test_switching_explicit_batches_does_not_reuse_old_paths(self):
        second=copy.deepcopy(self.spec)
        second['batch_id']=self.batch+'_next'
        old_prefix=self.root.relative_to(b.ROOT).as_posix()
        new_prefix=old_prefix+'/'+second['batch_id']
        second['paths']={k:v.replace(old_prefix,new_prefix,1) for k,v in second['paths'].items()}
        source=self.root/'second-spec.json';b.write_new(source,second)
        target=b.local(second['paths']['record_root'])/'plan.json'
        b.prepare(source,target)
        original=b.sha(self.plan_path)
        p.verify_plan(self.plan_path)
        self.assertEqual(p.KIT,self.root/'kit')
        p.verify_plan(target)
        self.assertEqual(p.KIT,b.local(second['paths']['kit']))
        self.assertEqual(p.RUNTIME,b.local(second['paths']['results_root']))
        self.assertEqual(p.OUTPUT,b.local(second['paths']['output_root']))
        p.verify_plan(self.plan_path)
        self.assertEqual(p.KIT,self.root/'kit')
        self.assertEqual(b.sha(self.plan_path),original)

    def test_legacy_runtime_preflight_cannot_authorize_generation(self):
        runtime=self.root/'legacy-check';runtime.mkdir()
        (runtime/'admission.json').write_text('{"cases":[{"completion_succeeded":true}]}')
        with patch.object(pilot_run,'RESULTS',runtime),patch.object(pilot_run,'bind_inputs',return_value=[]):
            self.assertEqual(pilot_run.preflight(),2)
        result=b.read(runtime/'preflight.json')
        self.assertFalse(result['generation_ready'])
        self.assertFalse(result['experiment_authorized'])
        self.assertNotEqual(result['classification'],'READY')

    def test_independent_negative_gates(self):
        self.plan["authorization"]["robot_generation"]=False
        self.replace_plan()
        gate=b.gates(self.plan,self.plan_path,self.admission)
        self.assertEqual(gate["classification"],"AUTHORIZATION_BLOCKED")
        self.assertTrue(gate["channel_admitted"]["model_A"])
        self.plan["authorization"]["robot_generation"]=True
        for value in (None,(dt.datetime.now(dt.timezone.utc)-dt.timedelta(seconds=1)).isoformat()):
            self.plan["deadline"]=value;self.replace_plan()
            self.assertFalse(b.gates(self.plan,self.plan_path,self.admission)["generation_ready"])
        self.plan["deadline"]=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=2)).isoformat()
        self.plan["budget"]["max_queries"]=None;self.replace_plan()
        self.assertFalse(b.gates(self.plan,self.plan_path,self.admission)["experiment_authorized"])
        with patch.object(b,"runtime_gate",return_value=False):
            self.assertEqual(b.gates(self.plan,self.plan_path,self.admission)["classification"],"ENVIRONMENT_BLOCKED")

    def test_old_sdk_or_other_config_admission_cannot_open_gate(self):
        valid=json.loads(self.admission.read_text())
        variants=[]
        for key,value in (("batch_id","old_batch"),("plan_sha256","old_plan")):
            bad=copy.deepcopy(valid);bad[key]=value;variants.append(bad)
        for key,value in (("scope","SDK_IMAGE_ONLY"),("model_config_sha256","wrong"),
                          ("image_content_review_pass",False),("image_url_in_completion_messages",False)):
            bad=copy.deepcopy(valid);bad["cases"][0][key]=value;variants.append(bad)
        for bad in variants:
            self.admission.write_text(json.dumps(bad))
            self.assertFalse(b.gates(self.plan,self.plan_path,self.admission)["generation_ready"])
        self.admission.write_text(json.dumps(valid))
        with patch.dict(os.environ,{"PILOT_BATCH_TEST_KEY":""}):
            self.assertEqual(b.gates(self.plan,self.plan_path,self.admission)["classification"],"CREDENTIAL_BLOCKED")

    def test_parent_and_direct_worker_block_before_client_or_output(self):
        self.plan["deadline"]=None;self.replace_plan()
        config=self.root/"records/model_A.config.json"
        with patch.object(p,"client_setup",side_effect=AssertionError("client must not start")):
            for entry in (p.run_pilot,p.pilot_worker):
                with self.assertRaisesRegex(ValueError,"generation blocked"):
                    entry(self.plan_path,self.admission,"model_A",config,self.batch+"/different_run_name")
        self.assertEqual(list((self.root/"outputs").iterdir()),[])
        self.assertEqual(list((self.root/"runtime").iterdir()),[])

    def test_standalone_worker_refuses_existing_journal_and_extra_kit_files(self):
        runtime=self.root/"runtime/different_run_name"
        runtime.mkdir()
        journal=runtime/"run.json";journal.write_text('{"classification":"OUTCOME_UNKNOWN"}')
        with patch.object(p,"client_setup",side_effect=AssertionError("no replay")):
            with self.assertRaisesRegex(ValueError,"journal already exists"):
                p.pilot_worker(self.plan_path,self.admission,"model_A",self.root/"records/model_A.config.json",self.batch+"/different_run_name")
        self.assertEqual(journal.read_text(),'{"classification":"OUTCOME_UNKNOWN"}')
        (self.root/"kit/unbound.txt").write_text('SYNTHETIC_OTHER_PARTICIPANT')
        with self.assertRaisesRegex(ValueError,"unbound files"):
            b.verify(self.plan)

    def test_accepted_intake_passes_explicit_kit_to_rebuild_and_measurement(self):
        # Empty synthetic input with mocked evaluator boundaries; no robot/CAD.
        source=self.root/"empty_synthetic_intake";source.mkdir()
        rows=[("step_kernel_readback",None,None,"PASS",None),
              ("stl_triangle_proxy",None,None,"PASS",None)]
        with patch.object(evaluation,"intake",return_value={"intake_status":"FILE_CONTRACT_ACCEPTED"}), \
             patch.object(evaluation,"source_rebuild",return_value=(source,{"os_exit_code":0,"outputs_created":True})) as rebuild, \
             patch.object(evaluation,"_structure_metrics",return_value=rows) as measure:
            self.assertEqual(evaluation.evaluate_integration(source,self.batch+'/name/evaluation','SYNTHETIC_PLUMBING',
                kit=self.root/'kit',results_root=self.root/'runtime',record_id='name/evaluation',batch_id=self.batch),0)
        self.assertEqual(rebuild.call_args.kwargs['kit'],self.root/'kit')
        self.assertEqual(measure.call_args.kwargs['kit'],self.root/'kit')
        result=b.read(self.root/'runtime/name/evaluation/evaluation.json')
        self.assertEqual(result['batch_id'],self.batch)
        self.assertEqual(result['run_id'],self.batch+'/name/evaluation')

    def test_real_worker_message_cad_flag_snapshots_and_evaluator_paths(self):
        # Real pinned Model message formatting; Agent/completion and OS actions
        # are the only replaced boundaries. No synthetic robot files are made.
        testcase=self
        prepared=[]
        class OfflineAgent:
            def __init__(self,model,env,**kwargs):
                self.model=model;self.env=env;self.messages=[];self.n_calls=0;self.cost=0
                testcase.assertEqual(kwargs["step_limit"],2)
                testcase.assertEqual(kwargs["wall_time_limit_seconds"],60)
            def run(self,task):
                messages=[self.model.format_message(role="user",content=task)]
                actual=self.model._prepare_messages_for_api(messages)
                prepared.extend(actual)
                self.messages=messages
                self.env.execute({"command":"SYNTHETIC_ACTION_NOT_EXECUTED"})
                return {"exit_status":"SYNTHETIC_STOP","submission":"no design"}
        setup=p.client_setup
        def offline_setup(*args):
            _,Model,model,key,verified=setup(*args)
            return OfflineAgent,Model,model,key,verified
        real_run=subprocess.run
        evaluated=[]
        def dispatch(argv,**kwargs):
            if str(b.ROOT/"model_comparison/tools/pilot_restored.py") in argv:
                def arg(name):return argv[argv.index(name)+1]
                with patch.dict(os.environ, dict(os.environ)):
                    rc=p.pilot_worker(Path(arg("--plan")),Path(arg("--admission")),arg("--slot"),Path(arg("--config")),arg("--run-id"))
                return subprocess.CompletedProcess(argv,rc,b"",b"")
            if str(b.ROOT/"model_comparison/tools/pilot_evaluate.py") in argv:
                evaluated.append(argv)
                def arg(name):return argv[argv.index(name)+1]
                _, context=evaluation.batch_evaluation_context(Path(arg('--execution-plan')),arg('--slot'))
                with patch.object(evaluation,"intake",return_value={"intake_status":"FAILED_ATTEMPT_RECORDED"}) as intake, \
                     patch.object(evaluation,"source_rebuild") as rebuild:
                    rc=evaluation.evaluate_integration(Path(arg("--submission")),arg("--run-id"),arg("--mode"),
                        kit=Path(arg("--kit")),results_root=Path(arg("--results-root")),
                        record_id=arg("--record-id"),batch_id=arg("--batch-id"),execution_context=context)
                    testcase.assertEqual(intake.call_args.kwargs["kit"],testcase.root/"kit")
                    rebuild.assert_not_called()
                return subprocess.CompletedProcess(argv,rc,b"",b"")
            return real_run(argv,**kwargs)
        with patch.object(p,"client_setup",side_effect=offline_setup), \
             patch.object(p,"execute_command",return_value=subprocess.CompletedProcess([],0,"","")) as execute, \
             patch.object(p.subprocess,"run",side_effect=dispatch):
            rc=p.run_pilot(self.plan_path,self.admission,"model_A",self.root/"records/model_A.config.json",self.batch+"/different_run_name")
            self.assertEqual(rc,2)  # Agent intentionally returned no real design.
            self.assertTrue(execute.call_args.kwargs["cad"])
            self.assertEqual(execute.call_args.kwargs["kit"],self.root/"kit")
            self.assertEqual(execute.call_args.kwargs["writable_output"],self.root/"outputs/different_run_name/work")
            self.assertEqual(p.evaluate_run(self.plan_path,"model_A"),2)
        uri=next(part["image_url"]["url"] for part in prepared[0]["content"] if part["type"]=="image_url")
        self.assertEqual(base64.b64decode(uri.split(',',1)[1]),(self.root/"kit/inputs/assets/reference.png").read_bytes())
        state=b.read(self.root/"runtime/different_run_name/run.json")
        self.assertEqual(state["run_id"],self.batch+"/different_run_name")
        self.assertEqual(state["snapshot_status"],"COMPLETE")
        self.assertTrue((self.root/"outputs/different_run_name/model_final").is_dir())
        self.assertTrue((self.root/"runtime/different_run_name/evaluation/metrics.json").is_file())
        evaluation_record=b.read(self.root/"runtime/different_run_name/evaluation/evaluation.json")
        self.assertEqual(evaluation_record['execution_context']['deadline'],self.plan['deadline'])
        self.assertEqual(evaluation_record['execution_context']['budget'],self.plan['budget'])
        self.assertEqual(len(evaluated),1)
        with self.assertRaises(FileExistsError):
            p.run_pilot(self.plan_path,self.admission,"model_A",self.root/"records/model_A.config.json",self.batch+"/different_run_name")


if __name__=="__main__":unittest.main()
