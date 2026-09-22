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
import io
import importlib.metadata
import inspect
import json
import logging
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
import shutil
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from urllib.parse import urlsplit
from contextlib import redirect_stderr, redirect_stdout


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


class EnvironmentBlocked(Exception):
    pass


class RuntimeFailure(Exception):
    pass


class FormatMismatch(RuntimeFailure):
    pass


class EndpointFailed(RuntimeFailure):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ConfigBlocked(message)


def env_require(condition: bool, message: str) -> None:
    if not condition:
        raise EnvironmentBlocked(message)


def runtime_require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeFailure(message)


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
    if os.name == "nt":
        system_root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT")
        if not system_root:
            raise EnvironmentBlocked("SystemRoot is unavailable")
        os.environ["COMSPEC"] = str(Path(system_root) / "System32" / "cmd.exe")
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

    @staticmethod
    def _same_path(left: Any, right: Path) -> bool:
        try:
            return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(os.path.abspath(str(right)))
        except (OSError, TypeError):
            return False

    @staticmethod
    def _trusted_shell_path() -> Path:
        if os.name == "nt":
            root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT")
            if not root:
                raise EnvironmentBlocked("SystemRoot is unavailable")
            return Path(root) / "System32" / "cmd.exe"
        return Path("/bin/sh")

    def _abort(self, reason: str) -> None:
        self.failed = True
        raise BoundaryAbort(reason)

    def _process(self, values: tuple[Any, ...]) -> None:
        if self.failed:
            self._abort("process execution remains locked after rejection")
        if len(self.launches) >= 2 or len(values) < 4:
            self._abort("process execution limit or event shape rejected")
        executable, command, cwd, child_env = values[:4]
        trusted_shell = self._trusted_shell_path()
        if not self._same_path(executable, trusted_shell) or Path(str(cwd)).resolve() != self.work:
            self._abort("unexpected executable or cwd")
        expected = (FIRST_COMMAND, SUBMIT_COMMAND)[len(self.launches)]
        if os.name == "nt":
            exact_command = f'{trusted_shell} /c "{expected}"'
        else:
            exact_command = ["/bin/sh", "-c", expected]
        if command != exact_command:
            self._abort("command is outside the fixed echo allowlist")
        if not isinstance(child_env, dict):
            self._abort("child environment must be an explicit mapping")
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
        if self.failed and event == "socket.connect":
            # Preserve the reviewed CPython socketpair/asyncio IPC exception
            # for cleanup, while ordinary loopback and gateway traffic remain
            # rejected after the one-way lock.
            try:
                self._gateway_policy(event, values)
            except PermissionError as error:
                raise BoundaryAbort(str(error)) from None
            return
        if self.failed and event in {
            "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr",
            "socket.send", "socket.sendall", "socket.sendto", "socket.sendmsg",
            "http.client.connect", "http.client.send", "os.system", "os.exec",
            "os.posix_spawn",
        }:
            self._abort("network/process boundary remains locked after rejection")
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
    env_require(cache.is_dir(), "prepared cache directory is missing")
    item = cache / CACHE_NAME
    env_require(item.is_file(), "prepared tokenizer cache file is missing")
    digest = hashlib.sha256(item.read_bytes()).hexdigest()
    env_require(digest == CACHE_SHA, "prepared tokenizer cache SHA-256 mismatch")
    os.environ["CUSTOM_TIKTOKEN_CACHE_DIR"] = str(cache)
    return digest


def provenance() -> dict[str, str]:
    dist = importlib.metadata.distribution("mini-swe-agent")
    direct_url = json.loads(dist.read_text("direct_url.json") or "{}")
    env_require(direct_url.get("url") == UPSTREAM_URL, "mini-swe-agent upstream URL mismatch")
    env_require(direct_url.get("vcs_info", {}).get("commit_id") == UPSTREAM_SHA,
                "mini-swe-agent upstream SHA mismatch")
    env_require(dist.version == UPSTREAM_VERSION, "mini-swe-agent version mismatch")
    for name, expected in (("litellm", LITELLM_VERSION), ("tiktoken", TIKTOKEN_VERSION)):
        env_require(importlib.metadata.version(name) == expected, f"{name} version mismatch")
    return {"mini_swe_agent": dist.version, "upstream_sha": UPSTREAM_SHA,
            "litellm": LITELLM_VERSION, "tiktoken": TIKTOKEN_VERSION}


def import_upstream(cache: Path):
    import minisweagent
    from minisweagent.agents.default import DefaultAgent
    from minisweagent.environments.local import LocalEnvironment
    from minisweagent.models.litellm_textbased_model import LitellmTextbasedModel
    dist = importlib.metadata.distribution("mini-swe-agent")
    package = Path(dist.locate_file("minisweagent")).resolve()
    env_require(minisweagent.__version__ == UPSTREAM_VERSION, "import version mismatch")
    env_require(package.is_relative_to(Path(sys.prefix).resolve()), "upstream package outside venv")
    for obj in (minisweagent, DefaultAgent, LitellmTextbasedModel, LocalEnvironment):
        env_require(Path(inspect.getfile(obj)).resolve().is_relative_to(package),
                    "imported code outside pinned upstream package")
    env_require(os.environ.get("TIKTOKEN_CACHE_DIR") == str(cache.resolve()),
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
    work = Path(tempfile.mkdtemp(prefix="robotgen-gateway-agent-e2e-"))
    global_config = work / "global-config"
    global_config.mkdir()
    os.environ["MSWEA_GLOBAL_CONFIG_DIR"] = str(global_config)
    base_url = "gateway.invalid"
    port = 443
    model_kwargs: dict[str, Any] = {}
    model_name = "offline/gateway-agent-e2e"
    if mode == "live":
        runtime_require(config is not None and key is not None, "live model inputs are incomplete")
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
    else:
        model_kwargs = {
            "api_base": "https://gateway.invalid/v1",
            "api_key": key or SYNTHETIC_CREDENTIAL,
            "timeout": 5,
            "max_retries": 0,
            "num_retries": 0,
            "stream": False,
        }

    controller = BoundaryController(work, base_url, port, secrets)
    sys.addaudithook(controller.audit)
    # Imports happen only after the fail-closed audit hook is installed.
    import litellm
    DefaultAgent, LocalEnvironment, LitellmTextbasedModel = import_upstream(cache)
    from minisweagent.exceptions import FormatError
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
    runtime_require(model.config.action_regex == REGEX, "upstream action_regex was changed")
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
    query_observation = {"calls": 0}

    def observe_query(frame: Any, event: str, value: Any) -> None:
        if event == "call" and frame.f_code is LitellmTextbasedModel._query.__code__:
            query_observation["calls"] += 1

    previous_profile = sys.getprofile()
    sys.setprofile(observe_query)
    try:
        if mode == "offline":
            responses = [
                fixture_response(f"First execute the marker.\n\n```mswea_bash_command\n{FIRST_COMMAND}\n```"),
                fixture_response(f"Now submit.\n\n```mswea_bash_command\n{SUBMIT_COMMAND}\n```"),
            ]
            calls: list[dict[str, Any]] = []

            def completion_fixture(*positional: Any, **kwargs: Any):
                runtime_require(not positional, "unexpected positional completion arguments")
                calls.append(deepcopy(kwargs))
                runtime_require(len(calls) <= 2, "fixture completion called more than twice")
                return responses[len(calls) - 1]

            try:
                with patch("litellm.completion", side_effect=completion_fixture) as completion, \
                        patch("litellm.cost_calculator.completion_cost", return_value=0.0) as cost_fixture:
                    result = agent.run("Run the fixed marker and submit the result.")
            except FormatError:
                raise FormatMismatch("upstream format error") from None
            runtime_require(completion.call_count == 2 and cost_fixture.call_count == 2,
                            "offline fixture call count mismatch")
            runtime_require(all("tools" not in call for call in calls), "native tools were passed")
            runtime_require(any(m.get("role") == "user" and m.get("content") == agent.messages[3]["content"]
                                for m in calls[1]["messages"]),
                            "first observation did not enter second call")
            evidence["fixture_calls"] = len(calls)
            evidence["cost_fixture_calls"] = cost_fixture.call_count
            evidence["fixture_status"] = "OFFLINE_SELF_TEST"
            evidence["native_tools_observed"] = {
                "observed": True,
                "present": any("tools" in call for call in calls),
            }
            evidence["completion_kwargs_observed"] = True
        else:
            try:
                result = agent.run("Run the fixed gateway marker and submit the result.")
            except BoundaryAbort:
                raise
            except FormatError:
                raise FormatMismatch("upstream format error") from None
            except Exception as error:
                raise EndpointFailed(type(error).__name__) from None
            evidence["native_tools_observed"] = {
                "observed": False,
                "present": "not_observed",
            }
            evidence["completion_kwargs_observed"] = False
    finally:
        sys.setprofile(previous_profile)
    if getattr(agent, "n_consecutive_format_errors", 0):
        raise FormatMismatch("repeated upstream format error")
    runtime_require(query_observation["calls"] == 2,
                    "successful path did not make exactly two model queries")
    runtime_require(len(controller.launches) == 2, "expected exactly two real shell launches")
    runtime_require(controller.launches[0]["command"] == FIRST_COMMAND and
                    controller.launches[1]["command"] == SUBMIT_COMMAND, "shell order mismatch")
    runtime_require([m["role"] for m in agent.messages] ==
                    ["system", "user", "assistant", "user", "assistant", "exit"],
                    "unexpected upstream message order")
    first, observation, second = agent.messages[2:5]
    runtime_require(first.get("extra", {}).get("actions") == [{"command": FIRST_COMMAND}],
                    "first action mismatch")
    runtime_require(second.get("extra", {}).get("actions") == [{"command": SUBMIT_COMMAND}],
                    "second action mismatch")
    runtime_require(observation.get("extra", {}).get("returncode") == 0 and
                    observation.get("extra", {}).get("exception_info") == "", "shell observation failed")
    runtime_require(observation.get("extra", {}).get("raw_output") == "robotgen_gateway_agent_e2e\n",
                    "first shell output mismatch")
    runtime_require(result.get("exit_status") == "Submitted" and result.get("submission") == SUBMISSION,
                    "native submit result mismatch")
    runtime_require(agent.config.output_path is None, "trajectory persistence must be disabled")
    runtime_require(not controller.failed, "boundary was rejected")
    evidence.update({
        "real_shell_launches": len(controller.launches),
        "model_query_calls": query_observation["calls"],
        "gateway_queries": query_observation["calls"] if mode == "live" else 0,
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
        lexical = path.absolute()
        resolved = path.resolve(strict=True)
        temp_root = Path(tempfile.gettempdir()).resolve()
    except OSError as error:
        raise ConfigBlocked("live config path is unavailable") from error
    require(not path.is_symlink() and lexical == resolved,
            "live config symlink aliases are not accepted")
    require(resolved.is_file() and resolved.is_relative_to(temp_root),
            "live config must be a regular file directly under system temp")
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8-sig"))
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
            and parsed.port in (None, 443)
            and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
            and parsed.path in ("", "/"), "unsupported gateway base_url")
    request = raw.get("request")
    require(isinstance(request, dict), "request must be an object")
    require(set(request) <= {
        "stream", "timeout_s", "max_retries", "temperature", "top_p", "max_tokens",
        "seed", "extra_body",
    }, "request contains an out-of-scope override")
    require(request.get("stream") is False and type(request.get("max_retries")) is int
            and request.get("max_retries") == 0,
            "stream/max_retries boundary rejected")
    timeout = request.get("timeout_s")
    require(type(timeout) in (int, float) and type(timeout) is not bool
            and 0 < timeout < float("inf"), "invalid timeout_s")
    require(all(request.get(name) is None for name in ("temperature", "top_p", "max_tokens", "seed")),
            "request generation overrides are outside reviewed scope")
    require(request.get("extra_body") == {}, "request extra_body overrides are outside reviewed scope")
    return raw


def quiet_call(function: Any, *args: Any, **kwargs: Any) -> tuple[Any, str]:
    """Run upstream while discarding all stdout/stderr and logging output."""
    capture = io.StringIO()
    previous_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with redirect_stdout(capture), redirect_stderr(capture):
            result = function(*args, **kwargs)
        return result, capture.getvalue()
    finally:
        capture.close()
        logging.disable(previous_disable)


def files_under(work_directory: str) -> list[str]:
    root = Path(work_directory).resolve()
    runtime_require(root.is_relative_to(Path(tempfile.gettempdir()).resolve()),
                    "evidence directory escaped system temp")
    contents: list[str] = []
    for item in root.rglob("*"):
        if item.is_file():
            contents.append(item.read_bytes().decode("utf-8", errors="replace"))
    return contents


def synthetic_config_checks() -> dict[str, str]:
    root = Path(tempfile.mkdtemp(prefix="robotgen-synthetic-config-"))
    base = {
        "schema_version": "robot-model-api-config/0.1",
        "provider": "smart_agi_gateway",
        "model": "gpt-5.6-sol",
        "api_key": "",
        "api_key_env": "SMART_AGI_API_KEY",
        "api_path": "/v1/chat/completions",
        "api_format": "openai_chat_completions",
        "base_url": "https://big-model.smart-agi.com",
        "request": {
            "stream": False, "timeout_s": 5, "max_retries": 0,
            "temperature": None, "top_p": None, "max_tokens": None,
            "seed": None, "extra_body": {},
        },
    }
    cases = {
        "wrong_model": {**base, "model": "glm-5.3"},
        "inline_credential": {**base, "api_key": SYNTHETIC_CREDENTIAL},
        "request_override": {**base, "request": {**base["request"], "extra_body": {"model": "other"}}},
    }
    results: dict[str, str] = {}
    try:
        for name, config in cases.items():
            path = root / f"{name}.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            try:
                validate_live_config(path)
            except ConfigBlocked:
                results[name] = "rejected_before_key_read"
            else:
                raise RuntimeFailure(f"synthetic config case was accepted: {name}")
        return results
    finally:
        shutil.rmtree(root, ignore_errors=True)


def policy_unit_checks() -> dict[str, str]:
    """Exercise reject-before-OS behavior without starting a second shell."""
    def fresh() -> BoundaryController:
        return BoundaryController(
            Path(tempfile.mkdtemp(prefix="robotgen-policy-test-")),
            "gateway.invalid", 443, [SYNTHETIC_CREDENTIAL],
        )

    def trusted_command(controller: BoundaryController, command: str = FIRST_COMMAND,
                        cwd: Path | None = None, child_env: dict[str, str] | None = None) -> tuple[Any, ...]:
        shell = controller._trusted_shell_path()
        exact = f'{shell} /c "{command}"' if os.name == "nt" else ["/bin/sh", "-c", command]
        clean_env = {"PATH": os.environ.get("PATH", "")}
        if os.name == "nt":
            clean_env["COMSPEC"] = os.environ.get("COMSPEC", "")
        return shell, exact, str(cwd or controller.work), child_env if child_env is not None else clean_env

    def expect_reject(name: str, controller: BoundaryController, event: str, values: tuple[Any, ...]) -> None:
        before = len(controller.launches)
        try:
            controller.audit(event, values)
        except BoundaryAbort:
            pass
        else:
            raise RuntimeFailure(f"regression case was accepted: {name}")
        runtime_require(len(controller.launches) == before,
                        f"regression case launched a process: {name}")

    cases: dict[str, str] = {}
    controller = fresh()
    expect_reject("illegal command", controller,
                  "subprocess.Popen", (*trusted_command(controller, "echo unauthorized"),))
    cases["illegal_command"] = "rejected_before_os"
    expect_reject("legal first command after rejection", controller,
                  "subprocess.Popen", trusted_command(controller))
    cases["post_rejection_process_lock"] = "rejected"
    controller.network_enabled = True
    controller.addresses.add("198.51.100.7")
    expect_reject("gateway network after rejection", controller,
                  "socket.connect", (object(), ("198.51.100.7", 443)))
    cases["post_rejection_gateway_network_lock"] = "rejected"
    expect_reject("ordinary loopback after rejection", controller,
                  "socket.connect", (object(), ("127.0.0.1", 9)))
    cases["post_rejection_loopback_network_lock"] = "rejected"

    controller = fresh()
    bad_executable = Path(tempfile.gettempdir()) / "not-the-system-shell.exe"
    shell, exact, cwd, env = trusted_command(controller)
    expect_reject("wrong executable", controller, "subprocess.Popen",
                  (bad_executable, exact, cwd, env))
    cases["wrong_executable"] = "rejected"

    controller = fresh()
    shell, exact, cwd, _ = trusted_command(controller)
    expect_reject("child_env None", controller, "subprocess.Popen",
                  (shell, exact, cwd, None))
    cases["child_env_none"] = "rejected"

    controller = fresh()
    shell, exact, _, env = trusted_command(controller)
    expect_reject("wrong cwd", controller, "subprocess.Popen",
                  (shell, exact, str(Path(tempfile.gettempdir())), env))
    cases["wrong_cwd"] = "rejected"

    controller = fresh()
    shell, _, cwd, env = trusted_command(controller)
    submit_exact = f'{shell} /c "{SUBMIT_COMMAND}"' if os.name == "nt" else ["/bin/sh", "-c", SUBMIT_COMMAND]
    expect_reject("wrong order", controller, "subprocess.Popen", (shell, submit_exact, cwd, env))
    cases["wrong_order"] = "rejected"

    controller = fresh()
    shell, exact, cwd, env = trusted_command(controller)
    controller.audit("subprocess.Popen", (shell, exact, cwd, env))
    shell, exact, cwd, env = trusted_command(controller, SUBMIT_COMMAND)
    controller.audit("subprocess.Popen", (shell, exact, cwd, env))
    expect_reject("third execution", controller, "subprocess.Popen", (shell, exact, cwd, env))
    cases["third_execution"] = "rejected"

    controller = fresh()
    shell, exact, cwd, env = trusted_command(controller)
    env["PATH"] = SYNTHETIC_CREDENTIAL
    expect_reject("synthetic credential in child env", controller,
                  "subprocess.Popen", (shell, exact, cwd, env))
    cases["synthetic_child_credential"] = "rejected"
    return cases


def run_self_test(cache: Path) -> int:
    secrets = [SYNTHETIC_CREDENTIAL]
    scrub_environment()
    provenance_info = provenance()
    digest = check_cache(cache)
    # Avoid probing the host through a helper process before the process audit
    # boundary is installed.
    platform_value = sys.platform
    rejection_cases = policy_unit_checks()
    config_rejection_cases = synthetic_config_checks()
    # The audit hook is installed inside run_agent and cannot be removed.
    evidence, captured = quiet_call(
        run_agent, mode="offline", cache=cache, config=None,
        key=SYNTHETIC_CREDENTIAL, secrets=secrets,
    )
    generated_files = files_under(evidence["work_directory"])
    evidence["rejection_cases"] = rejection_cases
    evidence["synthetic_config_rejection_cases"] = config_rejection_cases
    evidence["startup_provenance"] = provenance_info
    output = {
        "classification": "OFFLINE_SELF_TEST",
        "implementation": "PASS",
        "real_llm_api_calls": 0,
        "cache_sha256": digest,
        "python": sys.version,
        "platform": platform_value,
        **evidence,
        "credential_leak_check": (
            SYNTHETIC_CREDENTIAL not in captured
            and SYNTHETIC_CREDENTIAL not in json.dumps(evidence)
            and all(SYNTHETIC_CREDENTIAL not in content for content in generated_files)
        ),
    }
    runtime_require(output["credential_leak_check"], "synthetic credential leaked into output or temp files")
    print(json.dumps(sanitize(output, secrets), ensure_ascii=True, indent=2))
    print("REAL GATEWAY E2E: NOT RUN")
    print("FINAL: OFFLINE_SELF_TEST PASS")
    return 0


def run_live(config_path: Path, cache: Path) -> int:
    secrets: list[str] = []
    config = validate_live_config(config_path)
    provenance_info = provenance()
    # Validate and hash the prepared cache before touching the designated key.
    digest = check_cache(cache)
    key = os.environ.get("SMART_AGI_API_KEY", "")
    require(key, "SMART_AGI_API_KEY is unavailable")
    secrets.append(key)
    scrub_environment()
    evidence, _captured = quiet_call(
        run_agent, mode="live", cache=cache, config=config, key=key, secrets=secrets,
    )
    output = {
        "classification": "REAL_GATEWAY_E2E_PASS",
        "implementation": "PASS",
        "real_llm_api_calls": evidence.get("gateway_queries", 0),
        "model": "gpt-5.6-sol",
        "routed_model": "openai/gpt-5.6-sol",
        "cache_sha256": digest,
        "startup_provenance": provenance_info,
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
    except EnvironmentBlocked as error:
        print(f"FINAL: ENVIRONMENT_BLOCKED ({type(error).__name__})")
        return EXIT["ENVIRONMENT_BLOCKED"]
    except BoundaryAbort:
        print("FINAL: ENVIRONMENT_BLOCKED (boundary rejected; no retry)")
        return EXIT["ENVIRONMENT_BLOCKED"]
    except FormatMismatch as error:
        print(f"FINAL: FORMAT_MISMATCH ({type(error).__name__})")
        return EXIT["FORMAT_MISMATCH"]
    except EndpointFailed as error:
        print(f"FINAL: ENDPOINT_FAILED ({type(error).__name__})")
        return EXIT["ENDPOINT_FAILED"]
    except RuntimeFailure as error:
        print(f"FINAL: FAIL ({type(error).__name__})")
        return EXIT["FAIL"]
    except (ImportError, OSError, importlib.metadata.PackageNotFoundError):
        print("FINAL: ENVIRONMENT_BLOCKED (reviewed environment unavailable)")
        return EXIT["ENVIRONMENT_BLOCKED"]
    except Exception as error:
        # Deliberately omit exception text: SDK errors can contain prompts/headers.
        print(f"FINAL: FAIL ({type(error).__name__})")
        return EXIT["FAIL"]


if __name__ == "__main__":
    raise SystemExit(main())
