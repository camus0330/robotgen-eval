"""Operator-only synthetic checks, never counted as a model's robot design."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pilot_run import KIT, ROOT, checked_copy
from pilot_sandbox import child_environment, execute_python
from pilot_evaluate import intake


class PilotChecks(unittest.TestCase):
    def test_input_binding_exact_and_original_verifier(self):
        expected = json.loads((KIT / "records/input_manifest.json").read_text())["files"]
        for item in expected:
            self.assertEqual(hashlib.sha256((KIT / "inputs" / item["path"]).read_bytes()).hexdigest(), item["sha256"])
        child = execute_python("import sys; from pathlib import Path; sys.path.insert(0,'/kit/tools'); import experiment; experiment.verify_inputs(Path('/kit')); print('INPUTS_PASS')", kit=KIT)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertIn("INPUTS_PASS", child.stdout)

    def test_snapshot_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as name:
            target = Path(name) / "frozen"
            checked_copy(target, b"original")
            with self.assertRaises(ValueError):
                checked_copy(target, b"different")
            self.assertEqual(target.read_bytes(), b"original")

    def test_credentials_mounts_network_and_readonly(self):
        synthetic = "SYNTHETIC_PILOT_CREDENTIAL_NO_REAL_KEY"
        os.environ["PILOT_SYNTHETIC_SECRET"] = synthetic
        try:
            self.assertNotIn("PILOT_SYNTHETIC_SECRET", child_environment())
            self.assertNotIn("SMART_AGI_API_KEY", child_environment())
            source = """import os,socket
assert 'PILOT_SYNTHETIC_SECRET' not in os.environ
assert 'SMART_AGI_API_KEY' not in os.environ
assert not os.path.exists('/mnt') and not os.path.exists('/home')
try:
 open('/kit/inputs/PROMPT.md','a')
except OSError: pass
else: raise AssertionError('input writable')
try:
 socket.create_connection(('1.1.1.1',443),timeout=1)
except OSError: pass
else: raise AssertionError('external network available')
print('ISOLATION_PASS')
"""
            child = execute_python(source, kit=KIT)
            self.assertEqual(child.returncode, 0, child.stderr)
            self.assertIn("ISOLATION_PASS", child.stdout)
            self.assertNotIn(synthetic, child.stdout + child.stderr)
        finally:
            del os.environ["PILOT_SYNTHETIC_SECRET"]

    def test_timeout_and_actual_exit_code(self):
        child = execute_python("import time; time.sleep(30)", kit=KIT, seconds=1)
        self.assertEqual(child.returncode, 124)
        child = execute_python("raise SystemExit(7)", kit=KIT)
        self.assertEqual(child.returncode, 7)

    def test_missing_valid_contract_and_bad_sample(self):
        # Valid means file contract ONLY. These bytes are deliberately not CAD.
        fixtures = ROOT / "outputs/pilot_20260923/test_fixtures"
        fixtures.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=fixtures) as name:
            folder = Path(name)
            self.assertEqual(intake(folder)["intake_status"], "INVALID")
            meta = json.loads((KIT / "inputs/templates/submission.json").read_text())
            meta.update(submission_id="synthetic-contract", model_slot="model_A", phase="pilot", attempt=1,
                        status="COMPLETED", model_provider="fixture", model_exact_version="fixture", invocation_mode="fixture",
                        session_id="fixture", input_manifest_sha256=hashlib.sha256((KIT / "records/input_manifest.json").read_bytes()).hexdigest(),
                        prompt_sha256=hashlib.sha256((KIT / "inputs/PROMPT.md").read_bytes()).hexdigest(),
                        actual_elapsed_s=0, human_edit_minutes=0, feedback_rounds=0,
                        unknown_fields_reason="synthetic intake fixture, no API or real robot", logs=["fixture.log"])
            design = json.loads((KIT / "inputs/templates/design_manifest.json").read_text())
            for key in design["files"]:
                design["files"][key] = key + ".fixture"
            design["parts"] = [{"id": "synthetic", "quantity": 1, "step": "part.step", "stl": "part.stl"}]
            design["rebuild_command"] = ["false"]
            for joint in design["joints"]:
                joint["name"] = joint["role"]
                for kind in ("case_mount", "horn_mount"):
                    design["interfaces"].append({"id": joint["role"] + kind, "part_id": "synthetic", "joint_role": joint["role"],
                                                "kind": kind, "frame_in_part_mm": [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]})
            for contact in design["contacts"]:
                design["contacts"][contact] = contact
            for motion in design["motions"]:
                for key in design["motions"][motion]:
                    design["motions"][motion][key] = motion + key + ".fixture"
            files = list(design["files"].values()) + ["part.step", "part.stl", "fixture.log"]
            files += [value for motion in design["motions"].values() for value in motion.values()]
            for relative in files:
                (folder / relative).write_text("SYNTHETIC CONTRACT ONLY; NOT A ROBOT\n")
            (folder / "submission.json").write_text(json.dumps(meta))
            (folder / "design_manifest.json").write_text(json.dumps(design))
            result = intake(folder)
            self.assertEqual(result["intake_status"], "FILE_CONTRACT_ACCEPTED", result)
            self.assertEqual(result["engineering_evaluation"], "NOT_RUN")
            design["parts"][0]["step"] = "../escape.step"
            (folder / "design_manifest.json").write_text(json.dumps(design))
            self.assertEqual(intake(folder)["intake_status"], "INVALID")


if __name__ == "__main__":
    unittest.main(verbosity=2)
