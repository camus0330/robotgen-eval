"""Explicit batch configuration and gates for the existing restored CAD runner.

No model client, Agent, sandbox, evaluator or paid admission is implemented here.
"""
import datetime as dt
import hashlib
import importlib.metadata as metadata
import json
import math
from pathlib import Path
import re

from pilot_snapshot import relative_name
from pilot_run import BASELINE, CACHE_NAME, CACHE_SHA, ROOT

SCHEMA = "pilot-restored-batch/2"
SLOTS = {"model_A", "model_B", "model_C"}
CODE = ["pilot_batch.py", "pilot_restored.py", "pilot_run.py", "pilot_sandbox.py",
        "pilot_snapshot.py", "pilot_cad.py", "pilot_evaluate.py", "experiment.py"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def config_hash(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def local(value, interpreter=False):
    relative_name(value)
    path = ROOT / value
    checked = path.parent if interpreter else path
    if checked.resolve() != checked or not path.is_relative_to(ROOT):
        raise ValueError("batch paths must be literal repo-relative paths without symlinks")
    return path


def single(value):
    relative_name(value)
    if "/" in value:
        raise ValueError("batch/run IDs must be a single path component")
    return value


def validate_config(config):
    if set(config) != {"provider", "model", "base_url", "api_path", "api_key_env", "request"}:
        raise ValueError("explicit model config fields required; inline credentials forbidden")
    from urllib.parse import urlsplit
    url = urlsplit(config["base_url"])
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("credential-free HTTPS API base required")
    if config["api_path"] != "/chat/completions" or url.path.rstrip("/") != "/v1":
        raise ValueError("base_url must include /v1 once; api_path must be /chat/completions")
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", config["api_key_env"]):
        raise ValueError("credential source must be an environment variable name")
    if not config["provider"] or not config["model"]:
        raise ValueError("provider and exact requested model required")
    request = config["request"]
    if set(request) != {"timeout_s", "max_retries", "stream", "temperature", "max_tokens"}:
        raise ValueError("explicit request policy required")
    if request["max_retries"] != 0 or request["stream"] is not False:
        raise ValueError("retries/stream are disabled")
    if not positive(request["timeout_s"]):
        raise ValueError("positive request timeout required")
    if request["max_tokens"] is not None and not positive(request["max_tokens"], integer=True):
        raise ValueError("max_tokens must be a positive integer or null")
    if request["temperature"] is not None and not finite(request["temperature"]):
        raise ValueError("temperature must be finite or null")


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def positive(value, integer=False):
    return (type(value) is int if integer else finite(value)) and value > 0


def validate_shape(plan):
    if plan.get("schema_version") != SCHEMA:
        raise ValueError("explicit v2 plan required; historical default batches cannot run")
    batch = single(plan["batch_id"])
    paths = plan["paths"]
    if set(paths) != {"kit", "output_root", "results_root", "record_root", "addendum"}:
        raise ValueError("all batch paths must be explicit")
    for name in ("kit", "output_root", "results_root", "record_root"):
        path = local(paths[name])
        if batch not in path.parts:
            raise ValueError("every runtime/evidence path must belong to this batch")
        if not any(path.is_relative_to(ROOT / prefix) for prefix in
                   ("outputs", "results", "model_comparison/records")):
            raise ValueError("batch paths must be in generated-output or evidence directories")
    roots = [local(paths[name]) for name in ("kit", "output_root", "results_root", "record_root")]
    if any(a == b or a in b.parents or b in a.parents for i, a in enumerate(roots) for b in roots[i+1:]):
        raise ValueError("kit, participant outputs, results and operator records must be disjoint")
    if local(paths["addendum"]).parent != local(paths["record_root"]):
        raise ValueError("public addendum must be bound inside this batch's record directory")
    if not plan["models"] or not set(plan["models"]) <= SLOTS:
        raise ValueError("explicit nonempty model slots required")
    if set(plan["run_names"]) != set(plan["models"]) or len(set(plan["run_names"].values())) != len(plan["models"]):
        raise ValueError("one distinct run name per model slot required")
    for name in plan["run_names"].values():
        single(name)
    if sorted(plan["serial_order"]) != sorted(plan["models"]):
        raise ValueError("explicit serial order must cover each slot exactly once")
    for config in plan["models"].values():
        validate_config(config)
    for name in ("client_python", "cad_venv", "cache"):
        local(plan["runtime"][name], interpreter=name == "client_python")
    if plan["budget"].get("scope") != "per_run":
        raise ValueError("this runner requires an explicit uniform per-run budget")
    if plan["budget"].get("provider_retries") != 0 or plan["budget"].get("human_design_edits") != 0:
        raise ValueError("provider retries and human design edits must remain zero")
    if plan["deadline"] is not None:
        parsed = dt.datetime.fromisoformat(plan["deadline"])
        if parsed.tzinfo is None:
            raise ValueError("deadline requires an explicit timezone")


def verify(plan):
    validate_shape(plan)
    if plan["frozen_input_baseline"] != BASELINE:
        raise ValueError("frozen input baseline changed")
    from pilot_run import git_blob, digest
    expected = json.loads(git_blob("model_comparison/records/input_manifest.json"))
    kit = local(plan["paths"]["kit"])
    if plan["input_files"] != expected["files"] or plan["input_manifest_sha256"] != digest(git_blob("model_comparison/records/input_manifest.json")):
        raise ValueError("input plan differs from frozen Git manifest")
    if sha(kit / "records/input_manifest.json") != plan["input_manifest_sha256"]:
        raise ValueError("kit manifest changed")
    from experiment import verify_inputs
    verify_inputs(kit)
    from pilot_snapshot import safe_snapshot
    allowed = {"inputs/" + row["path"] for row in expected["files"]}
    allowed.update(("records/input_manifest.json", "tools/experiment.py"))
    if {row["path"] for row in safe_snapshot(kit)["files"]} != allowed:
        raise ValueError("kit contains unbound files outside the public input contract")
    if sha(kit / "tools/experiment.py") != digest(git_blob("model_comparison/tools/experiment.py")):
        raise ValueError("kit intake code changed")
    if sha(local(plan["paths"]["addendum"])) != plan["addendum_sha256"]:
        raise ValueError("public addendum changed")
    required = {"model_comparison/tools/" + n for n in CODE}
    required.add("model_comparison/spikes/mini_swe_gateway_agent_e2e.py")
    if set(plan["code_sha256"]) != required:
        raise ValueError("incomplete code binding")
    for name, expected_hash in plan["code_sha256"].items():
        if sha(local(name)) != expected_hash:
            raise ValueError("batch-bound runner/evaluator code changed")


def prepare(spec_path, plan_path):
    from pilot_run import bind_inputs, SYSTEM_PROMPT
    spec = read(spec_path)
    validate_shape(spec)
    roots = [local(spec["paths"][n]) for n in ("kit", "output_root", "results_root", "record_root")]
    plan_path = Path(plan_path).absolute()
    if plan_path.parent != local(spec["paths"]["record_root"]):
        raise ValueError("plan must be inside its new record directory")
    if any(p.exists() for p in roots):
        raise ValueError("batch directories already exist; refusing overwrite/reuse")
    addon = local(spec["addendum_source"]).read_bytes()
    # Validate configuration before reserving any path. No runtime tests/API.
    for path in roots:
        path.mkdir(parents=True, exist_ok=False)
    bind_inputs(local(spec["paths"]["kit"]))
    local(spec["paths"]["addendum"]).write_bytes(addon)
    kit = local(spec["paths"]["kit"])
    spec.update(frozen_input_baseline=BASELINE,
                input_files=read(kit / "records/input_manifest.json")["files"],
                input_manifest_sha256=sha(kit / "records/input_manifest.json"),
                addendum_sha256=hashlib.sha256(addon).hexdigest(),
                system_prompt_sha256=hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
                code_sha256={"model_comparison/tools/" + n: sha(ROOT / "model_comparison/tools" / n) for n in CODE})
    helper = "model_comparison/spikes/mini_swe_gateway_agent_e2e.py"
    spec["code_sha256"][helper] = sha(ROOT / helper)
    for slot, config in spec["models"].items():
        write_new(local(spec["paths"]["record_root"]) / (slot + ".config.json"), config)
    write_new(plan_path, spec)
    return spec


def runtime_gate(plan):
    """Reuse prior evidence and read metadata; no repeated CAD/environment probe."""
    try:
        runtime = plan["runtime"]
        evidence_path = local(runtime["evidence"]["path"])
        if sha(evidence_path) != runtime["evidence"]["sha256"]:
            return False
        evidence = read(evidence_path)
        if evidence["status"] != "CAD_CLIENT_CACHE_PASS_GENERATION_GATE_CLOSED":
            return False
        for key, stored in (("cad_venv", "cad_runtime"), ("client_python", "model_client"), ("cache", "tokenizer_cache")):
            actual = local(runtime[key], interpreter=key == "client_python")
            expected = Path(evidence["local_paths"][stored])
            if actual != (expected / "bin/python" if key == "client_python" else expected):
                return False
        if not local(runtime["client_python"], interpreter=True).is_file() or not (local(runtime["cad_venv"]) / "bin/python").is_file():
            return False
        if sha(local(runtime["cache"]) / CACHE_NAME) != CACHE_SHA:
            return False
        cad_paths = list((local(runtime["cad_venv"]) / "lib").glob("python*/site-packages"))
        cad_versions = {d.metadata["Name"].lower().replace('_', '-'): d.version
                        for d in metadata.distributions(path=[str(p) for p in cad_paths])}
        if any(cad_versions.get(n) != v for n, v in (("cadquery", "2.6.1"), ("cadquery-ocp", "7.8.1.1.post1"), ("numpy", "2.2.6"))):
            return False
        client_root = local(runtime["client_python"], interpreter=True).parent.parent
        paths = list((client_root / "lib").glob("python*/site-packages"))
        distributions = {d.metadata["Name"].lower().replace('_', '-'): d for d in metadata.distributions(path=[str(p) for p in paths])}
        if any(distributions[n].version != v for n, v in (("mini-swe-agent", "2.4.6"), ("litellm", "1.102.0"), ("tiktoken", "0.14.0"))):
            return False
        origin = json.loads(distributions["mini-swe-agent"].read_text("direct_url.json"))
        return (origin.get("url") == "https://github.com/SWE-agent/mini-swe-agent.git"
                and origin["vcs_info"]["commit_id"] == "04d809ceab9df28f9adaed044884180159172930")
    except (OSError, ValueError, KeyError, TypeError):
        return False


def authorization_gate(plan, now=None):
    budget = plan["budget"]
    auth = plan["authorization"]
    now = now or dt.datetime.now(dt.timezone.utc)
    if auth.get("robot_generation") is not True or not isinstance(auth.get("source"), str) or not auth["source"].strip() or plan["deadline"] is None:
        return False
    if not all(positive(budget.get(k), integer=k in ("max_queries", "max_consecutive_format_errors"))
               for k in ("wall_time_s", "max_queries", "cost_limit", "max_consecutive_format_errors")):
        return False
    if budget.get("cost_limit_semantics") != "library_estimate_usd_not_billing_cap":
        return False
    return (dt.datetime.fromisoformat(plan["deadline"]) - now).total_seconds() > budget["wall_time_s"]


def channel_gate(plan, plan_hash, admission, slot):
    if admission.get("batch_id") != plan["batch_id"] or admission.get("plan_sha256") != plan_hash:
        return False
    config = plan["models"][slot]
    cases = [c for c in admission.get("cases", []) if c.get("slot") == slot]
    if len(cases) != 1:
        return False
    case = cases[0]
    return (case.get("scope") == "HARNESS_PROTOCOL_IMAGE_ADMISSION"
            and case.get("model_config_sha256") == config_hash(config)
            and case.get("request_model_id") == config["model"]
            and case.get("image_sha256") == sha(local(plan["paths"]["kit"]) / "inputs/assets/reference.png")
            and case.get("finish_reason") == "stop"
            and all(case.get(k) is True for k in ("parser_pass", "nonempty_completion", "image_url_in_completion_messages", "image_content_review_pass")))


def gates(plan, plan_path, admission_path, slot=None):
    import os
    verify(plan)
    slots = [slot] if slot else list(plan["models"])
    if not set(slots) <= set(plan["models"]):
        raise ValueError("slot absent from explicit batch plan")
    admission = read(admission_path) if admission_path and Path(admission_path).is_file() else {}
    runtime = runtime_gate(plan)
    channel = {s: channel_gate(plan, sha(plan_path), admission, s) for s in slots}
    authorized = authorization_gate(plan)
    credentials = {s: bool(os.environ.get(plan["models"][s]["api_key_env"], "").strip()) for s in slots}
    ready = runtime and all(channel.values()) and authorized and all(credentials.values())
    classification = ("ENVIRONMENT_BLOCKED" if not runtime else "ACCESS_BLOCKED" if not all(channel.values())
                      else "AUTHORIZATION_BLOCKED" if not authorized else "CREDENTIAL_BLOCKED" if not all(credentials.values()) else "READY")
    return {"batch_id": plan["batch_id"], "plan_sha256": sha(plan_path),
            "runtime_available": runtime, "channel_admitted": channel,
            "experiment_authorized": authorized, "credential_available": credentials,
            "generation_ready": ready, "classification": classification, "exit_code": 0 if ready else 2}
