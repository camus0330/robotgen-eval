"""Bounded native Codex image admission; no robot generation or token export."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / "model_comparison/records/pilot_20260923/alternate_access_20260923"
CANDIDATES = ("gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-terra")
DISABLED = ("shell_tool", "unified_exec", "apps", "plugins", "browser_use",
            "browser_use_external", "computer_use", "image_generation", "view_image",
            "code_mode", "code_mode_host", "multi_agent", "multi_agent_v2", "memories",
            "skill_search", "goals", "unbounded_connection_retries", "workspace_dependencies")


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def config_args(*, cad=False, python_executable=None, guard_path=None, native_linux=False):
    settings = {"model_provider": "openai", "approval_policy": "never", "web_search": "disabled",
                "project_doc_max_bytes": 0, "skills.include_instructions": False,
                "skills.bundled.enabled": False, "features.skip_host_skill_discovery": True,
                "show_raw_agent_reasoning": False, "shell_environment_policy.inherit": "none",
                "include_permissions_instructions": False}
    settings.update({"features." + name: False for name in DISABLED})
    guard = guard_path or Path(__file__).with_name("pilot_alt_guard.py")
    command_argv = [python_executable or sys.executable, "-I", "-B", str(guard)] + (["--cad"] if cad else [])
    command = shlex.join(command_argv) if native_linux else subprocess.list2cmdline(command_argv)
    args = []
    for k, v in settings.items():
        args += ["-c", k + "=" + json.dumps(v)]
    hook = '[{matcher=".*",hooks=[{type="command",command=' + json.dumps(command) + ',timeout=10}]}]'
    args += ["-c", "hooks.PreToolUse=" + hook]
    return args


def permission_args():
    # No broad home/repository read grant; client auth is not a tool mount.
    return ["-c", 'default_permissions="robotgen-alt"',
            "-c", 'permissions.robotgen-alt.filesystem={":minimal"="read",":workspace_roots"={"."="read"}}',
            "-c", "permissions.robotgen-alt.network.enabled=false"]


def admission(model):
    if model not in CANDIDATES:
        raise ValueError("undiscovered candidate")
    destination = RECORD / (model + "_admission.json")
    if destination.exists():
        raise ValueError("one admission per model; result already exists")
    work = Path(tempfile.mkdtemp(prefix="robotgen-alt-access-"))
    image = work / "reference.png"
    shutil.copyfile(ROOT / "outputs/pilot_20260923/input_kit/inputs/assets/reference.png", image)
    prompt = "Access check only. Describe the attached image in one short sentence, then write ACCESS_IMAGE_OK. Do not use tools, execute code, or create a robot design."
    argv = [shutil.which("codex"), "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral",
            "--strict-config", "--skip-git-repo-check", "--dangerously-bypass-hook-trust",
            "--sandbox", "read-only", "--color", "never", "--json", "-C", str(work),
            "-m", model, "-i", str(image)] + config_args() + [prompt]
    state = {"model_requested": model, "classification": "STARTED", "started_at": stamp(),
             "argv": argv, "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
             "independent_session": True, "robot_generation": False,
             "api_query_calls": None, "api_query_count_source": "not_observed",
             "provider_retries_observed": None, "events": [], "os_exit_code": None}
    write(destination, state)  # One-attempt journal exists BEFORE launching the client.
    # Authentication stays inside the official client. No credential files read.
    env = {k: os.environ[k] for k in ("SystemRoot", "WINDIR", "PATH", "USERPROFILE", "APPDATA",
            "LOCALAPPDATA", "TEMP", "TMP", "HOMEDRIVE", "HOMEPATH") if k in os.environ}
    start = time.monotonic()
    try:
        child = subprocess.run(argv, cwd=work, env=env, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=120)
        state["os_exit_code"] = child.returncode
        # Retain only native visible final messages, usage and errors; no reasoning events.
        for line in child.stdout.splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            kind = item.get("type")
            if kind in ("thread.started", "turn.completed", "turn.failed", "error"):
                state["events"].append(item)
            elif kind == "item.completed" and item.get("item", {}).get("type") == "agent_message":
                state["events"].append(item)
        # CLI diagnostics, not SDK dumps. Key material is absent from child env.
        state["stderr"] = child.stderr[-12000:]
        state["classification"] = "RESPONSE_RECEIVED" if child.returncode == 0 else "ACCESS_FAILED"
    except subprocess.TimeoutExpired:
        state["classification"] = "ACCESS_TIMEOUT"
        state["os_exit_code"] = 124
    state.update(ended_at=stamp(), elapsed_s=time.monotonic() - start)
    # Existing authorized env key is used only to screen the shareable record in memory.
    key = os.environ.get("SMART_AGI_API_KEY", "")
    if key and key in json.dumps(state, ensure_ascii=False):
        write(destination, {"classification": "OUTPUT_CREDENTIAL_MATCH", "os_exit_code": state["os_exit_code"]})
        return 2
    write(destination, state)
    print(json.dumps({k: state[k] for k in ("model_requested", "classification", "os_exit_code", "elapsed_s")}))
    return state["os_exit_code"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--admit", choices=CANDIDATES, required=True)
    raise SystemExit(admission(parser.parse_args().admit))
