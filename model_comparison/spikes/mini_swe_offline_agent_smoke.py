"""Probe pinned upstream primitives with parsed deterministic actions, never an LLM."""

import importlib.metadata
import inspect
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import traceback


UPSTREAM = "https://github.com/SWE-agent/mini-swe-agent.git"
UPSTREAM_SHA = "04d809ceab9df28f9adaed044884180159172930"
VERSION = "2.4.6"
MARKER = "robotgen_offline_smoke"
SUBMISSION = "robotgen_offline_submission"
FIRST_COMMAND = f"echo {MARKER}"
SUBMIT_COMMAND = f"echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT&&echo {SUBMISSION}"


def check(condition, description):
    if not condition:
        raise AssertionError(description)


def check_trajectory(path, agent, calls, exit_status):
    data = json.loads(path.read_text(encoding="utf-8"))
    check(data["trajectory_format"] == "mini-swe-agent-1.1", "trajectory format")
    check(data["info"]["mini_version"] == VERSION, "trajectory mini version")
    check(data["info"]["model_stats"]["api_calls"] == calls, "trajectory calls")
    check(data["info"]["exit_status"] == exit_status, "trajectory exit status")
    check(data["messages"] == agent.messages, "all messages saved unchanged")
    config = data["info"]["config"]
    check(config["model"]["model_name"] == "deterministic", "model config")
    check(config["model"]["outputs"] == agent.model.config.outputs, "model outputs saved")
    check(config["environment"]["cwd"] == agent.env.config.cwd, "environment config")
    check(config["agent_type"] == "minisweagent.agents.default.DefaultAgent", "real agent")
    check(config["model_type"] == "minisweagent.models.test_models.DeterministicModel", "real model")
    check(config["environment_type"] == "minisweagent.environments.local.LocalEnvironment", "real environment")
    print(f"trajectory={path}")
    print(f"trajectory_format={data['trajectory_format']}; api_calls={calls}; exit_status={exit_status}")
    print("trajectory messages/model config/environment config: PASS")
    return data


def main():
    # Inspect variable NAMES only, deleting unneeded entries without reading their values.
    # LocalEnvironment exposes os.environ to templates and inherits it in shell commands.
    allowed = {"PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP", "HOME"}
    for name in tuple(os.environ):
        if name.upper() not in allowed:
            del os.environ[name]
    work = Path(tempfile.mkdtemp(prefix="robotgen-mini-swe-smoke-"))
    # This fresh directory has no .env; upstream must not load the user's global config.
    os.environ["MSWEA_GLOBAL_CONFIG_DIR"] = str(work / "empty-global-config")
    os.environ["MSWEA_SILENT_STARTUP"] = "1"
    print(f"Python={sys.version}")
    print(f"platform={platform.platform()}; machine={platform.machine()}")
    print(f"executable={sys.executable}")
    print(f"temporary evidence directory={work}")

    try:
        dist = importlib.metadata.distribution("mini-swe-agent")
        direct_url = json.loads(dist.read_text("direct_url.json") or "{}")
        check(direct_url.get("url") == UPSTREAM, "requires the fixed upstream VCS installation")
        check(direct_url.get("vcs_info", {}).get("commit_id") == UPSTREAM_SHA, "upstream SHA mismatch")
        check(dist.version == VERSION, "distribution version mismatch")

        import minisweagent
        from minisweagent.agents.default import DefaultAgent
        from minisweagent.environments.local import LocalEnvironment
        from minisweagent.models.test_models import DeterministicModel, make_output

        check(minisweagent.__version__ == VERSION, "imported mini-swe version mismatch")
        package = Path(dist.locate_file("minisweagent")).resolve()
        check(package.is_relative_to(Path(sys.prefix).resolve()), "package outside this virtualenv")
        for obj in (minisweagent, DefaultAgent, DeterministicModel, make_output, LocalEnvironment):
            source = Path(inspect.getfile(obj)).resolve()
            check(source.is_relative_to(package), "imported code outside pinned distribution")
            print(f"source[{obj.__name__}]={source}")
        print(f"minisweagent.__version__={minisweagent.__version__}")
        print(f"install source={direct_url['url']}@{direct_url['vcs_info']['commit_id']}")
        for name in ("pip", "pydantic", "jinja2", "python-dotenv", "platformdirs", "rich", "litellm", "openai", "tenacity"):
            print(f"installed dependency: {name}=={importlib.metadata.version(name)}")
    except Exception as exc:
        status = "ENVIRONMENT_BLOCKED" if isinstance(exc, (ImportError, OSError, importlib.metadata.PackageNotFoundError)) else "FAIL"
        traceback.print_exc()
        print(f"Scenario A: {status} (installation/import precondition failed)")
        print(f"Scenario B: {status} (installation/import precondition failed)")
        print(f"FINAL: {status}")
        return 2 if status == "ENVIRONMENT_BLOCKED" else 1

    results = []
    # These are two independent test scenarios, not an agent/tool execution loop.
    for scenario in ("A", "B"):
        folder = work / scenario
        folder.mkdir()
        agent = None
        try:
            if scenario == "A":
                outputs = [
                    make_output("Run the offline marker command.", [{"command": FIRST_COMMAND}], cost=0),
                    make_output("Submit the deterministic result.", [{"command": SUBMIT_COMMAND}], cost=0),
                ]
            else:
                outputs = [
                    make_output("First limited response.", [{"command": "echo robotgen_step_one"}], cost=0),
                    make_output("Second response must remain unconsumed.", [{"command": "echo robotgen_step_two"}], cost=0),
                ]
            model = DeterministicModel(outputs=outputs, cost_per_call=0)
            agent = DefaultAgent(
                model=model,
                env=LocalEnvironment(cwd=str(folder)),
                system_template="Offline deterministic framework smoke; no robot task.",
                instance_template="{{task}}",
                step_limit=1 if scenario == "B" else 0,
                cost_limit=0,
                output_path=folder / "native.traj.json",
            )
            task = f"Run offline scenario {scenario}."
            result = agent.run(task)
            expected_exit = "Submitted" if scenario == "A" else "LimitsExceeded"
            calls = 2 if scenario == "A" else 1
            check(result["exit_status"] == expected_exit, "unexpected exit status")
            check(agent.n_calls == calls, "unexpected model call count")
            check(model.current_index == calls - 1, "unexpected consumed response count")
            expected_roles = ["system", "user", "assistant", "user"]
            expected_roles += ["assistant", "exit"] if scenario == "A" else ["exit"]
            check([m["role"] for m in agent.messages] == expected_roles, "message order")
            check(agent.messages[1]["content"] == task, "initial user message")
            observation = agent.messages[3]
            check(observation["extra"]["returncode"] == 0, "shell command failed")
            check(not observation["extra"]["exception_info"], "shell raised an exception")
            marker = MARKER if scenario == "A" else "robotgen_step_one"
            check(observation["extra"]["raw_output"].splitlines() == [marker], "real shell output")
            check(marker in observation["content"], "observation content lacks shell output")
            if scenario == "A":
                check(result["submission"].splitlines() == [SUBMISSION], "submission content")
                check(agent.messages[-1]["content"] == result["submission"], "exit submission")
            else:
                check(len(model.config.outputs) == 2, "second response still available")
                check(model.config.outputs[1] == outputs[1], "second response changed")
                check(all(m.get("content") != outputs[1]["content"] for m in agent.messages), "second response was consumed")
            data = check_trajectory(agent.config.output_path, agent, calls, expected_exit)
            check(data["messages"][2]["extra"]["actions"] == outputs[0]["extra"]["actions"], "saved action")
            check(data["messages"][3]["extra"]["raw_output"] == observation["extra"]["raw_output"], "saved raw observation")
            print(f"Scenario {scenario}: PASS; exit_status={expected_exit}; n_calls={agent.n_calls}; current_index={model.current_index}")
            print(f"roles={expected_roles}; raw_observation={observation['extra']['raw_output']!r}")
            print(f"submission={result.get('submission')!r}" if scenario == "A" else "second response unconsumed: True")
            results.append("PASS")
        except Exception as exc:
            shell_errors = [m.get("extra", {}) for m in agent.messages if m.get("extra", {}).get("exception_info")] if agent else []
            status = "ENVIRONMENT_BLOCKED" if isinstance(exc, OSError) or shell_errors else "FAIL"
            traceback.print_exc()
            for error in shell_errors:
                print(f"LocalEnvironment exception: {error['exception_info']}")
            print(f"Scenario {scenario}: {status}")
            print(f"native trajectory, if saved: {folder / 'native.traj.json'}")
            results.append(status)

    status = "FAIL" if "FAIL" in results else "ENVIRONMENT_BLOCKED" if "ENVIRONMENT_BLOCKED" in results else "PASS"
    print("No real LLM API/key, text-based parser, native tool calling, or Docker was used/tested.")
    print("DeterministicModel supplies parsed actions; this is not RobotGen Harness implementation.")
    print(f"FINAL: {status}")
    return {"PASS": 0, "FAIL": 1, "ENVIRONMENT_BLOCKED": 2}[status]


if __name__ == "__main__":
    raise SystemExit(main())
