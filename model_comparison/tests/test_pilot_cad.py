"""New CAD environment test piece only; never a robot/model result."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pilot_snapshot
from pilot_snapshot import safe_snapshot, SnapshotRejected
from pilot_cad import source_rebuild, RebuildContractError
from pilot_evaluate import _structure_metrics
from pilot_run import KIT, ROOT, RESULTS, finalize_snapshot, write_json
from pilot_sandbox import execute_command, child_environment


BUILD = '''import cadquery as cq
shape=cq.Workplane('XY').box(10,10,10)
cq.exporters.export(shape,'assembly.step')
cq.exporters.export(shape,'cube.stl')
'''


class PilotCadAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run_id = "cad_source_acceptance_" + uuid.uuid4().hex[:12]
        cls.root = ROOT / "outputs/pilot_20260923" / cls.run_id
        cls.root.mkdir()
        cls.evidence = {"run_id":cls.run_id, "mode":"CAD_ENVIRONMENT_TEST_NOT_ROBOT", "real_model_calls":0,
                        "rule_version":"pilot-cad-20260923.2", "cases":{}}

    @classmethod
    def tearDownClass(cls):
        path = RESULTS / cls.run_id / "acceptance.json"
        write_json(path, cls.evidence)
        print("CAD_ACCEPTANCE_EVIDENCE=" + str(path), flush=True)

    def build_case(self, name, code=BUILD, missing_part=False, stale_outputs=False):
        case = self.root / name
        case.mkdir()
        source = case / "source"
        source.mkdir()
        (source / "build.py").write_text(code, encoding="utf-8")
        manifest = {"files":{"cad_source":"build.py","assembly_step":"assembly.step"},
                    "parts":[{"id":"cube","step":"assembly.step","stl":"cube.stl"}],
                    "rebuild_command":["python3","build.py"],"rebuild_inputs":["build.py"],
                    "rebuild_outputs":["assembly.step","cube.stl"]}
        if missing_part:
            manifest["parts"].append({"id":"missing","step":"assembly.step","stl":"missing.stl"})
            manifest["rebuild_outputs"].append("missing.stl")
        (source / "design_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        if stale_outputs:
            (source / "assembly.step").write_text("SYNTHETIC_OLD_STEP", encoding="utf-8")
            (source / "cube.stl").write_text("SYNTHETIC_OLD_STL", encoding="utf-8")
        received = case / "received"
        accepted = safe_snapshot(source, received)
        expected = {"build.py","design_manifest.json"} | ({"assembly.step","cube.stl"} if stale_outputs else set())
        self.assertEqual({r["path"] for r in accepted["files"]}, expected)
        rebuilt, evidence = source_rebuild(received, case, kit=KIT)
        rows = {r[0]:{"raw_value":r[1],"status":r[3],"failure_type":r[4]} for r in _structure_metrics(rebuilt)}
        self.evidence["cases"][name] = {"source_snapshot":accepted,"rebuild":evidence,"measurements":rows}
        self.assertEqual(safe_snapshot(source), accepted)  # Original stays unchanged.
        return rebuilt, evidence, rows

    def test_source_only_cube_real_cad(self):
        _, rebuild, rows = self.build_case("cube")
        self.assertEqual(rebuild["os_exit_code"], 0)
        self.assertTrue(rebuild["outputs_created"])
        self.assertEqual(rows["step_kernel_readback"]["status"], "PASS")
        step = rows["step_kernel_readback"]["raw_value"]["parts"][0]
        self.assertEqual(step["solid_count"], 1)
        self.assertTrue(step["valid"])
        self.assertAlmostEqual(step["volume_mm3"], 1000, places=5)
        for size in step["bbox_mm"]:
            self.assertAlmostEqual(size, 10, places=5)
        self.assertEqual(rows["all_printed_parts_envelope"]["status"], "PASS")
        part = rows["stl_triangle_proxy"]["raw_value"]["parts"][0]["measurement"]
        self.assertEqual(part["bbox_mm"]["size"], [10,10,10])
        self.assertEqual(part["triangle_count"], 12)
        self.assertFalse(part["solid_validity_checked"])
        self.assertEqual(rows["joint_tree_actuator_contract"]["status"], "NA")

    def test_exit_zero_without_outputs_rejected(self):
        _, rebuild, rows = self.build_case("exit_zero_no_output", "pass\n", stale_outputs=True)
        self.assertEqual(rebuild["os_exit_code"], 0)
        self.assertFalse(rebuild["outputs_created"])
        self.assertEqual(rebuild["missing_outputs"], ["assembly.step","cube.stl"])
        self.assertEqual({r["path"] for r in rebuild["source_snapshot"]["files"]}, {"build.py","design_manifest.json"})
        self.assertEqual(rows["step_kernel_readback"]["status"], "FAIL")

    def test_bad_step_is_data_failure(self):
        code = BUILD + "from pathlib import Path\nPath('assembly.step').write_text('SYNTHETIC_BAD_STEP')\n"
        _, rebuild, rows = self.build_case("bad_step", code)
        self.assertEqual(rebuild["os_exit_code"], 0)
        self.assertEqual(rows["step_kernel_readback"]["status"], "FAIL")
        self.assertEqual(rows["step_kernel_readback"]["failure_type"], "STEP_READBACK_FAILED")

    def test_missing_part_cannot_pass_all_envelopes(self):
        _, rebuild, rows = self.build_case("missing_part", missing_part=True)
        self.assertFalse(rebuild["outputs_created"])
        self.assertEqual(rows["all_printed_parts_envelope"]["status"], "FAIL")
        self.assertEqual(rows["all_printed_parts_envelope"]["raw_value"]["sizes_mm"], [[10,10,10],None])

    def test_escape_junction_rejected_before_any_read(self):
        case = self.root / "escape"
        case.mkdir()
        outside, source = case / "synthetic_external", case / "source"
        outside.mkdir(); source.mkdir()
        (outside / "marker.txt").write_text("SYNTHETIC_EXTERNAL_MARKER_ONLY", encoding="utf-8")
        (source / "a.txt").write_text("ordinary", encoding="utf-8")
        if os.name == "nt":
            script = "New-Item -ItemType Junction -Path '" + str(source / "escape") + "' -Target '" + str(outside) + "' | Out-Null"
            child = subprocess.run(["powershell","-NoProfile","-Command",script], env=child_environment(), capture_output=True)
            self.assertEqual(child.returncode, 0)
        else:
            (source / "escape").symlink_to(outside, target_is_directory=True)
        reads = []
        pin = pilot_snapshot._pin
        @contextmanager
        def observed_pin(path, directory):
            with pin(path, directory) as stream:
                if stream is None:
                    yield stream
                else:
                    class Watch:
                        def fileno(self): return stream.fileno()
                        def read(self, *args):
                            reads.append(str(path)); return stream.read(*args)
                    yield Watch()
        with patch.object(pilot_snapshot, "_pin", observed_pin):
            with self.assertRaises(SnapshotRejected):
                safe_snapshot(source, case / "snapshot")
        self.assertEqual(reads, [])
        self.assertFalse((case / "snapshot").exists())
        self.assertEqual(list(case.glob(".pilot-incomplete-*")), [])
        # Remove ONLY the link, not the synthetic target or its contents.
        if os.name == "nt": os.rmdir(source / "escape")
        else: (source / "escape").unlink()
        # Also exercise an actual file symlink (WSL can create it on DrvFS
        # without enabling Windows developer mode). Target is synthetic only.
        child = execute_command("ln -s ../synthetic_external/marker.txt escape_file", kit=KIT, writable_output=source)
        self.assertEqual(child.returncode, 0)
        with patch.object(pilot_snapshot, "_pin", observed_pin):
            with self.assertRaises(SnapshotRejected): safe_snapshot(source, case / "snapshot")
        self.assertEqual(reads, [])
        (source / "escape_file").unlink()
        self.evidence["cases"]["escape"] = {"rejected_before_read":True,"file_reads":0,"complete_snapshot_exists":False,
                                            "junction_rejected":True,"file_symlink_rejected":True}

    def test_quotas_unclear_contract_and_unstopped_tool(self):
        case = self.root / "quotas"
        case.mkdir(); source = case / "source"; source.mkdir()
        (source / "a").write_bytes(b"1234")
        for kwargs in ({"max_bytes":3},{"max_files":0},{"tool_stopped":False}):
            with self.assertRaises(SnapshotRejected): safe_snapshot(source, case / "snapshot", **kwargs)
        with self.assertRaises(RebuildContractError):
            from pilot_cad import validate_rebuild_contract
            validate_rebuild_contract({}, safe_snapshot(source))
        self.assertFalse((case / "snapshot").exists())

    def test_success_exception_and_timeout_keep_partial_output(self):
        for name, suffix, expected in (("normal","",0),("exception","; raise RuntimeError('synthetic')",1),
                                       ("timeout","; import time; time.sleep(30)",124)):
            case = self.root / name
            case.mkdir(); work = case / "work"; work.mkdir()
            code = "from pathlib import Path; Path('partial.txt').write_text('SYNTHETIC_PARTIAL')" + suffix
            import shlex
            child = execute_command("python3 -c " + shlex.quote(code), kit=KIT, writable_output=work, seconds=1 if name=="timeout" else 10)
            self.assertEqual(child.returncode, expected)
            state = {"exit_code":expected}
            finalize_snapshot(state, case, tool_stopped=True)
            self.assertEqual(state["snapshot_status"], "COMPLETE")
            self.assertEqual([f["path"] for f in state["final_snapshot_digest"]["files"]], ["partial.txt"])
            self.evidence["cases"][name] = {"os_exit_code":child.returncode, "snapshot":state}


if __name__ == "__main__":
    unittest.main(verbosity=2)
