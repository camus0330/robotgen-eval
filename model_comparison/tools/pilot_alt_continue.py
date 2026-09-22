"""Bounded continuation startup checks; never invokes a model for admission."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

from pilot_alt_access import RECORD, permission_args, stamp, write

CONTINUATION = RECORD / "continuation_20260923_0332"


def windows_check():
    evidence = CONTINUATION / "windows_startup_1.json"
    if evidence.exists():
        raise ValueError("bounded check already executed; reuse evidence")
    base = Path("D:/robotgen-alt-runtime") / uuid.uuid4().hex
    work, external, clean_home = (base / x for x in ("work", "external", "client-state"))
    for path in (work, external, clean_home):
        path.mkdir(parents=True)
        for parent in [path, *path.parents]:
            if parent.stat().st_file_attributes & 0x400:
                raise ValueError("reparse path forbidden")
    marker = external / "synthetic.txt"
    marker.write_text("SYNTHETIC_EXTERNAL_MARKER_ONLY", encoding="utf-8")
    (work / "allowed.txt").write_text("allowed", encoding="utf-8")
    codex = str(Path(shutil.which("codex")).resolve(strict=True))
    shell = str(Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe")
    command = (
        "try { if ([IO.File]::ReadAllText('allowed.txt') -ne 'allowed') { exit 3 } } catch { exit 3 }; "
        "try { $null=[IO.File]::ReadAllText('" + str(marker) + "'); exit 4 } catch {}; "
        "try { [IO.File]::WriteAllText('" + str(external / 'forbidden-write.txt') + "','synthetic'); exit 5 } catch {}; "
        "Write-Output 'SCOPED_READ_WRITE_PASS'; exit 0")
    argv = [codex, "sandbox", "-P", "robotgen-alt", "-C", str(work)] + permission_args() + [
        "-c", "permissions.robotgen-alt.workspace_roots={" + json.dumps(str(work)) + "=true}",
        shell, "-NoProfile", "-NonInteractive", "-Command", command]
    env = {k: os.environ[k] for k in ("SystemRoot", "WINDIR", "PATH", "USERPROFILE", "APPDATA",
           "LOCALAPPDATA", "TEMP", "TMP", "HOMEDRIVE", "HOMEPATH") if k in os.environ}
    # sandbox has no --ignore-user-config flag. Use an empty per-check state root;
    # future exec uses its supported --ignore-user-config with identical profile.
    env["CODEX_HOME"] = str(clean_home)
    state = {"run_id": CONTINUATION.name, "started_at": stamp(), "platform": "Windows",
             "python_parent_cwd": str(Path.cwd()), "subprocess_cwd": str(work), "codex_C": str(work),
             "codex_path": codex, "powershell_path": shell, "argv": argv,
             "config_source": "explicit -c profile; empty per-check CODEX_HOME; no user/global config changes",
             "codex_home": str(clean_home), "profile": "robotgen-alt", "legacy_sandbox_mode": False,
             "synthetic_external_root": str(external), "external_outside_minimal": "dedicated D drive data directory",
             "model_requests": 0, "os_exit_code": None, "passed": False}
    write(evidence, state)
    try:
        child = subprocess.run(argv, cwd=work, env=env, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=90)
        state.update(os_exit_code=child.returncode, stdout=child.stdout, stderr=child.stderr,
                     passed=child.returncode == 0 and "SCOPED_READ_WRITE_PASS" in child.stdout)
    except subprocess.TimeoutExpired:
        state.update(os_exit_code=124, failure="STARTUP_TIMEOUT")
    state["ended_at"] = stamp()
    write(evidence, state)
    print(json.dumps({k:state[k] for k in ("run_id", "os_exit_code", "passed")}))
    return 0 if state["passed"] else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows-check", action="store_true", required=True)
    parser.parse_args()
    raise SystemExit(windows_check())
