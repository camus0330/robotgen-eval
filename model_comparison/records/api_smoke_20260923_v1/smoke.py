"""One-shot SDK channel test. Never executes a completion or starts an Agent."""
import base64
import datetime as dt
import getpass
import hashlib
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import sys
import time

from openai import OpenAI, DefaultHttpxClient, APIStatusError

ROOT = Path(__file__).resolve().parents[3]
BATCH = Path(__file__).resolve().parent
IMAGE = ROOT / "model_comparison/inputs/assets/reference.png"
BASE_URL = "https://big-model.smart-agi.com/v1"
TARGET = BASE_URL + "/chat/completions"
IMAGE_PROMPT = "仅根据附图，描述主体的姿态、主要颜色和三项可见结构细节。不清楚的地方明确说明，不推测尺寸，不生成设计或代码。"


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def redact(value, key):
    if isinstance(value, str):
        return value.replace(key, "[REDACTED]") if key else value
    if isinstance(value, dict):
        return {k: redact(v, key) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, key) for v in value]
    return value


def save(path, data, key):
    # Only this newly reserved run directory is written. Never serialize an SDK
    # response wholesale: it could contain hidden reasoning or request headers.
    text = json.dumps(redact(data, key), ensure_ascii=False, indent=2) + "\n"
    with path.open("w", encoding="utf-8") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())


def request_once(client, key, run, index, model, messages, max_tokens, image_sha=None):
    record = dict(request_model=model, expected_target=TARGET, actual_target=None,
                  started_at=stamp(), elapsed_s=None, http_status=None,
                  reply=None, error=None, returned_model=None, finish_reason=None,
                  usage=None, request_id=None, client_max_retries=0,
                  outcome="STARTED_OUTCOME_UNKNOWN", valid_completion=False,
                  image_sha256=image_sha, image_in_request=image_sha is not None,
                  image_send_attempted=False, image_server_accepted=None,
                  answer_matches_image=None, visual_review="NOT_PERFORMED",
                  client_request_started=True, http_send_attempts=0)
    path = run / f"{index}_{model}.json"
    save(path, record, key)  # Durable before entering any network call.

    def guard(request):
        if str(request.url) != TARGET or request.method != "POST":
            raise ValueError("unexpected endpoint or method rejected")
        if record["http_send_attempts"]:
            raise ValueError("repeat HTTP send rejected")
        record.update(actual_target=TARGET, http_send_attempts=1,
                      image_send_attempted=image_sha is not None)
        save(path, record, key)

    # Public httpx hooks observe only method/URL, never credentials or headers.
    client._client.event_hooks["request"] = [guard]
    start = time.monotonic()
    try:
        raw = client.chat.completions.with_raw_response.create(
            model=model, messages=messages, temperature=0,
            max_tokens=max_tokens, stream=False)
        record["http_status"] = raw.status_code
        record["request_id"] = raw.headers.get("x-request-id")
        response = raw.parse()
        choice = response.choices[0] if response.choices else None
        content = choice.message.content if choice else None
        finish = choice.finish_reason if choice else None
        usage = response.usage
        record.update(returned_model=response.model, reply=content,
                      finish_reason=finish,
                      usage={name: getattr(usage, name, None) for name in
                             ("prompt_tokens", "completion_tokens", "total_tokens")}
                      if usage else None)
        nonempty = isinstance(content, str) and bool(content.strip())
        record["valid_completion"] = nonempty and finish == "stop"
        record["outcome"] = ("EMPTY_CONTENT" if not nonempty else
                             "LENGTH_LIMIT" if finish == "length" else
                             "VALID_COMPLETION" if finish == "stop" else
                             "OTHER_FINISH_REASON")
        if index == 1:
            record["exact_OK"] = content == "OK"
        if image_sha:
            record["image_server_accepted"] = True
            record["visual_review"] = "PENDING_MANUAL_COMPARISON_WITH_ORIGINAL_PNG"
    except APIStatusError as error:
        record.update(http_status=error.status_code, request_id=error.request_id,
                      outcome="HTTP_ERROR_OUTCOME_UNKNOWN")
        body = error.body
        detail = body.get("error", body) if isinstance(body, dict) else None
        record["error"] = {"class": type(error).__name__}
        if isinstance(detail, dict):
            record["error"].update({name: redact(str(detail[name]), key)[:2000]
                                   for name in ("type", "code", "message")
                                   if detail.get(name) is not None})
        # Error/timeout alone cannot establish server execution or billing.
    except Exception as error:
        record.update(outcome="OUTCOME_UNKNOWN",
                      error={"class": type(error).__name__})
    finally:
        record.update(elapsed_s=round(time.monotonic() - start, 3), ended_at=stamp())
        save(path, record, key)
        print(json.dumps(redact(record, key), ensure_ascii=False), flush=True)
    return record


def run_checks(client, key, run):
    first = request_once(client, key, run, 1, "glm-5.3",
                         [{"role": "user", "content": "Reply with exactly: OK"}], 256)
    if not first["valid_completion"]:
        return 2
    # A local image-read failure must not consume another request.
    data = IMAGE.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("reference image is not PNG")
    uri = "data:image/png;base64," + base64.b64encode(data).decode("ascii")
    second = request_once(client, key, run, 2, "deepseek-v4-pro", [
        {"role": "user", "content": [
            {"type": "text", "text": IMAGE_PROMPT},
            {"type": "image_url", "image_url": {"url": uri}}]}],
        1024, hashlib.sha256(data).hexdigest())
    return 0 if second["valid_completion"] else 2


def main():
    # Process-local only: inherited SDK debug logging must not dump bodies or
    # headers. All permitted evidence is emitted explicitly below.
    logging.disable(logging.CRITICAL)
    key = os.environ.get("SMART_AGI_API_KEY", "").strip()
    if not key:
        if not sys.stdin.isatty():
            print("No Key: run this script in a local terminal for hidden getpass input.", file=sys.stderr)
            return 3
        key = getpass.getpass("SMART_AGI_API_KEY (hidden, not saved): ").strip()
    if not key:
        print("Empty Key; no request made.", file=sys.stderr)
        return 3
    run = BATCH / "live"
    # A rerun must never replay an uncertain or completed request.
    run.mkdir(mode=0o700, exist_ok=False)
    save(run / "environment.json", {
        "started_at": stamp(), "sdk": "openai",
        "sdk_version": importlib.metadata.version("openai"),
        "python": sys.version.split()[0], "max_chat_requests": 2,
        "client_max_retries": 0, "timeout_s": 120.0,
        "proxy_policy": "inherited unchanged; no headers or proxy values logged",
        "scope": "CHANNEL_SMOKE_ONLY_NOT_HARNESS_ADMISSION_OR_ROBOT_GENERATION"
    }, key)
    # Disable redirect following so credentials and requests stay on TARGET.
    with OpenAI(api_key=key, base_url=BASE_URL, max_retries=0, timeout=120.0,
                http_client=DefaultHttpxClient(follow_redirects=False)) as client:
        return run_checks(client, key, run)


if __name__ == "__main__":
    raise SystemExit(main())
