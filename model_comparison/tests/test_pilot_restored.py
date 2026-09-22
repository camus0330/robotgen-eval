"""Directed tests for the restored batch wiring; no API/old CAD fixture calls."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import pilot_restored as p


class RestoredWiring(unittest.TestCase):
    def test_preferred_backup_binding_and_no_old_batch(self):
        plan={"batch_id":p.BATCH,"candidates":{k:list(v) for k,v in p.CANDIDATES.items()}}
        good={"request_model_id":"deepseek-v4-pro","classification":"ADMITTED","parser_pass":True,
              "nonempty_completion":True,"image_url_in_completion_messages":True,"child_os_exit_code":0}
        admission={"batch_id":p.BATCH,"cases":[good]}
        self.assertEqual(p.selected(plan,admission,"model_A"),"deepseek-v4-pro")
        admission["cases"].append(dict(good,request_model_id="deepseek-v4.1-flash"))
        self.assertEqual(p.selected(plan,admission,"model_A"),"deepseek-v4-pro")
        good["classification"]="ACCESS_OR_PROTOCOL_FAILED"
        self.assertEqual(p.selected(plan,admission,"model_A"),"deepseek-v4.1-flash")
        admission["cases"][1]["image_url_in_completion_messages"]=False
        self.assertIsNone(p.selected(plan,admission,"model_A"))
        admission["batch_id"]="old_404"
        with self.assertRaises(AssertionError): p.selected(plan,admission,"model_A")

    def test_exact_endpoint_and_model_before_key(self):
        config=p.new_config("kimi-k3")
        p.validate_config(config,"kimi-k3")
        for name,value in (("model","gpt-5.6-sol"),("base_url","https://unrelated.invalid"),
                           ("api_path","/v1/models"),("api_key","synthetic-inline"),("api_key_env","OTHER_KEY")):
            wrong=copy.deepcopy(config);wrong[name]=value
            with self.assertRaises(ValueError):p.validate_config(wrong,"kimi-k3")
        config["request"]["max_retries"]=1
        with self.assertRaises(ValueError):p.validate_config(config,"kimi-k3")

    def test_budget_and_shared_contract(self):
        budget={"max_queries":48}
        self.assertEqual(p.query_timeout(budget,0,3600),600)
        self.assertEqual(p.query_timeout(budget,47,20),17)
        with self.assertRaises(TimeoutError):p.query_timeout(budget,48,3600)
        with self.assertRaises(TimeoutError):p.query_timeout(budget,2,3)
        for token in ("rebuild_inputs","rebuild_outputs","rebuild_excluded","rebuild_command",
                      "/cad/bin/python","/kit/inputs/assets/xl330_m288_t.step","3600","48"):
            self.assertIn(token,p.ADDENDUM)

    def test_actual_pinned_message_binding_and_diagnostic_cleaning(self):
        # Isolated test process only; no real credential or completion call.
        os.environ["SMART_AGI_API_KEY"]="SYNTHETIC_RESTORED_TEST_CREDENTIAL"
        with tempfile.TemporaryDirectory() as directory:
            _,_,model,key,_=p.client_setup("glm-5.3",p.new_config("glm-5.3"),Path(directory))
            messages=[model.format_message(role="user",content=p.with_image("admission marker"))]
            prepared=model._prepare_messages_for_api(messages)
            self.assertTrue(p.has_image(prepared))
            self.assertTrue(prepared[0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))
            self.assertEqual(model.config.model_kwargs["num_retries"],0)
            error=RuntimeError("synthetic failure "+key)
            safe=p.error_fields(error,key)
            self.assertNotIn(key,json.dumps(safe))
            self.assertLessEqual(len(safe["error_message"]),1500)


if __name__=="__main__": unittest.main(verbosity=2)
