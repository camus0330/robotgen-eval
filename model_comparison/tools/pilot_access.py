"""One non-retrying, small admission request per declared gateway candidate.

No robot generation; only allowlisted response metadata is persisted.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

MODELS = ("deepseek-v4-pro", "kimi-k3", "glm-5.3")
ENDPOINT = "https://big-model.smart-agi.com/v1/chat/completions"
CATALOGUE = "https://big-model.smart-agi.com/api/v1/model-plaza"


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to repeat an existing admission batch")
    key = os.environ.get("SMART_AGI_API_KEY", "")
    if not key.strip():
        raise SystemExit("CONFIG_BLOCKED: selected environment credential absent")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(urllib.request.Request(CATALOGUE, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as response:
        catalogue_bytes = response.read()
    catalogue = json.loads(catalogue_bytes)
    # Persist the public catalogue independently of authenticated responses.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    catalogue_path = args.output.with_name("public_model_catalogue.json")
    catalogue_path.write_text(json.dumps(catalogue, ensure_ascii=False, indent=2), encoding="utf-8")
    evidence = {"started_at": now(), "endpoint": ENDPOINT, "identity_evidence_source": CATALOGUE,
                "catalogue_sha256": hashlib.sha256(catalogue_path.read_bytes()).hexdigest(),
                "provider_retries": 0, "robot_generation": False, "cases": []}
    # Reserve this batch before issuing its first request. Never overwrite it to retry.
    args.output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    for model in MODELS:
        case = {"request_model_id": model, "started_at": now(), "client_query_calls": 1,
                "completion_succeeded": False, "text_action_protocol": "not_observed",
                "backend_identity": "not_confirmed", "server_completion_count": "not_observed"}
        body = {"model": model, "stream": False, "max_tokens": 128,
                "messages": [{"role": "user", "content": "Reply with exactly this text action block, without executing it:\n```mswea_bash_command\necho pilot_admission\n```"}]}
        request = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(), headers={
            "Content-Type": "application/json", "Authorization": "Bearer " + key,
            "User-Agent": "RobotGen-pilot-admission/1"})
        try:
            with opener.open(request, timeout=120) as response:
                case["http_status"] = response.status
                payload = json.loads(response.read())
            choices = payload.get("choices", [])
            content = choices[0].get("message", {}).get("content") if choices else None
            case["completion_succeeded"] = isinstance(content, str) and bool(content)
            case["text_action_protocol"] = ("lexical_match_only" if isinstance(content, str) and
                content.strip() == "```mswea_bash_command\necho pilot_admission\n```" else "not_confirmed")
            case["classification"] = "COMPLETION_RECEIVED" if case["completion_succeeded"] else "INVALID_RESPONSE"
        except urllib.error.HTTPError as error:
            case["http_status"] = error.code
            case["safe_exception_class"] = type(error).__name__
            # Classify only; no raw error response, headers, or message is persisted.
            case["classification"] = "ACCESS_BLOCKED" if error.code in (401, 403, 404) else "ENDPOINT_FAILED"
            error.close()
        except Exception as error:
            case["classification"] = "ENDPOINT_FAILED"
            case["safe_exception_class"] = type(error).__name__
        case["ended_at"] = now()
        evidence["cases"].append(case)
        evidence["ended_at"] = now()
        serialized = json.dumps(evidence, ensure_ascii=False, indent=2)
        if key in serialized:
            raise SystemExit("CREDENTIAL_CHECK_FAILED")
        args.output.write_text(serialized + "\n", encoding="utf-8")
        print(json.dumps(case), flush=True)
    return 0 if all(c["completion_succeeded"] for c in evidence["cases"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
