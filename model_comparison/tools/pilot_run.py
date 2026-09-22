"""Deadline pilot preflight plus bounded real and offline integration paths.

Generation is fail-closed while candidates are blocked; an admitted slot with an
explicit reviewed config can reach the real pinned Agent path.
"""
import argparse
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import base64
import tempfile
from types import SimpleNamespace
from pilot_snapshot import safe_snapshot, SnapshotRejected

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "f1d77516e35d7191a942d842b83f7ae23bb0710b"
RECORDS = ROOT / "model_comparison/records/pilot_20260923"
RESULTS = ROOT / "results/pilot_20260923"
KIT = ROOT / "outputs/pilot_20260923/input_kit"
CACHE = Path(r"C:\Users\hp\AppData\Local\Temp\robotgen-tokenizer-cache-569bm_v2")
CACHE_NAME = "9b5ad71b2ce5302211f9c61530b329a4922fc6a4"
CACHE_SHA = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
SYSTEM_PROMPT = """Use one text action per response, with exactly this literal fence syntax:
```mswea_bash_command
<command>
```
Wait for the actual observation before the next action. Submit by a command whose
first output line is COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT. Read the frozen task,
submission specification and all public inputs. Do not access other designs.
"""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def snapshot_digest(path):
    return safe_snapshot(path) if path is not None else None


def finalize_snapshot(state, out_root, *, tool_stopped):
    """Same bounded copy on success, exceptions and timeouts, after tools stop."""
    work, final = out_root / "work", out_root / "final"
    state["final_snapshot"] = None
    if not work.exists():
        state["snapshot_status"] = "NO_WORK_DIRECTORY"
        return
    try:
        evidence = safe_snapshot(work, final, tool_stopped=tool_stopped)
        state.update(final_snapshot=str(final), final_snapshot_digest=evidence, snapshot_status="COMPLETE")
    except (SnapshotRejected, OSError) as error:
        state.update(snapshot_status="REJECTED", snapshot_exception_class=type(error).__name__)
        if state.get("exit_code") == 0:
            state.update(classification="SNAPSHOT_REJECTED", exit_code=2)


def git_blob(relative):
    return subprocess.run(["git", "show", f"{BASELINE}:{relative}"], cwd=ROOT,
                          check=True, capture_output=True).stdout


def checked_copy(path, content):
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError("Existing snapshot differs; refusing overwrite")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(content)


def bind_inputs():
    """Bind exact baseline Git bytes, never normalize or refresh frozen originals."""
    manifest_bytes = git_blob("model_comparison/records/input_manifest.json")
    expected = json.loads(manifest_bytes)["files"]
    observed = []
    for item in expected:
        relative = item["path"]
        content = git_blob("model_comparison/inputs/" + relative)
        if digest(content) != item["sha256"]:
            raise ValueError("Baseline input hash mismatch")
        checked_copy(KIT / "inputs" / relative, content)
        working = (ROOT / "model_comparison/inputs" / relative).read_bytes()
        observed.append({**item, "checkout_sha256": digest(working),
                         "checkout_exact": working == content,
                         "checkout_crlf_only": working.replace(b"\r\n", b"\n") == content})
    checked_copy(KIT / "records/input_manifest.json", manifest_bytes)
    checked_copy(KIT / "tools/experiment.py", git_blob("model_comparison/tools/experiment.py"))
    return observed


def preflight():
    inputs = bind_inputs()
    cache_ok = (CACHE / CACHE_NAME).is_file() and digest((CACHE / CACHE_NAME).read_bytes()) == CACHE_SHA
    versions = {name: importlib.metadata.version(name)
                for name in ("mini-swe-agent", "litellm", "tiktoken")}
    dist = importlib.metadata.distribution("mini-swe-agent")
    upstream = json.loads(dist.read_text("direct_url.json"))["vcs_info"]["commit_id"]
    client_ok = versions == {"mini-swe-agent": "2.4.6", "litellm": "1.102.0", "tiktoken": "0.14.0"} and upstream == "04d809ceab9df28f9adaed044884180159172930"
    admission = json.loads((RESULTS / "admission.json").read_text(encoding="utf-8"))
    admitted = [case for case in admission["cases"] if case.get("completion_succeeded") is True]
    generation_ready = bool(admitted and cache_ok and client_ok)
    result = {"time": stamp(), "classification": "READY" if generation_ready else "ACCESS_BLOCKED", "python": sys.executable,
              "python_version": sys.version.split()[0], "versions": versions, "upstream_sha": upstream,
              "client_provenance_pass": client_ok, "cache_path": str(CACHE),
              "cache_sha256": CACHE_SHA if cache_ok else None, "cache_pass": cache_ok,
              "input_binding": inputs, "canonical_kit": str(KIT),
              "selected_credential_present": bool(os.environ.get("SMART_AGI_API_KEY", "").strip()),
              "admission": admission["cases"], "admitted_candidates": len(admitted), "generation_ready": generation_ready,
              "image_binding": "PLANNED: identical original PNG bytes as image_url data URI, once per instance; NOT_SENT",
              "uncompleted_gates": ["candidate completion + native protocol admission", "generation environment and hard lifecycle validation", "frozen executable runner and image transport validation"],
              "exit_code": 2}
    if not cache_ok or not client_ok:
        result["classification"] = "ENVIRONMENT_BLOCKED"
    write_json(RESULTS / "preflight.json", result)
    print(json.dumps({k: result[k] for k in ("classification", "client_provenance_pass", "cache_pass", "generation_ready", "exit_code")}))
    return 2


def run(slot, config_path=None):
    plan = json.loads((RECORDS / "plan.json").read_text(encoding="utf-8"))
    selected = next(m for m in plan["models"] if m["slot"] == slot)
    if config_path is not None and selected.get("admission_status") == "ADMITTED":
        return run_real_integration(config_path, run_id="pilot_" + slot + "_20260922_v1")
    target = RESULTS / slot / "run_gate.json"
    if target.exists():
        raise ValueError("Run-gate evidence already exists; refusing overwrite")
    # No generation implementation is advertised as ready on blocked evidence.
    result = {"slot": slot, "time": stamp(), "status": "NOT_STARTED",
              "failure_type": selected["admission_status"] if selected["admission_status"] != "ADMITTED" else "ENVIRONMENT_BLOCKED",
              "stage": "pre_generation_gate", "generation_attempt_started": False,
              "model_query_calls": 0, "real_shell_launches": 0,
              "first_snapshot": None, "final_snapshot": None,
              "reason": "No admitted candidate; full generation runner/environment not validated",
              "exit_code": 2}
    write_json(target, result)
    print(json.dumps(result))
    return 2


def run_real_integration(config_path: Path, run_id="integration_only_20260922_v1") -> int:
    """Parent lifecycle: one bounded worker, with a durable pre-request placeholder."""
    evidence_path = RESULTS / run_id / "run.json"
    if evidence_path.exists():
        raise ValueError("INTEGRATION_ONLY attempt already recorded; refusing repeat")
    write_json(evidence_path, {"run_id":run_id,"mode":"INTEGRATION_ONLY","classification":"RUNNING","stage":"startup","generation_attempt_started":False,"model_query_calls":0,"real_shell_launches":0,"started_at":stamp(),"provider_retries":0})
    import multiprocessing
    worker = multiprocessing.get_context("spawn").Process(target=_safe_real_attempt, args=(str(config_path), run_id))
    worker.start()
    worker.join(1200)
    if worker.is_alive():
        worker.terminate(); worker.join(30)
        result = json.loads(evidence_path.read_text(encoding="utf-8"))
        result.update({"classification":"TIMEOUT","exit_code":124,"stage":"host_attempt_timeout","ended_at":stamp(),"worker_exit_code":worker.exitcode})
        finalize_snapshot(result, ROOT / "outputs/pilot_20260923" / run_id, tool_stopped=not worker.is_alive() and result.get("tool_stopped") is True)
        write_json(evidence_path, result); print(json.dumps({k:result.get(k) for k in ("run_id","classification","exit_code","model_query_calls","real_shell_launches")})); return 124
    result = json.loads(evidence_path.read_text(encoding="utf-8"))
    if result.get("classification") == "RUNNING":
        result.update({"classification":"INFRASTRUCTURE_FAILED","exit_code":worker.exitcode or 1,"stage":"worker_exit","ended_at":stamp()})
        write_json(evidence_path, result)
    finalize_snapshot(result, ROOT / "outputs/pilot_20260923" / run_id, tool_stopped=result.get("tool_stopped") is True)
    write_json(evidence_path, result)
    print(json.dumps({k:result.get(k) for k in ("run_id","classification","exit_code","model_query_calls","real_shell_launches","exit_status")}))
    return int(result.get("exit_code", worker.exitcode or 1))


def _safe_real_attempt(config_path: str, run_id: str) -> None:
    try:
        _run_real_attempt(config_path, run_id)
    except BaseException as error:
        evidence_path = RESULTS / run_id / "run.json"
        result = json.loads(evidence_path.read_text(encoding="utf-8")) if evidence_path.exists() else {"run_id":run_id}
        result.update({"classification":"INFRASTRUCTURE_FAILED","exit_code":1,"stage":"worker_exception","safe_exception_class":type(error).__name__,"ended_at":stamp()})
        write_json(evidence_path, result)


def _run_real_attempt(config_path: str, run_id: str) -> None:
    """Run one explicitly requested integration attempt through the real Agent.

    This path is reachable only with a caller-supplied, validated temporary config;
    it never maps the route to a three-model slot and never enters the model table.
    """
    evidence_path = RESULTS / run_id / "run.json"
    raw = json.loads(Path(config_path).read_text(encoding="utf-8-sig"))
    if raw.get("provider") != "smart_agi_gateway" or not raw.get("base_url", "").startswith("https://"):
        raise ValueError("config is not the reviewed HTTPS gateway shape")
    request = raw.get("request", {})
    if request.get("max_retries") != 0 or request.get("stream") is not False:
        raise ValueError("provider retry/stream policy mismatch")
    key = os.environ.get(raw.get("api_key_env", ""), "")
    if not key.strip():
        result = {"run_id": run_id, "mode": "INTEGRATION_ONLY", "classification": "CONFIG_BLOCKED", "exit_code": 3, "stage": "credential_precheck", "model_query_calls": 0, "real_shell_launches": 0}
        write_json(evidence_path, result); print(json.dumps(result)); return 3
    sys.path.insert(0, str(ROOT / "model_comparison" / "spikes"))
    from mini_swe_gateway_agent_e2e import check_cache, import_upstream, scrub_environment, sanitize
    from pilot_sandbox import execute_command
    scrub_environment(); check_cache(CACHE)
    DefaultAgent, _, LitellmTextbasedModel = import_upstream(CACHE)
    import litellm
    from minisweagent.exceptions import Submitted
    out_root = ROOT / "outputs" / "pilot_20260923" / run_id
    out_root.mkdir(parents=True, exist_ok=True)
    first = out_root / "first"
    final = out_root / "final"
    work = out_root / "work"
    work.mkdir(exist_ok=False)
    image = KIT / "inputs" / "assets" / "reference.png"
    image_uri = "data:image/png;base64," + base64.b64encode(image.read_bytes()).decode("ascii")
    task_text = ((KIT / "inputs" / "PROMPT.md").read_text(encoding="utf-8") + "\n\n" +
                 (KIT / "inputs" / "TASK_SPEC.md").read_text(encoding="utf-8") + "\n\n" +
                 (KIT / "inputs" / "SUBMISSION_SPEC.md").read_text(encoding="utf-8") +
                 "\n\nReference image:\n<MSWEA_MULTIMODAL_CONTENT><CONTENT_TYPE>image_url</CONTENT_TYPE>" + image_uri + "</MSWEA_MULTIMODAL_CONTENT>")
    model_kwargs = {"api_base": raw["base_url"].rstrip("/") + raw.get("api_path", "/v1/chat/completions").rsplit("/chat/completions", 1)[0], "api_key": key, "timeout": request.get("timeout_s", 600), "max_retries": 0, "num_retries": 0, "stream": False}
    model = LitellmTextbasedModel(model_name="openai/" + str(raw["model"]), multimodal_regex=r"(?s)<MSWEA_MULTIMODAL_CONTENT><CONTENT_TYPE>(.+?)</CONTENT_TYPE>(.+?)</MSWEA_MULTIMODAL_CONTENT>", cost_tracking="ignore_errors", model_kwargs=model_kwargs)
    profile_calls = {"n": 0}
    import sys as _sys
    previous_profile = _sys.getprofile()
    class IsolatedEnvironment:
        def __init__(self): self.launches = []
        def execute(self, action, cwd="", timeout=None):
            command = action.get("command", "")
            self.launches.append(command)
            state["tool_stopped"] = False
            state["real_shell_launches"] = len(self.launches)
            write_json(evidence_path, state)
            child = execute_command(command, kit=KIT, writable_output=work, seconds=min(timeout or 30, 30))
            state["tool_stopped"] = True
            write_json(evidence_path, state)
            output = {"output": child.stdout, "returncode": child.returncode, "exception_info": "" if child.returncode == 0 else "isolated command failed"}
            if not first.exists() and safe_snapshot(work)["files"]:
                state["first_snapshot_digest"] = safe_snapshot(work, first)
                state["first_snapshot"] = str(first)
                write_json(evidence_path, state)
            lines = output["output"].lstrip().splitlines(keepends=True)
            if output["returncode"] == 0 and lines and lines[0].strip() == "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT":
                raise Submitted({"role":"exit","content":"".join(lines[1:]),"extra":{"exit_status":"Submitted","submission":"".join(lines[1:])}})
            return output
        def get_template_vars(self, **kwargs): return kwargs
        def serialize(self): return {"info":{"config":{"environment_type":"isolated_pilot_environment","credential_mount":False}}}
    env = IsolatedEnvironment()
    agent = DefaultAgent(model=model, env=env, system_template="RobotGen integration-only. " + SYSTEM_PROMPT, instance_template="{{task}}", step_limit=20, max_consecutive_format_errors=2, cost_limit=1.0, output_path=None)
    def observe(frame, event, arg):
        if event == "call" and frame.f_code is LitellmTextbasedModel._query.__code__: profile_calls["n"] += 1
    state = {"run_id":run_id,"mode":"INTEGRATION_ONLY","route_model":raw["model"],"backend_identity":"not_confirmed","started_at":stamp(),"classification":"RUNNING","stage":"agent_run","generation_attempt_started":True,"model_query_calls":0,"real_shell_launches":0,"fixture_calls":0,"real_llm_api_calls":None,"real_llm_api_calls_source":"not_observed","first_snapshot":None,"final_snapshot":str(final),"image_bound":True,"provider_retries":0}
    state["tool_stopped"] = True
    write_json(evidence_path, state)
    _sys.setprofile(observe)
    try:
        result = agent.run(task_text)
        first_snapshot = first if first.exists() else None
        state.update({"classification":"PASS" if result.get("exit_status") == "Submitted" else "FAILED","exit_code":0 if result.get("exit_status") == "Submitted" else 1,"stage":"complete","ended_at":stamp(),"model_query_calls":profile_calls["n"],"real_shell_launches":len(env.launches),"exit_status":result.get("exit_status"),"submission":result.get("submission"),"first_snapshot":str(first_snapshot) if first_snapshot else None,"first_snapshot_digest":snapshot_digest(first_snapshot) if first_snapshot else None,"assistant_action_observations":sanitize([{"role":m.get("role"),"content":m.get("content"),"actions":m.get("extra",{}).get("actions"),"returncode":m.get("extra",{}).get("returncode")} for m in agent.messages], [key])})
    except Exception as error:
        state.update({"classification":"TIMEOUT" if type(error).__name__ == "TimeoutExpired" else "FAILED","exit_code":124 if type(error).__name__ == "TimeoutExpired" else 1,"stage":"agent_run","ended_at":stamp(),"safe_exception_class":type(error).__name__,"model_query_calls":profile_calls["n"],"real_shell_launches":len(env.launches),"first_snapshot":str(first) if first.exists() else None,"first_snapshot_digest":snapshot_digest(first) if first.exists() else None})
    finally:
        _sys.setprofile(previous_profile)
    write_json(evidence_path, state)
    print(json.dumps({k:state.get(k) for k in ("run_id","classification","exit_code","model_query_calls","real_shell_launches","exit_status")}))
    return state["exit_code"]


def _fixture_files(work):
    """Return a tiny synthetic, explicitly non-robot fixture for offline integration."""
    files = {
        "cad_source.py": "# synthetic fixture CAD source; not a robot design\n",
        "assembly.step": "ISO-10303-21; HEADER; FILE_DESCRIPTION(('synthetic fixture'),'1'); ENDSEC; DATA; ENDSEC; END-ISO-10303-21;\n",
        "bom.csv": "part,quantity\nfixture_cube,1\n",
        "robot.mjcf": "<mujoco model='fixture'><worldbody><body name='base'><joint name='fixture_joint' type='hinge'/></body></worldbody></mujoco>\n",
        "robot.urdf": "<robot name='fixture'><link name='base'/><joint name='fixture_joint' type='fixed'><parent link='base'/><child link='tip'/></joint><link name='tip'/></robot>\n",
        "controller.py": "# fixture controller\n",
        "readme.md": "Synthetic offline integration fixture; not a RobotGen result.\n",
        "limitations.md": "No dynamics or CAD-kernel claim.\n",
        "dependencies.txt": "python>=3.13\n",
        "part.step": "ISO-10303-21; HEADER; FILE_DESCRIPTION(('synthetic cube'),'1'); ENDSEC; DATA; ENDSEC; END-ISO-10303-21;\n",
        "part.stl": """solid fixture
facet normal 0 0 -1
 outer loop
  vertex 0 0 0
  vertex 10 10 0
  vertex 10 0 0
 endloop
endfacet
facet normal 0 0 -1
 outer loop
  vertex 0 0 0
  vertex 0 10 0
  vertex 10 10 0
 endloop
endfacet
facet normal 0 0 1
 outer loop
  vertex 0 0 10
  vertex 10 0 10
  vertex 10 10 10
 endloop
endfacet
facet normal 0 0 1
 outer loop
  vertex 0 0 10
  vertex 10 10 10
  vertex 0 10 10
 endloop
endfacet
endsolid fixture
""",
        "swing.reference": "synthetic\n", "swing.config": "duration_s: 1\n",
        "wave.reference": "synthetic\n", "wave.config": "duration_s: 1\n",
        "run.log": "OFFLINE_INTEGRATION fixture\n",
        "rebuild.py": """from pathlib import Path
required = ['submission.json', 'design_manifest.json', 'part.step', 'part.stl', 'robot.urdf', 'robot.mjcf']
missing = [p for p in required if not (Path('/work') / p).is_file()]
if missing: raise SystemExit('missing fixture files')
(Path('/work') / 'rebuild.marker').write_text('rebuild-ok\\n')
print('COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT')
print('offline_fixture_submission')
""",
    }
    roles = ["left_shoulder_pitch", "left_elbow_pitch", "right_shoulder_pitch", "right_elbow_pitch",
             "left_hip_pitch", "left_knee_pitch", "right_hip_pitch", "right_knee_pitch"]
    design = {"units":{"cad":"mm","simulation":"m/kg/s/rad"},
              "files":{"cad_source":"cad_source.py","assembly_step":"assembly.step","bom":"bom.csv","mjcf":"robot.mjcf","urdf":"robot.urdf","controller":"controller.py","readme":"readme.md","limitations":"limitations.md","dependencies":"dependencies.txt"},
              "rebuild_command":["pilot_rebuild"],"parts":[{"id":"fixture_cube","quantity":1,"step":"part.step","stl":"part.stl"}],
              "joints":[{"role":r,"name":r} for r in roles],
              "contacts":{"left_hand":"left_hand_geom","right_hand":"right_hand_geom","left_foot":"left_foot_geom","right_foot":"right_foot_geom"},
              "motions":{"swing":{"reference":"swing.reference","config":"swing.config"},"wave":{"reference":"wave.reference","config":"wave.config"}},"interfaces":[]}
    for role in roles:
        for kind in ("case_mount","horn_mount"):
            design["interfaces"].append({"id":role+"_"+kind,"part_id":"fixture_cube","joint_role":role,"kind":kind,"frame_in_part_mm":[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]})
    return files, design


def run_offline_integration(cache: Path) -> int:
    """Reach the real upstream Agent loop with a fixture at the completion boundary."""
    run_id = "offline_integration_20260922_v4"
    output = ROOT / "outputs" / "pilot_20260923" / run_id
    evidence_path = RESULTS / run_id / "run.json"
    if evidence_path.exists():
        raise ValueError("Offline integration run already exists; refusing overwrite")
    from pilot_sandbox import execute_python
    sys.path.insert(0, str(ROOT / "model_comparison" / "spikes"))
    from mini_swe_gateway_agent_e2e import check_cache, import_upstream, scrub_environment, fixture_response
    scrub_environment(); check_cache(cache)
    DefaultAgent, _LocalEnvironment, LitellmTextbasedModel = import_upstream(cache)
    import litellm
    from minisweagent.exceptions import Submitted
    from unittest.mock import patch
    import re
    output.mkdir(parents=True, exist_ok=True)
    work = output / "work"
    work.mkdir(exist_ok=False)
    (work / "submission.json").write_text("{}", encoding="utf-8")
    files, design = _fixture_files(work)
    import hashlib as _hashlib
    manifest_hash = _hashlib.sha256((KIT / "records/input_manifest.json").read_bytes()).hexdigest()
    prompt_hash = _hashlib.sha256((KIT / "inputs/PROMPT.md").read_bytes()).hexdigest()
    meta = {"submission_id":"offline-integration-fixture","model_slot":"model_A","phase":"pilot","attempt":1,"status":"COMPLETED","model_provider":"OFFLINE_INTEGRATION","model_exact_version":"fixture","invocation_mode":"DefaultAgent text action","session_id":run_id,"generation_seed":None,"input_manifest_sha256":manifest_hash,"prompt_sha256":prompt_hash,"actual_elapsed_s":0,"feedback_rounds":0,"human_edit_minutes":0,"human_edits":[],"actual_cost":None,"usage_tokens":None,"unknown_fields_reason":"offline fixture has no provider usage or billing","logs":["run.log"]}
    files["submission.json"] = json.dumps(meta, indent=2) + "\n"
    files["design_manifest.json"] = json.dumps(design, indent=2) + "\n"
    payload = {name: content for name, content in files.items()}
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    write_action = "pilot_write " + encoded
    responses = [fixture_response("Write the fixture.\n\n```mswea_bash_command\n" + write_action + "\n```") ,
                 fixture_response("Rebuild and submit.\n\n```mswea_bash_command\npilot_rebuild\n```")]

    class IsolatedPilotEnvironment:
        def __init__(self): self.launches = []
        def execute(self, action, cwd="", timeout=None):
            command = action.get("command", "")
            self.launches.append(command)
            if command.startswith("pilot_write "):
                blob = command.split(" ", 1)[1]
                source = "import base64,json; from pathlib import Path; d=json.loads(base64.b64decode(" + repr(blob) + ")); [((Path('/work')/n).parent.mkdir(parents=True,exist_ok=True),(Path('/work')/n).write_text(v,encoding='utf-8')) for n,v in d.items()]"
                state["tool_stopped"] = False
                child = execute_python(source, kit=KIT, writable_output=work, seconds=30)
                state["tool_stopped"] = True
                out = {"output": child.stdout, "returncode": child.returncode, "exception_info": ""}
                if child.returncode != 0: out["exception_info"] = "isolated fixture write failed"
                safe_snapshot(work, output / "first")
                return out
            if command == "pilot_rebuild":
                state["tool_stopped"] = False
                child = execute_python("import runpy; runpy.run_path('/work/rebuild.py')", kit=KIT, writable_output=work, seconds=30)
                state["tool_stopped"] = True
                if child.returncode == 0 and child.stdout.startswith("COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"):
                    raise Submitted({"role":"exit","content":"offline_fixture_submission\n","extra":{"exit_status":"Submitted","submission":"offline_fixture_submission\n"}})
                return {"output":child.stdout,"returncode":child.returncode,"exception_info":"isolated rebuild failed"}
            return {"output":"unsupported fixture command\n","returncode":2,"exception_info":"unsupported fixture command"}
        def get_template_vars(self, **kwargs): return kwargs
        def serialize(self):
            return {"info":{"config":{"environment_type":"isolated_pilot_fixture","credential_mount":False}}}

    model = LitellmTextbasedModel(model_name="offline/pilot-fixture", cost_tracking="ignore_errors", model_kwargs={"api_key":"synthetic-offline-key","api_base":"https://gateway.invalid/v1","timeout":30,"max_retries":0,"num_retries":0,"stream":False})
    env = IsolatedPilotEnvironment()
    agent = DefaultAgent(model=model, env=env, system_template="RobotGen offline integration. " + SYSTEM_PROMPT, instance_template="{{task}}", step_limit=2, max_consecutive_format_errors=1, cost_limit=1.0, output_path=None)
    calls=[]
    def completion_fixture(**kwargs):
        calls.append(True)
        return responses[len(calls)-1]
    state={"run_id":run_id,"started_at":stamp(),"mode":"OFFLINE_INTEGRATION","classification":"RUNNING","tool_stopped":True,"work_directory":str(work),"first_snapshot":str(output/'first'),"final_snapshot":None}
    try:
        with patch("litellm.completion", side_effect=completion_fixture), patch("litellm.cost_calculator.completion_cost", return_value=0.0):
            result = agent.run("Use the provided task inputs and create the synthetic fixture submission.")
        state.update({"classification":"PASS","exit_code":0,"stage":"complete","agent_calls":agent.n_calls,"model_query_calls":len(calls),"real_shell_launches":len(env.launches),"exit_status":result.get("exit_status"),"submission":result.get("submission"),"final_snapshot":str(output/'final'),"fixture_calls":len(calls),"cost_fixture_calls":2,"real_llm_api_calls":0,"real_llm_api_calls_source":"offline_fixture","first_snapshot_sha256":_hashlib.sha256(json.dumps(sorted(p.name for p in (output/'first').iterdir())).encode()).hexdigest()})
    except Exception as error:
        state.update({"classification":"FAILED","exit_code":1,"stage":"agent_run","safe_exception_class":type(error).__name__,"agent_calls":agent.n_calls,"model_query_calls":len(calls),"real_shell_launches":len(env.launches),"fixture_calls":len(calls),"cost_fixture_calls":2,"real_llm_api_calls":0,"real_llm_api_calls_source":"offline_fixture"})
    finalize_snapshot(state, output, tool_stopped=state["tool_stopped"])
    write_json(evidence_path, state)
    print(json.dumps({k:state.get(k) for k in ("run_id","classification","exit_code","agent_calls","model_query_calls","real_shell_launches","exit_status")}))
    return state["exit_code"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--slot", choices=("model_A", "model_B", "model_C"))
    run_parser.add_argument("--config", type=Path)
    run_parser.add_argument("--offline-integration", action="store_true")
    run_parser.add_argument("--integration-only-config", type=Path)
    args = parser.parse_args()
    if args.command == "preflight": return preflight()
    if args.offline_integration: return run_offline_integration(CACHE)
    if args.integration_only_config: return run_real_integration(args.integration_only_config)
    if not args.slot: parser.error("run requires --slot or --offline-integration")
    return run(args.slot, args.config)


if __name__ == "__main__":
    raise SystemExit(main())
