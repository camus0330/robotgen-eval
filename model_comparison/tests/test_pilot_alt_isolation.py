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
    def test_native_external_marker_denied(self):
        # Python's Windows mkdtemp uses owner-only ACLs; the sandbox logon account
        # cannot enter those directories. Inherit ACLs only for this new test root.
        base = Path(os.environ["SystemRoot"]) / "Temp" / ("robotgen-alt-boundary-" + uuid.uuid4().hex)
        base.mkdir()
        work = base
        outside = base.parent / (base.name + "-external-marker.txt")
        outside.write_text("SYNTHETIC_EXTERNAL_MARKER_ONLY", encoding="utf-8")
        (work / "allowed.txt").write_text("allowed", encoding="utf-8")
        shell = str(Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe")
        code = "try { $null=[IO.File]::ReadAllText('allowed.txt') } catch { exit 3 }; try { $null=[IO.File]::ReadAllText('" + str(outside) + "'); exit 2 } catch { Write-Output 'EXTERNAL_READ_DENIED'; exit 0 }"
        argv = [shutil.which("codex"), "sandbox", "-P", "robotgen-alt", "-C", str(work)] + permission_args() + [
            "-c", "permissions.robotgen-alt.workspace_roots={" + json.dumps(str(work)) + "=true}",
            shell, "-NoProfile", "-NonInteractive", "-Command", code]
        child = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        write(RECORD / "checks" / ("native_boundary_" + uuid.uuid4().hex + ".json"), {"argv": argv, "os_exit_code": child.returncode,
              "stdout": child.stdout, "stderr": child.stderr, "synthetic_only": True,
              "passed": child.returncode == 0 and "EXTERNAL_READ_DENIED" in child.stdout})
        self.assertEqual(child.returncode, 0, "Native sandbox cannot establish scoped reads; see safe record")
        self.assertIn("EXTERNAL_READ_DENIED", child.stdout)

    def test_guard_denies_native_and_allows_only_cad(self):
        for name, expected in (("Bash", "deny"), ("apply_patch", "deny"), ("read_file", "deny"),
                               ("mcp__other__read", "deny"), ("mcp__cad__execute", "allow"), ("mcp__cad__submit", "allow")):
            child = subprocess.run([sys.executable, "-I", "-B", str(TOOLS / "pilot_alt_guard.py"), "--cad"],
                                   input=json.dumps({"tool_name": name}), capture_output=True, text=True)
            self.assertEqual(child.returncode, 0)
            self.assertEqual(json.loads(child.stdout)["hookSpecificOutput"]["permissionDecision"], expected)

    def test_mcp_executes_only_inside_existing_namespace(self):
        output = Path(tempfile.mkdtemp(prefix="robotgen-alt-mcp-"))
        (output / "work").mkdir()
        source = "import os,pathlib,json; assert pathlib.Path('/kit/inputs/TASK_SPEC.md').is_file(); assert not pathlib.Path('/mnt').exists(); assert not pathlib.Path('/home/camus').exists(); assert 'ROBOTGEN_SYNTHETIC_CREDENTIAL' not in os.environ; print(json.dumps({'namespace_boundary':'PASS'}))"
        command = "/cad/bin/python -I -B -c " + shlex.quote(source)
        argv = [sys.executable, "-B", str(TOOLS / "pilot_alt_mcp.py"), "--kit", str(TOOLS.parents[1] / "outputs/pilot_20260923/input_kit"), "--output", str(output)]
        requests = [
            {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}},
            {"jsonrpc":"2.0","id":2,"method":"tools/list"},
            {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"execute","arguments":{"command":command}}}]
        env = dict(os.environ)
        env["ROBOTGEN_SYNTHETIC_CREDENTIAL"] = "SYNTHETIC_ONLY"
        child = subprocess.run(argv, input="".join(json.dumps(x)+"\n" for x in requests), capture_output=True,
                               text=True, encoding="utf-8", timeout=90, env=env)
        responses = [json.loads(x) for x in child.stdout.splitlines()]
        write(RECORD / "checks" / ("mcp_boundary_" + uuid.uuid4().hex + ".json"), {"argv":argv,"os_exit_code":child.returncode,"responses":responses,
              "tool_state":json.loads((output / "tool_state.json").read_text()),"stderr":child.stderr,"robot_result":False})
        self.assertEqual(child.returncode, 0)
        self.assertEqual([x["name"] for x in responses[1]["result"]["tools"]], ["execute","submit"])
        value = json.loads(responses[2]["result"]["content"][0]["text"])
        self.assertEqual(value["exit_code"], 0)
        self.assertIn('"namespace_boundary": "PASS"', value["stdout"])


if __name__ == "__main__":
    unittest.main()
