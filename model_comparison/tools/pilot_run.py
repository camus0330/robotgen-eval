"""Deadline pilot preflight and fail-closed admission gate.

Generation is deliberately unavailable while all candidate routes are blocked.
This entry point never substitutes an unverified alias or executes model code.
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
    result = {"time": stamp(), "classification": "ACCESS_BLOCKED", "python": sys.executable,
              "python_version": sys.version.split()[0], "versions": versions, "upstream_sha": upstream,
              "client_provenance_pass": client_ok, "cache_path": str(CACHE),
              "cache_sha256": CACHE_SHA if cache_ok else None, "cache_pass": cache_ok,
              "input_binding": inputs, "canonical_kit": str(KIT),
              "selected_credential_present": bool(os.environ.get("SMART_AGI_API_KEY", "").strip()),
              "admission": admission["cases"], "generation_ready": False,
              "image_binding": "PLANNED: identical original PNG bytes as image_url data URI, once per instance; NOT_SENT",
              "uncompleted_gates": ["candidate completion + native protocol admission", "generation environment and hard lifecycle validation", "frozen executable runner and image transport validation"],
              "exit_code": 2}
    if not cache_ok or not client_ok:
        result["classification"] = "ENVIRONMENT_BLOCKED"
    write_json(RESULTS / "preflight.json", result)
    print(json.dumps({k: result[k] for k in ("classification", "client_provenance_pass", "cache_pass", "generation_ready", "exit_code")}))
    return 2


def run(slot):
    plan = json.loads((RECORDS / "plan.json").read_text(encoding="utf-8"))
    selected = next(m for m in plan["models"] if m["slot"] == slot)
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--slot", choices=("model_A", "model_B", "model_C"), required=True)
    args = parser.parse_args()
    return preflight() if args.command == "preflight" else run(args.slot)


if __name__ == "__main__":
    raise SystemExit(main())
