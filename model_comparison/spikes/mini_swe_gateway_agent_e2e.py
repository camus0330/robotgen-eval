"""Guarded mini-swe-agent gateway E2E spike.

The offline mode exercises the real DefaultAgent, text parser, LocalEnvironment,
observation formatter, and submit path with only LiteLLM's completion and cost
boundaries replaced by deterministic fixtures.  The live mode is deliberately
strict: it accepts only the reviewed gateway route and never reads the formal
RobotGen model configuration.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.metadata
import inspect
import json
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from urllib.parse import urlsplit


UPSTREAM_SHA = "04d809ceab9df28f9adaed044884180159172930"
UPSTREAM_URL = "https://github.com/SWE-agent/mini-swe-agent.git"
UPSTREAM_VERSION = "2.4.6"
LITELLM_VERSION = "1.102.0"
TIKTOKEN_VERSION = "0.14.0"
CACHE_NAME = "9b5ad71b2ce5302211f9c61530b329a4922fc6a4"
CACHE_SHA = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
REGEX = r"```mswea_bash_command\s*\n(.*?)\n```"
FIRST_COMMAND = "echo robotgen_gateway_agent_e2e"
SUBMIT_COMMAND = (
    "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT&&"
    "echo robotgen_gateway_agent_submission"
)
SUBMISSION = "robotgen_gateway_agent_submission\n"
SYNTHETIC_CREDENTIAL = "synthetic-credential-for-offline-leak-check"
SAFE_ENV_NAMES = {
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
    "TEMP", "TMP", "MSWEA_GLOBAL_CONFIG_DIR", "MSWEA_SILENT_STARTUP",
    "PYTHON_DOTENV_DISABLED", "LITELLM_MODE", "LITELLM_LOCAL_MODEL_COST_MAP",
    "MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT", "CUSTOM_TIKTOKEN_CACHE_DIR",
    "TIKTOKEN_CACHE_DIR",
}
EXIT = {"PASS": 0, "FAIL": 1, "ENVIRONMENT_BLOCKED": 2,
        "CONFIG_BLOCKED": 3, "FORMAT_MISMATCH": 4, "ENDPOINT_FAILED": 5}


class BoundaryAbort(BaseException):
    """A fail-closed boundary error that upstream must not turn into an observation."""


class ConfigBlocked(Exception):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ConfigBlocked(message)


def fixture_response(content: str) -> SimpleNamespace:
    """Return only a raw assistant response payload; parsing remains upstream."""
    message = {"role": "assistant", "content": content}
    payload = {"choices": [{"message": message, "finish_reason": "stop"}]}
    return SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(
                content=content,
                model_dump=lambda **kwargs: deepcopy(message),
            ),
            finish_reason="stop",
        )],
        model_dump=lambda **kwargs: deepcopy(payload),
    )


def sanitize(value: Any, secrets: list[str]) -> Any:
    """Keep summaries useful while never copying SDK payloads or credentials."""
    if isinstance(value, dict):
        return {
            str(key): sanitize(item, secrets)
            for key, item in value.items()
            if str(key).lower() not in {
                "api_key", "authorization", "headers", "extra_headers",
                "request", "request_kwargs", "traceback", "exception_info",
            }
        }
    if isinstance(value, (list, tuple)):
        return [sanitize(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"(?i)(authorization\s*[:=]\s*|bearer\s+)[^\s,}\]]+", "[REDACTED]", value)
    return value


def scrub_environment() -> None:
    """Remove inherited credentials and provider overrides without inspecting values."""
    for name in tuple(os.environ):
        if name.upper() not in SAFE_ENV_NAMES:
            os.environ.pop(name, None)
    os.environ.update({
        "MSWEA_SILENT_STARTUP": "1",
        "PYTHON_DOTENV_DISABLED": "1",
        "LITELLM_MODE": "PRODUCTION",
        "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        "MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT": "1",
    })


class BoundaryController:
    """Narrow audit policy for this fixed two-command smoke path."""

    def __init__(self, work: Path, host: str, port: int, secrets: list[str]):
        self.work = work.resolve()
        self.host = host
        self.port = port
        self.secrets = secrets
        self.network_enabled = False
        self.addresses: set[str] = set()
        self.failed = False
        self.launches: list[dict[str, Any]] = []
        self.gateway_network_targets: list[dict[str, Any]] = []
        self.unrelated_network_attempts: list[dict[str, Any]] = []
        self.local_runtime_ipc_targets: list[dict[str, Any]] = []

        # The reviewed gateway probe owns the CPython socketpair/asyncio IPC
        # exception.  Its policy still rejects ordinary localhost traffic.
        from mini_swe_gateway_probe import make_audit_policy
        self._gateway_policy = make_audit_policy(
            {
                "gateway_network_targets": self.gateway_network_targets,
                "unrelated_network_attempts": self.unrelated_network_attempts,
                "local_runtime_ipc_targets": self.local_runtime_ipc_targets,
            },
            host,
            port,
            self.addresses,
            lambda: self.network_enabled and not self.failed,
        )

    def _abort(self, reason: str) -> None:
        self.failed = True
        raise BoundaryAbort(reason)

    def _process(self, values: tuple[Any, ...]) -> None:
        if len(self.launches) >= 2 or len(values) < 4:
            self._abort("process execution limit or event shape rejected")
        executable, command, cwd, child_env = values[:4]
        if not executable or Path(str(cwd)).resolve() != self.work:
            self._abort("unexpected executable or cwd")
        expected = (FIRST_COMMAND, SUBMIT_COMMAND)[len(self.launches)]
        if os.name == "nt":
            exact_command = f'{executable} /c "{expected}"'
        else:
            exact_command = ["/bin/sh", "-c", expected]
        if command != exact_command:
            self._abort("command is outside the fixed echo allowlist")
        if child_env is not None:
            if any(str(name).upper() not in SAFE_ENV_NAMES for name in child_env):
                self._abort("child environment contains a non-allowlisted name")
            if any(secret and secret in str(value) for value in child_env.values() for secret in self.secrets):
                self._abort("credential reached the shell environment")
        self.launches.append({
            "index": len(self.launches) + 1,
            "executable_basename": Path(str(executable)).name,
            "command": expected,
            "cwd_is_temp": True,
            "child_env_safe": True,
        })

    def audit(self, event: str, values: tuple[Any, ...]) -> None:
        if event == "subprocess.Popen":
            self._process(values)
            return
        if event == "open" and values and isinstance(values[0], (str, os.PathLike)):
            if Path(values[0]).name.lower() in {".env", "api_config.json"}:
                self._abort("credential/config file access rejected")
        try:
            self._gateway_policy(event, values)
        except PermissionError as error:
            self.failed = True
            raise BoundaryAbort(str(error)) from None


def check_cache(cache: Path) -> str:
    cache = cache.resolve()
    require(cache.is_dir(), "prepared cache directory is missing")
    item = cache / CACHE_NAME
    require(item.is_file(), "prepared tokenizer cache file is missing")
    digest = hashlib.sha256(item.read_bytes()).hexdigest()
    require(digest == CACHE_SHA, "prepared tokenizer cache SHA-256 mismatch")
    os.environ["CUSTOM_TIKTOKEN_CACHE_DIR"] = str(cache)
    return digest


def provenance() -> dict[str, str]:
    dist = importlib.metadata.distribution("mini-swe-agent")
    direct_url = json.loads(dist.read_text("direct_url.json") or "{}")
    require(direct_url.get("url") == UPSTREAM_URL, "mini-swe-agent upstream URL mismatch")
    require(direct_url.get("vcs_info", {}).get("commit_id") == UPSTREAM_SHA,
            "mini-swe-agent upstream SHA mismatch")
    require(dist.version == UPSTREAM_VERSION, "mini-swe-agent version mismatch")
    for name, expected in (("litellm", LITELLM_VERSION), ("tiktoken", TIKTOKEN_VERSION)):
        require(importlib.metadata.version(name) == expected, f"{name} version mismatch")
    return {"mini_swe_agent": dist.version, "upstream_sha": UPSTREAM_SHA,
            "litellm": LITELLM_VERSION, "tiktoken": TIKTOKEN_VERSION}


def import_upstream(cache: Path):
    import minisweagent
    from minisweagent.agents.default import DefaultAgent
    from minisweagent.environments.local import LocalEnvironment
    from minisweagent.models.litellm_textbased_model import LitellmTextbasedModel
    dist = importlib.metadata.distribution("mini-swe-agent")
    package = Path(dist.locate_file("minisweagent")).resolve()
    require(minisweagent.__version__ == UPSTREAM_VERSION, "import version mismatch")
    require(package.is_relative_to(Path(sys.prefix).resolve()), "upstream package outside venv")
    for obj in (minisweagent, DefaultAgent, LitellmTextbasedModel, LocalEnvironment):
        require(Path(inspect.getfile(obj)).resolve().is_relative_to(package),
                "imported code outside pinned upstream package")
    require(os.environ.get("TIKTOKEN_CACHE_DIR") == str(cache.resolve()),
            "LiteLLM did not select the prepared tokenizer cache")
    return DefaultAgent, LocalEnvironment, LitellmTextbasedModel


def fixed_prompt() -> str:
    return (
        "Execute this task in exactly two turns. First, return exactly one "
        f"mswea_bash_command action with `{FIRST_COMMAND}`. Wait for the "
        "actual shell observation. Only after receiving that observation, "
        "return exactly one mswea_bash_command action with "
        f"`{SUBMIT_COMMAND}`. Do not use any other command, action block, "
        "tool, redirect, path, or shell syntax."
    )


def run_agent(*, mode: str, cache: Path, config: dict[str, Any] | None,
              key: str | None, secrets: list[str]) -> dict[str, Any]:
    import litellm

    DefaultAgent, LocalEnvironment, LitellmTextbasedModel = import_upstream(cache)
    work = Path(tempfile.mkdtemp(prefix="robotgen-gateway-agent-e2e-"))
    base_url = "gateway.invalid"
    port = 443
    model_kwargs: dict[str, Any] = {}
    model_name = "offline/gateway-agent-e2e"
    if mode == "live":
        assert config is not None and key is not None
        base_url = urlsplit(config["base_url"]).hostname or ""
        port = urlsplit(config["base_url"]).port or 443
        model_name = "openai/" + config["model"]
        request = config["request"]
        model_kwargs = {
            "api_base": config["base_url"].rstrip("/") + "/v1",
            "api_key": key,
            "timeout": request["timeout_s"],
            "max_retries": 0,
            "num_retries": 0,
            "stream": False,
        }
        for name in ("temperature", "top_p", "max_tokens", "seed"):
            if request.get(name) is not None:
                model_kwargs[name] = request[name]
        if request.get("extra_body"):
            model_kwargs["extra_body"] = request["extra_body"]

    controller = BoundaryController(work, base_url, port, secrets)
    sys.addaudithook(controller.audit)
    if mode == "live":
        controller.network_enabled = True
        controller.addresses.update(
            row[4][0] for row in socket.getaddrinfo(base_url, port, type=socket.SOCK_STREAM)
        )
    litellm.telemetry = False
    litellm.drop_params = False
    litellm.suppress_debug_info = True
    litellm.num_retries = 0
    litellm.num_retries_per_request = 0
    model = LitellmTextbasedModel(
        model_name=model_name,
        cost_tracking="ignore_errors",
        model_kwargs=model_kwargs,
    )
    require(model.config.action_regex == REGEX, "upstream action_regex was changed")
    env = LocalEnvironment(cwd=str(work), timeout=5)
    agent = DefaultAgent(
        model=model,
        env=env,
        system_template=f"RobotGen gateway agent E2E spike. {fixed_prompt()}",
        instance_template="{{task}}",
        step_limit=2,
        max_consecutive_format_errors=1,
        cost_limit=1.0,
        output_path=None,
    )
    evidence: dict[str, Any] = {
        "work_directory_is_temp": str(work).lower().startswith(str(Path(tempfile.gettempdir())).lower())
    }
    if mode == "offline":
        responses = [
            fixture_response(f"First execute the marker.\n\n```mswea_bash_command\n{FIRST_COMMAND}\n```"),
            fixture_response(f"Now submit.\n\n```mswea_bash_command\n{SUBMIT_COMMAND}\n```"),
        ]
        calls: list[dict[str, Any]] = []

        def completion_fixture(*positional: Any, **kwargs: Any):
            require(not positional, "unexpected positional completion arguments")
            calls.append(deepcopy(kwargs))
            require(len(calls) <= 2, "fixture completion called more than twice")
            return responses[len(calls) - 1]

        with patch("litellm.completion", side_effect=completion_fixture) as completion, \
                patch("litellm.cost_calculator.completion_cost", return_value=0.0) as cost_fixture:
            result = agent.run("Run the fixed marker and submit the result.")
        require(completion.call_count == 2 and cost_fixture.call_count == 2,
                "offline fixture call count mismatch")
        require(all("tools" not in call for call in calls), "native tools were passed")
        require(any(m.get("role") == "user" and m.get("content") == agent.messages[3]["content"]
                    for m in calls[1]["messages"]), "first observation did not enter second call")
        evidence["fixture_calls"] = 2
        evidence["fixture_status"] = "OFFLINE_SELF_TEST"
    else:
        result = agent.run("Run the fixed gateway marker and submit the result.")
    require(len(controller.launches) == 2, "expected exactly two real shell launches")
    require(controller.launches[0]["command"] == FIRST_COMMAND and
            controller.launches[1]["command"] == SUBMIT_COMMAND, "shell order mismatch")
    require([m["role"] for m in agent.messages] ==
            ["system", "user", "assistant", "user", "assistant", "exit"],
            "unexpected upstream message order")
    first, observation, second = agent.messages[2:5]
    require(first.get("extra", {}).get("actions") == [{"command": FIRST_COMMAND}],
            "first action mismatch")
    require(second.get("extra", {}).get("actions") == [{"command": SUBMIT_COMMAND}],
            "second action mismatch")
    require(observation.get("extra", {}).get("returncode") == 0 and
            observation.get("extra", {}).get("exception_info") == "", "shell observation failed")
    require(observation.get("extra", {}).get("raw_output") == "robotgen_gateway_agent_e2e\n",
            "first shell output mismatch")
    require(result.get("exit_status") == "Submitted" and result.get("submission") == SUBMISSION,
            "native submit result mismatch")
    require(agent.config.output_path is None, "trajectory persistence must be disabled")
    require(not controller.failed, "boundary was rejected")
    evidence.update({
        "real_shell_launches": len(controller.launches),
        "gateway_queries": 2 if mode == "live" else 0,
        "native_tools": False,
        "exit_status": result["exit_status"],
        "submission": result["submission"],
        "agent_calls": agent.n_calls,
        "forbidden_accesses": controller.unrelated_network_attempts,
        "local_runtime_ipc": controller.local_runtime_ipc_targets,
        "gateway_network_targets": controller.gateway_network_targets,
        "work_directory": str(work),
    })
    return evidence


def validate_live_config(path: Path) -> dict[str, Any]:
    """Validate the only accepted route before reading the designated key."""
    require(path.name.lower() != "api_config.json",
            "formal api_config.json is not an accepted live input")
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigBlocked("live config could not be read or parsed") from error
    require(isinstance(raw, dict), "live config must be an object")
    require(raw.get("schema_version") == "robot-model-api-config/0.1", "unsupported schema_version")
    require(raw.get("provider") == "smart_agi_gateway", "unsupported provider")
    require(raw.get("model") == "gpt-5.6-sol", "live model must be gpt-5.6-sol")
    require(raw.get("api_key") == "", "inline api_key must be empty")
    require(raw.get("api_key_env") == "SMART_AGI_API_KEY", "only SMART_AGI_API_KEY is accepted")
    require(raw.get("api_path") == "/v1/chat/completions", "unsupported api_path")
    require(raw.get("api_format") == "openai_chat_completions", "unsupported api_format")
    base = raw.get("base_url")
    parsed = urlsplit(base) if isinstance(base, str) else None
    require(parsed is not None and parsed.scheme == "https" and parsed.hostname == "big-model.smart-agi.com"
            and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
            and parsed.path in ("", "/"), "unsupported gateway base_url")
    request = raw.get("request")
    require(isinstance(request, dict), "request must be an object")
    require(set(request) <= {
        "stream", "timeout_s", "max_retries", "temperature", "top_p", "max_tokens",
        "seed", "extra_body",
    }, "request contains an out-of-scope override")
    require(request.get("stream") is False and request.get("max_retries") == 0,
            "stream/max_retries boundary rejected")
    timeout = request.get("timeout_s")
    require(type(timeout) in (int, float) and 0 < timeout < float("inf"), "invalid timeout_s")
    require(all(request.get(name) is None for name in ("temperature", "top_p", "max_tokens", "seed")),
            "request generation overrides are outside reviewed scope")
    require(request.get("extra_body") == {}, "request extra_body overrides are outside reviewed scope")
    return raw


def policy_unit_checks() -> None:
    """Exercise reject-before-OS behavior without starting a second shell."""
    controller = BoundaryController(Path(tempfile.mkdtemp(prefix="robotgen-policy-test-")), "gateway.invalid", 443, [SYNTHETIC_CREDENTIAL])
    fake = ("cmd.exe", 'cmd.exe /c "echo unauthorized"', str(controller.work), None)
    rejected = False
    try:
        controller.audit("subprocess.Popen", fake)
    except BoundaryAbort:
        rejected = True
    require(rejected and not controller.launches, "unauthorized command was not rejected before OS execution")
    network_rejected = False
    try:
        controller.audit("socket.connect", (object(), ("127.0.0.1", 9)))
    except BoundaryAbort:
        network_rejected = True
    require(network_rejected and not controller.launches, "post-rejection network/process stop failed")


def run_self_test(cache: Path) -> int:
    secrets = [SYNTHETIC_CREDENTIAL]
    scrub_environment()
    digest = check_cache(cache)
    # Avoid probing the host through a helper process before the process audit
    # boundary is installed.
    platform_value = sys.platform
    policy_unit_checks()
    # The audit hook is installed inside run_agent and cannot be removed.
    evidence = run_agent(mode="offline", cache=cache, config=None,
                         key=SYNTHETIC_CREDENTIAL, secrets=secrets)
    output = {
        "classification": "OFFLINE_SELF_TEST",
        "implementation": "PASS",
        "real_llm_api_calls": 0,
        "cache_sha256": digest,
        "python": sys.version,
        "platform": platform_value,
        **evidence,
        "credential_leak_check": SYNTHETIC_CREDENTIAL not in json.dumps(evidence),
    }
    require(output["credential_leak_check"], "synthetic credential leaked into summary")
    print(json.dumps(sanitize(output, secrets), ensure_ascii=True, indent=2))
    print("REAL GATEWAY E2E: NOT RUN")
    print("FINAL: OFFLINE_SELF_TEST PASS")
    return 0


def run_live(config_path: Path, cache: Path) -> int:
    secrets: list[str] = []
    config = validate_live_config(config_path)
    # Validate and hash the prepared cache before touching the designated key.
    digest = check_cache(cache)
    key = os.environ.get("SMART_AGI_API_KEY", "")
    require(key, "SMART_AGI_API_KEY is unavailable")
    secrets.append(key)
    scrub_environment()
    evidence = run_agent(mode="live", cache=cache, config=config, key=key, secrets=secrets)
    output = {
        "classification": "REAL_GATEWAY_E2E_PASS",
        "implementation": "PASS",
        "real_llm_api_calls": evidence.get("gateway_queries", 0),
        "model": "gpt-5.6-sol",
        "routed_model": "openai/gpt-5.6-sol",
        "cache_sha256": digest,
        **evidence,
    }
    print(json.dumps(sanitize(output, secrets), ensure_ascii=True, indent=2))
    print("FINAL: REAL_GATEWAY_E2E_PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--self-test", action="store_true")
    modes.add_argument("--live", action="store_true")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.self_test and args.config:
        parser.error("--self-test does not accept --config")
    if args.live and not args.config:
        parser.error("--live requires --config")
    try:
        if args.self_test:
            return run_self_test(args.cache)
        return run_live(args.config, args.cache)
    except ConfigBlocked as error:
        print(f"FINAL: CONFIG_BLOCKED ({type(error).__name__})")
        return EXIT["CONFIG_BLOCKED"]
    except BoundaryAbort:
        print("FINAL: ENVIRONMENT_BLOCKED (boundary rejected; no retry)")
        return EXIT["ENVIRONMENT_BLOCKED"]
    except (ImportError, OSError, importlib.metadata.PackageNotFoundError):
        print("FINAL: ENVIRONMENT_BLOCKED (reviewed environment unavailable)")
        return EXIT["ENVIRONMENT_BLOCKED"]
    except Exception as error:
        # Deliberately omit exception text: SDK errors can contain prompts/headers.
        print(f"FINAL: FAIL ({type(error).__name__})")
        return EXIT["FAIL"]


if __name__ == "__main__":
    raise SystemExit(main())
