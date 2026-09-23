"""Ubuntu migration checks: no model requests, CAD fixture or package install."""
import contextlib
import importlib.metadata
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
import pilot_run
import pilot_sandbox
from pilot_snapshot import safe_snapshot, SnapshotRejected


@unittest.skipUnless(sys.platform == "linux", "native Ubuntu checks")
class UbuntuMigration(unittest.TestCase):
    def test_missing_client_cache_and_admission_are_recorded_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Real frozen Git blobs, temporary destinations, no historical files.
            repository = pilot_run.ROOT
            def real_git_blob(relative):
                return subprocess.run(
                    ["git", "show", f"{pilot_run.BASELINE}:{relative}"],
                    cwd=repository, check=True, capture_output=True).stdout
            with patch.object(pilot_run, "ROOT", root), \
                 patch.object(pilot_run, "RESULTS", root / "results"), \
                 patch.object(pilot_run, "KIT", root / "unused"), \
                 patch.object(pilot_run, "CACHE", root / "missing-cache"), \
                 patch.object(pilot_run, "git_blob", real_git_blob), \
                 patch.object(pilot_run.importlib.metadata, "version",
                              side_effect=importlib.metadata.PackageNotFoundError), \
                 contextlib.redirect_stdout(io.StringIO()):
                # Checkout-byte checks still read the actual public input tree.
                (root / "model_comparison").mkdir()
                (root / "model_comparison/inputs").symlink_to(
                    Path(__file__).resolve().parents[1] / "inputs")
                self.assertEqual(pilot_run.preflight("ubuntu-test"), 2)
                report = root / "results/ubuntu-test/preflight.json"
                before = report.read_bytes()
                data = json.loads(before)
                self.assertEqual(data["classification"], "ENVIRONMENT_BLOCKED")
                self.assertFalse(data["generation_ready"])
                self.assertFalse(data["admission_evidence_present"])
                self.assertEqual(data["input_baseline"], pilot_run.BASELINE)
                self.assertTrue(all(row["checkout_exact"] for row in data["input_binding"]))
                with self.assertRaises(ValueError):
                    pilot_run.preflight("ubuntu-test")
                self.assertEqual(report.read_bytes(), before)
                with self.assertRaises(ValueError):
                    pilot_run.preflight("../escape")

    def test_host_runtime_validation_and_native_launcher(self):
        inner = ["/usr/bin/timeout", "10", "/usr/bin/bwrap"]
        self.assertEqual(pilot_sandbox.host_command(inner), inner)
        with patch.object(pilot_sandbox, "CAD_VENV", "/cad"):
            with self.assertRaises(ValueError):
                pilot_sandbox.cad_mount()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(pilot_sandbox, "CAD_VENV", directory):
                with self.assertRaises(FileNotFoundError):
                    pilot_sandbox.cad_mount()
                runtime = Path(directory)
                (runtime / "pyvenv.cfg").write_text("home = /usr/bin\n")
                (runtime / "bin").mkdir()
                (runtime / "bin/python").symlink_to("/usr/bin/python3")
                mount = pilot_sandbox.cad_mount()
                self.assertEqual(mount[:3], ["--ro-bind", directory, "/cad"])

    def test_actual_namespace_hides_credentials_other_participant_and_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kit, first, other = (root / name for name in ("kit", "first", "other"))
            for folder in (kit, first, other):
                folder.mkdir()
            (kit / "public.txt").write_text("public")
            (other / "private.txt").write_text("SYNTHETIC_OTHER_PARTICIPANT")
            source = f"""import os, socket
from pathlib import Path
assert 'PILOT_SYNTHETIC_SECRET' not in os.environ
assert 'HTTPS_PROXY' not in os.environ
assert not Path('/home').exists()
assert not Path({str(other)!r}).exists()
assert not Path('/other').exists()
assert Path('/kit/public.txt').read_text() == 'public'
try:
 Path('/kit/public.txt').write_text('changed')
except OSError: pass
else: raise AssertionError('public input writable')
assert [name for _, name in socket.if_nameindex()] == ['lo']
try:
 socket.create_connection(('1.1.1.1', 443), timeout=1)
except OSError: pass
else: raise AssertionError('external network available')
Path('/work/own.txt').write_text('own')
"""
            with patch.dict(os.environ, {"PILOT_SYNTHETIC_SECRET": "SYNTHETIC_ONLY",
                                        "HTTPS_PROXY": "http://127.0.0.1:1"}):
                child = pilot_sandbox.execute_python(source, kit=kit, writable_output=first)
            self.assertEqual(child.returncode, 0, child.stderr)
            self.assertEqual((first / "own.txt").read_text(), "own")
            self.assertEqual((other / "private.txt").read_text(), "SYNTHETIC_OTHER_PARTICIPANT")

    def test_native_action_timeout_preserves_only_stopped_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kit, work = root / "kit", root / "work"
            kit.mkdir(); work.mkdir()
            command = "python3 -c 'from pathlib import Path; import time; Path(\"partial\").write_text(\"partial\"); time.sleep(10)'"
            child = pilot_sandbox.execute_command(command, kit=kit, writable_output=work, seconds=1)
            self.assertEqual(child.returncode, 124, child.stderr)
            with self.assertRaises(SnapshotRejected):
                safe_snapshot(work, root / "unsafe", tool_stopped=False)
            result = safe_snapshot(work, root / "final")
            self.assertEqual([row["path"] for row in result["files"]], ["partial"])
            (work / "escape").symlink_to(kit, target_is_directory=True)
            with self.assertRaises(SnapshotRejected):
                safe_snapshot(work, root / "linked")
            self.assertFalse((root / "linked").exists())


if __name__ == "__main__":
    unittest.main()
