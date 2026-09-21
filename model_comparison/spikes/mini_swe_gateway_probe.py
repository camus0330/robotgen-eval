"""One real mini-swe query using RobotGen's existing API config; never execute actions."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.metadata
import inspect
import io
import json
import logging
import os
from pathlib import Path
import platform
import re
import socket
import sys
import tempfile
from urllib.parse import urlsplit


SHA = "04d809ceab9df28f9adaed044884180159172930"
CACHE_NAME = "9b5ad71b2ce5302211f9c61530b329a4922fc6a4"
CACHE_SHA = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
EXIT = {"PASS": 0, "FAIL": 1, "CONFIG_BLOCKED": 2, "FORMAT_MISMATCH": 3,
        "ENDPOINT_FAILED": 4, "ENVIRONMENT_BLOCKED": 5}
MESSAGES = [
    {"role": "system", "content": "You are participating in a compatibility test. Follow the requested output format exactly."},
    {"role": "user", "content": "Return exactly one mini-swe action block whose command is:\n\necho robotgen_gateway_probe\n\nUse this exact fence name:\n\nmswea_bash_command\n\nDo not return any other action block."},
]


class ConfigBlocked(Exception):
    pass


def require(condition, message):
    if not condition:
        raise ConfigBlocked(message)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--config", required=True, type=Path)
    cli.add_argument("--cache", required=True, type=Path)
    args = cli.parse_args()
    secrets = []
    result = {
        "config_path": str(args.config.resolve()), "query_count": 0, "key_source": "none",
        "mini_swe_retry_attempts": 1, "provider_retries": 0,
        "gateway_network_targets": [], "unrelated_network_attempts": [],
        "response_type": None, "returned_model": None, "finish_reason": None,
        "assistant_content": None, "actions": None, "usage": None, "cost": "not observed",
    }

    def sanitize(value):
        if isinstance(value, dict):
            return {k: sanitize(v) for k, v in value.items()
                    if k.lower() not in {"api_key", "authorization", "headers", "extra_headers"}}
        if isinstance(value, list):
            return [sanitize(v) for v in value]
        if isinstance(value, str):
            for secret in secrets:
                value = value.replace(secret, "[REDACTED]")
            value = re.sub(r"(?i)(authorization\s*[:=]\s*|bearer\s+)[^\s,}\]]+", "[REDACTED]", value)
        return value

    # Never emit dependency logs or raw tracebacks, even when an SDK embeds request data.
    logging.disable(logging.CRITICAL)
    capture = io.StringIO()
    status = "CONFIG_BLOCKED"
    stage = "config"
    try:
        config = json.loads(args.config.read_text(encoding="utf-8-sig"))
        require(isinstance(config, dict), "config must be an object")
        inline = config.get("api_key", "")
        if isinstance(inline, str) and inline:
            secrets.append(inline)
        env_name = config.get("api_key_env", "")
        require(isinstance(env_name, str), "api_key_env must be a string")
        env_key = os.environ.get(env_name, "") if env_name else ""
        if env_key:
            secrets.append(env_key)
        key = env_key or (inline if isinstance(inline, str) else "")
        result["key_source"] = "env" if env_key else "config" if key else "none"
        # Credentials unrelated to this config and all proxy/config overrides are removed by name.
        allowed = {"PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP"}
        for name in tuple(os.environ):
            if name.upper() not in allowed:
                del os.environ[name]
        os.environ.update({
            "NO_PROXY": "*", "PYTHON_DOTENV_DISABLED": "1", "MSWEA_SILENT_STARTUP": "1",
            "MSWEA_GLOBAL_CONFIG_DIR": tempfile.mkdtemp(prefix="robotgen-gateway-config-"),
            "LITELLM_MODE": "PRODUCTION", "LITELLM_LOCAL_MODEL_COST_MAP": "True",
            "MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT": "1",
        })
        result.update({k: config.get(k) for k in ("provider", "model", "base_url", "api_path", "api_format")})
        require(config.get("schema_version") == "robot-model-api-config/0.1", "unsupported schema_version")
        require(config.get("provider") == "smart_agi_gateway", "unsupported provider")
        require(config.get("api_format") == "openai_chat_completions", "unsupported api_format")
        request = config.get("request")
        require(isinstance(request, dict), "request must be an object")
        require(request.get("stream") is False, "request.stream must be false")
        require(type(request.get("max_retries")) is int and request["max_retries"] == 0, "request.max_retries must be 0")
        timeout = request.get("timeout_s")
        require(type(timeout) in (int, float) and 0 < timeout < float("inf"), "timeout_s must be finite and positive")
        result["timeout_s"] = timeout
        base = config.get("base_url")
        require(isinstance(base, str), "base_url must be a string")
        url = urlsplit(base)
        require(url.scheme == "https" and bool(url.hostname) and not url.username and not url.password
                and not url.query and not url.fragment and url.path in ("", "/"), "unsupported base_url shape")
        require(config.get("api_path") == "/v1/chat/completions", "unsupported api_path")
        api_base = base.rstrip("/") + "/v1"
        result["derived_api_base"] = api_base
        model_id = config.get("model")
        require(isinstance(model_id, str) and bool(model_id.strip()), "model is empty")
        require(model_id not in {"model_A", "model_B", "model_C"}, "model slot is not a server model ID")
        result["routed_model_name"] = "openai/" + model_id
        require(bool(key), "API key unavailable from env/config")
        generation = {k: request[k] for k in ("temperature", "top_p", "max_tokens", "seed")
                      if request.get(k) is not None}
        extra = request.get("extra_body", {})
        require(isinstance(extra, dict), "extra_body must be an object")
        require(not any(k.lower() in ("model", "messages", "stream", "tools", "api_key", "api_base",
                                             "max_retries", "num_retries", "drop_params", "extra_headers") for k in extra),
                "extra_body conflicts with this pilot's fixed request boundaries")
        if extra:
            generation["extra_body"] = extra
        result["non_null_generation_parameters"] = generation
        stage = "environment"
        cache = args.cache.resolve()
        digest = hashlib.sha256((cache / CACHE_NAME).read_bytes()).hexdigest()
        if digest != CACHE_SHA:
            raise OSError("prepared tokenizer SHA-256 mismatch")
        os.environ["CUSTOM_TIKTOKEN_CACHE_DIR"] = str(cache)
        result.update({"cache_sha256": digest, "python": sys.version, "platform": platform.platform()})
        dist = importlib.metadata.distribution("mini-swe-agent")
        origin = json.loads(dist.read_text("direct_url.json") or "{}")
        if (origin.get("vcs_info", {}).get("commit_id") != SHA or dist.version != "2.4.6"
                or origin.get("url") != "https://github.com/SWE-agent/mini-swe-agent.git"):
            raise OSError("mini-swe provenance mismatch")
        result.update({"upstream_sha": SHA, "mini_swe_version": dist.version})
        for name, expected in (("litellm", "1.102.0"), ("tiktoken", "0.14.0")):
            result[name] = importlib.metadata.version(name)
            if result[name] != expected:
                raise OSError(f"{name} differs from reviewed environment")
        addresses = set()
        network_enabled = False
        host, port = url.hostname, url.port or 443

        def audit(event, values):
            target = None
            permitted = False
            if event == "socket.getaddrinfo":
                target = [values[0], values[1]]
                permitted = network_enabled and values[0] == host and values[1] == port
            elif event == "socket.connect":
                target = values[1]
                permitted = network_enabled and isinstance(target, tuple) and target[0] in addresses and target[1] == port
            elif event == "http.client.connect":
                target = [values[1], values[2]]
                permitted = network_enabled and target == [host, port]
            elif event == "http.client.send":
                target = "HTTP send (headers omitted)"
                permitted = network_enabled and getattr(values[0], "host", None) == host
            elif event in {"socket.gethostbyname", "socket.gethostbyaddr", "socket.sendto", "socket.sendmsg"}:
                target = event
            elif event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"}:
                target = "forbidden process execution"
            elif event == "open" and isinstance(values[0], (str, os.PathLike)) and Path(values[0]).name.lower() == ".env":
                target = "forbidden dotenv access"
            else:
                return
            record = {"event": event, "target": target}
            result["gateway_network_targets" if permitted else "unrelated_network_attempts"].append(record)
            if not permitted:
                raise PermissionError(f"gateway boundary rejected {event}")

        sys.addaudithook(audit)
        with redirect_stdout(capture), redirect_stderr(capture):
            import litellm
            from minisweagent.exceptions import FormatError
            from minisweagent.models.litellm_textbased_model import LitellmTextbasedModel

            # Native library settings only: no function/provider/cost/parser patches.
            litellm.telemetry = False
            litellm.drop_params = False
            litellm.suppress_debug_info = True
            litellm.num_retries = 0
            litellm.num_retries_per_request = 0
            package = Path(dist.locate_file("minisweagent")).resolve()
            if not Path(inspect.getfile(LitellmTextbasedModel)).resolve().is_relative_to(package):
                raise OSError("model import outside pinned distribution")
            if os.environ.get("TIKTOKEN_CACHE_DIR") != str(cache) or result["unrelated_network_attempts"]:
                raise OSError("offline import/cache boundary failed")
            model = LitellmTextbasedModel(
                model_name=result["routed_model_name"], cost_tracking="ignore_errors",
                model_kwargs={"api_base": api_base, "api_key": key, "timeout": timeout,
                              "max_retries": 0, "num_retries": 0, "stream": False, **generation},
            )
            # Observe only the type returned by real _query; do not replace any callable.
            def observe_return(frame, event, value):
                if event == "return" and frame.f_code is LitellmTextbasedModel._query.__code__ and value is not None:
                    result["response_type"] = f"{type(value).__module__}.{type(value).__name__}"

            network_enabled = True
            addresses.update(row[4][0] for row in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))
            stage = "query"
            result["query_count"] = 1
            previous_profile = sys.getprofile()
            sys.setprofile(observe_return)
            try:
                output = model.query(MESSAGES)
                extra_output = output["extra"]
                result["actions"] = extra_output["actions"]
                result["assistant_content"] = output.get("content")
                status = "PASS" if result["actions"] == [{"command": "echo robotgen_gateway_probe"}] else "FORMAT_MISMATCH"
            except FormatError as error:
                extra_output = error.messages[0].get("extra", {})
                result["format_error"] = {k: extra_output.get(k) for k in ("n_actions", "model_response", "interrupt_type")}
                result["assistant_content"] = extra_output.get("model_response")
                status = "FORMAT_MISMATCH"
            finally:
                sys.setprofile(previous_profile)
            payload = extra_output.get("response", {})
            if isinstance(payload, dict):
                result["returned_model"] = payload.get("model")
                result["usage"] = payload.get("usage")
                choices = payload.get("choices") or []
                result["finish_reason"] = choices[0].get("finish_reason") if choices else None
            cost = extra_output.get("cost")
            result["cost"] = cost if cost else "cost unavailable / ignored"
    except ConfigBlocked as error:
        status = "CONFIG_BLOCKED"
        result["reason"] = str(error)
    except AssertionError as error:
        status = "FAIL"
        result["sanitized_message"] = sanitize(str(error))
    except Exception as error:
        status = "CONFIG_BLOCKED" if stage == "config" else "ENVIRONMENT_BLOCKED" if stage == "environment" else "ENDPOINT_FAILED"
        result["exception_class"] = type(error).__name__
        result["sanitized_message"] = sanitize(str(error))[:1500]
    finally:
        capture.close()  # Raw dependency output is discarded, never written to logs or reports.
    if result["unrelated_network_attempts"]:
        status = "ENVIRONMENT_BLOCKED"
    result["classification"] = status
    result["exit_code"] = EXIT[status]
    print(json.dumps(sanitize(result), ensure_ascii=True, indent=2))
    print(f"FINAL: {status}")
    return EXIT[status]


if __name__ == "__main__":
    raise SystemExit(main())
