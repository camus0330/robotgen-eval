"""Probe one real upstream text-action loop with only the completion/cost boundaries patched."""

import argparse
from copy import deepcopy
import hashlib
import importlib.metadata
import inspect
import json
import math
import os
from pathlib import Path
import platform
import sys
import tempfile
import traceback
from types import SimpleNamespace
from unittest.mock import patch


UPSTREAM_SHA = "04d809ceab9df28f9adaed044884180159172930"
CACHE_NAME = "9b5ad71b2ce5302211f9c61530b329a4922fc6a4"
CACHE_SHA = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
REGEX = r"```mswea_bash_command\s*\n(.*?)\n```"
FIRST_COMMAND = "echo robotgen_text_e2e"
SUBMIT_COMMAND = "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT&&echo robotgen_text_submission"
SUBMISSION = "robotgen_text_submission\n"


def check(condition, description):
    if not condition:
        raise AssertionError(description)


def fixture_response(content):
    # Serialization shape only: no actions, parsing, observation or execution logic.
    message = {"role": "assistant", "content": content}
    payload = {"choices": [{"message": message, "finish_reason": "stop"}]}
    return SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content=content, model_dump=lambda **kwargs: deepcopy(message)),
            finish_reason="stop",
        )],
        model_dump=lambda **kwargs: deepcopy(payload),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", required=True, type=Path)
    args = parser.parse_args()
    # LocalEnvironment inherits the environment and exposes it to templates.
    # Delete by name only; never inspect discarded API keys or other config values.
    allowed = {"PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP"}
    for name in tuple(os.environ):
        if name.upper() not in allowed:
            del os.environ[name]
    work = Path(tempfile.mkdtemp(prefix="robotgen-text-e2e-"))
    os.environ.update({
        "MSWEA_GLOBAL_CONFIG_DIR": str(work / "empty-global-config"),
        "MSWEA_SILENT_STARTUP": "1", "PYTHON_DOTENV_DISABLED": "1",
        "LITELLM_MODE": "PRODUCTION", "LITELLM_LOCAL_MODEL_COST_MAP": "True",
    })
    print(f"Python={sys.version}; platform={platform.platform()}; machine={platform.machine()}")
    print(f"executable={sys.executable}; pid={os.getpid()}; evidence directory={work}")
    network_events = {
        "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr", "socket.connect",
        "socket.send", "socket.sendall", "socket.sendto", "socket.sendmsg",
        "http.client.connect", "http.client.send",
    }
    blocked, launches = [], []

    def audit(event, values):
        forbidden = event in network_events
        if event == "open" and isinstance(values[0], (str, os.PathLike)):
            forbidden = Path(values[0]).name.lower() in {".env", "api_config.json"}
        if event == "subprocess.Popen":
            # Observe real LocalEnvironment launches without replacing its implementation.
            executable, command, cwd, _ = values
            launches.append({"executable": executable, "command": command, "cwd": cwd})
            expected = (FIRST_COMMAND, SUBMIT_COMMAND)
            permitted = len(launches) <= 2 and Path(cwd).resolve() == work
            if permitted:
                action = expected[len(launches) - 1]
                if os.name == "nt":
                    permitted = command == f'{executable} /c "{action}"'
                else:
                    permitted = command == ["/bin/sh", "-c", action]
            forbidden = not permitted
        if forbidden:
            blocked.append(event)
            raise PermissionError(f"Offline text-e2e boundary rejected {event}")

    sys.addaudithook(audit)
    agent = None
    code = 0
    try:
        cache = args.cache.resolve()
        if not cache.is_dir() or not (cache / CACHE_NAME).is_file():
            raise FileNotFoundError(f"Prepared tokenizer cache missing: {cache}")
        digest = hashlib.sha256((cache / CACHE_NAME).read_bytes()).hexdigest()
        check(digest == CACHE_SHA, "prepared cache SHA-256 mismatch")
        os.environ["CUSTOM_TIKTOKEN_CACHE_DIR"] = str(cache)
        print(f"prepared cache={cache}; sha256={digest}")
        dist = importlib.metadata.distribution("mini-swe-agent")
        origin = json.loads(dist.read_text("direct_url.json") or "{}")
        check(origin.get("url") == "https://github.com/SWE-agent/mini-swe-agent.git", "unexpected upstream")
        check(origin.get("vcs_info", {}).get("commit_id") == UPSTREAM_SHA, "upstream SHA mismatch")
        check(dist.version == "2.4.6", "mini-swe version mismatch")
        print(f"direct_url={json.dumps(origin)}; mini-swe-agent={dist.version}")
        for name, version in (("litellm", "1.102.0"), ("tiktoken", "0.14.0")):
            actual = importlib.metadata.version(name)
            check(actual == version, f"{name} differs from the reviewed environment")
            print(f"{name}={actual}")

        import minisweagent
        from minisweagent.agents.default import DefaultAgent
        from minisweagent.environments.local import LocalEnvironment
        from minisweagent.models.litellm_textbased_model import LitellmTextbasedModel

        check(minisweagent.__version__ == "2.4.6", "import version mismatch")
        package = Path(dist.locate_file("minisweagent")).resolve()
        check(package.is_relative_to(Path(sys.prefix).resolve()), "package outside virtualenv")
        for obj in (minisweagent, DefaultAgent, LitellmTextbasedModel, LocalEnvironment):
            source = Path(inspect.getfile(obj)).resolve()
            check(source.is_relative_to(package), "import outside pinned distribution")
            print(f"source[{obj.__name__}]={source}")
        if blocked:
            raise PermissionError("Import suppressed a forbidden-access exception")
        model = LitellmTextbasedModel(model_name="robotgen/offline-text-e2e")
        check(model.config.action_regex == REGEX, "default action_regex changed")
        check(os.environ.get("TIKTOKEN_CACHE_DIR") == str(cache), "LiteLLM did not select prepared cache")
        responses = [
            fixture_response(f"First execute the marker.\n\n```mswea_bash_command\n{FIRST_COMMAND}\n```"),
            fixture_response(f"Now submit.\n\n```mswea_bash_command\n{SUBMIT_COMMAND}\n```"),
        ]
        for response in responses:
            check("extra" not in response.choices[0].message.model_dump(), "fixture must not supply actions")
        snapshots = []

        def completion_fixture(*positional, **kwargs):
            check(not positional, "unexpected positional completion arguments")
            snapshots.append(deepcopy(kwargs))  # Preserve the actual context at call time.
            return responses[len(snapshots) - 1]

        agent = DefaultAgent(
            model=model, env=LocalEnvironment(cwd=str(work)),
            system_template="Offline RobotGen text-path integration smoke.",
            instance_template="{{task}}", step_limit=4, cost_limit=1.0,
            output_path=work / "native.traj.json",
        )
        with patch("litellm.completion", side_effect=completion_fixture) as completion, \
                patch("litellm.cost_calculator.completion_cost", return_value=0.001) as cost_fixture:
            result = agent.run("Run the offline text-path marker and submit.")
            check(completion.call_count == 2 and agent.n_calls == 2, "exactly two model calls required")
            check(len(snapshots) == 2, "completion context snapshots")
            for index, call in enumerate(completion.call_args_list):
                check("tools" not in call.kwargs and "tools" not in snapshots[index], "native tools unexpectedly supplied")
                check(call.kwargs == snapshots[index], "completion arguments changed after call")
                print(f"completion {index + 1} kwargs keys={sorted(call.kwargs)}; tools present=False")
            check(cost_fixture.call_count == 2, "real query must perform cost accounting twice")
            for index, call in enumerate(cost_fixture.call_args_list):
                check(call.args[0] is responses[index], "cost fixture must receive actual response")
                check(call.kwargs["model"] == model.config.model_name, "cost model name")
        if blocked:
            raise PermissionError("Runtime attempted forbidden access")
        check(len(launches) == 2, "expected two real LocalEnvironment shell launches")
        check([m["role"] for m in agent.messages] == ["system", "user", "assistant", "user", "assistant", "exit"], "message order")
        first, observation, second = agent.messages[2:5]
        check(first["extra"]["actions"] == [{"command": FIRST_COMMAND}], "first parsed action")
        check(second["extra"]["actions"] == [{"command": SUBMIT_COMMAND}], "second parsed action")
        check(observation["extra"]["returncode"] == 0 and observation["extra"]["exception_info"] == "", "real command failed")
        check(observation["extra"]["raw_output"] == "robotgen_text_e2e\n", "real raw output")
        check("robotgen_text_e2e" in observation["content"], "formatted observation missing marker")
        check(any(m["role"] == "user" and m["content"] == observation["content"] for m in snapshots[1]["messages"]), "second call lacks actual observation")
        check(result["exit_status"] == "Submitted" and result["submission"] == SUBMISSION, "submission contract")
        check(agent.messages[-1]["content"] == SUBMISSION, "final exit content")
        check(math.isclose(agent.cost, 0.002, rel_tol=0, abs_tol=1e-12), "agent cost accumulation")
        for index, message in enumerate((first, second)):
            check(message["extra"]["response"] == responses[index].model_dump(), "persisted response payload")
            check(message["extra"]["cost"] == 0.001, "per-response cost")
        trajectory = json.loads(agent.config.output_path.read_text(encoding="utf-8"))
        check(trajectory["trajectory_format"] == "mini-swe-agent-1.1", "native trajectory format")
        check(trajectory["info"]["exit_status"] == "Submitted", "saved exit status")
        check(trajectory["info"]["submission"] == SUBMISSION, "saved submission")
        check(trajectory["info"]["model_stats"] == {"api_calls": 2, "instance_cost": agent.cost}, "saved model stats")
        check(trajectory["messages"] == agent.messages, "saved actions/observations/responses/exit")
        for key, value in {
            "agent_type": "minisweagent.agents.default.DefaultAgent",
            "model_type": "minisweagent.models.litellm_textbased_model.LitellmTextbasedModel",
            "environment_type": "minisweagent.environments.local.LocalEnvironment",
        }.items():
            check(trajectory["info"]["config"][key] == value, f"native trajectory {key}")
        print("completion calls=2; native tools passed to completion=False")
        print(f"first parsed action=PASS {first['extra']['actions']}")
        print(f"real observation=PASS raw_output={observation['extra']['raw_output']!r}; returncode=0")
        print(f"observation content={observation['content']!r}")
        print("second call contains observation=PASS")
        print(f"exit_status={result['exit_status']}; submission={result['submission']!r}")
        print(f"agent.n_calls={agent.n_calls}; agent.cost={agent.cost}; completion_cost calls=2")
        print(f"trajectory=PASS; path={agent.config.output_path}")
    except Exception as error:
        traceback.print_exc()
        environment_error = agent and any(m.get("extra", {}).get("exception_info") for m in agent.messages)
        code = 2 if blocked or environment_error or isinstance(error, (ImportError, OSError)) else 1
        print(f"native trajectory, if saved: {work / 'native.traj.json'}")
    print(f"real subprocess launches={json.dumps(launches)}")
    print(f"forbidden accesses={json.dumps(blocked)}")
    print(f"forbidden network attempt count={sum(event in network_events for event in blocked)}")
    print(f"FINAL: { {0: 'PASS', 1: 'FAIL', 2: 'ENVIRONMENT_BLOCKED'}[code] }")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
