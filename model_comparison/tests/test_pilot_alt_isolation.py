"""This batch's native filesystem boundary and isolated MCP wiring only."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import shlex
import uuid

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from pilot_alt_access import permission_args, RECORD, write


class AlternateIsolation(unittest.TestCase):
    def test_windows_failure_evidence_preserved(self):
        # Historical failure is checked for integrity, never reclassified PASS.
        state = json.loads((RECORD / "continuation_20260923_0332/windows_startup_1.json").read_text(encoding="utf-8"))
        self.assertFalse(state["passed"])
        self.assertEqual(state["subprocess_cwd"], state["codex_C"])
        self.assertFalse(state["legacy_sandbox_mode"])
        self.assertIn("requires the elevated Windows sandbox backend", state["stderr"])

    def test_guard_denies_native_and_allows_only_cad(self):
        for name, expected in (("Bash", "deny"), ("apply_patch", "deny"), ("read_file", "deny"),
                               ("mcp__other__read", "deny"), ("mcp__cad__execute", "allow"), ("mcp__cad__submit", "allow")):
            child = subprocess.run([sys.executable, "-I", "-B", str(TOOLS / "pilot_alt_guard.py"), "--cad"],
                                   input=json.dumps({"tool_name": name}), capture_output=True, text=True)
            self.assertEqual(child.returncode, 0)
            self.assertEqual(json.loads(child.stdout)["hookSpecificOutput"]["permissionDecision"], expected)

    def test_native_linux_boundary_and_cad_mcp(self):
        source = (TOOLS / "pilot_alt_linux_check.py").read_bytes()
        argv = ["wsl", "-d", "Ubuntu-24.04", "--", "/usr/bin/python3", "-B", "-"]
        child = subprocess.run(argv, input=source, capture_output=True, timeout=170)
        state = json.loads(child.stdout)
        state.update(outer_argv=argv, outer_exit_code=child.returncode)
        write(RECORD / "continuation_20260923_0332" / ("linux_test_" + state["run_id"] + ".json"), state)
        self.assertEqual(child.returncode, 0)
        self.assertTrue(state["filesystem_passed"])
        self.assertTrue(state["mcp"]["passed"])
        self.assertEqual(state["mcp"]["state"]["tool_calls"], 1)

    def test_generation_configuration_selects_cad_hook(self):
        from pilot_alt_access import config_args
        args = config_args(cad=True, python_executable="/usr/bin/python3",
                           guard_path="/operator/pilot_alt_guard.py", native_linux=True)
        hook = next(x for x in args if x.startswith("hooks.PreToolUse="))
        self.assertIn("--cad", hook)
        self.assertIn("features.shell_tool=false", args)
        self.assertIn("features.multi_agent=false", args)


if __name__ == "__main__":
    unittest.main()
