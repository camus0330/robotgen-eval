"""Check the pinned upstream text parser with local response shapes only."""

import importlib.metadata
import inspect
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import traceback
from types import SimpleNamespace


UPSTREAM = "https://github.com/SWE-agent/mini-swe-agent.git"
UPSTREAM_SHA = "04d809ceab9df28f9adaed044884180159172930"
VERSION = "2.4.6"
EXPECTED_REGEX = r"```mswea_bash_command\s*\n(.*?)\n```"


def check(condition, description):
    if not condition:
        raise AssertionError(description)


def response(content, finish_reason="stop"):
    # Shape only: no parsed actions, regex, extraction, provider or execution logic.
    return SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=content), finish_reason=finish_reason
    )])


def expect_format_error(model, value, error_type, count):
    try:
        model._parse_actions(value)
    except error_type as error:
        check(type(error) is error_type, "must raise the real upstream FormatError")
        check(bool(error.messages), "FormatError must contain an error observation")
        message = error.messages[0]
        check(message["role"] == "user", "error observation role")
        check(message["extra"]["interrupt_type"] == "FormatError", "interrupt_type")
        check(message["extra"]["n_actions"] == count, "n_actions")
        check(message["extra"]["model_response"] == value.choices[0].message.content,
              "original model_response must be retained verbatim")
        wording = message["content"].lower()
        check("exactly one" in wording or "exactly 1" in wording, "exactly-one error meaning")
        check(f"found {count}" in wording, "found-count error meaning")
        return message
    raise AssertionError("Expected FormatError; parser must not silently select an action")


def main():
    # Delete non-allowlisted variable names without reading their values.
    allowed = {"PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP", "HOME"}
    for name in tuple(os.environ):
        if name.upper() not in allowed:
            del os.environ[name]
    work = Path(tempfile.mkdtemp(prefix="robotgen-text-parser-"))
    os.environ["MSWEA_GLOBAL_CONFIG_DIR"] = str(work / "empty-global-config")
    os.environ["MSWEA_SILENT_STARTUP"] = "1"
    # Existing dependency settings: no .env loading or import-time remote cost-map fetch.
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    os.environ["LITELLM_MODE"] = "PRODUCTION"
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    print(f"Python={sys.version}")
    print(f"platform={platform.platform()}; machine={platform.machine()}")
    print(f"executable={sys.executable}")
    print(f"temporary config root={work}")

    blocked = []

    def reject_external_access(event, args):
        # Fail closed, without replacing any provider/model/parser implementation.
        forbidden = event in {"socket.connect", "socket.getaddrinfo", "socket.sendto",
                              "http.client.connect", "subprocess.Popen", "os.system"}
        if event == "open" and isinstance(args[0], (str, os.PathLike)):
            forbidden = Path(args[0]).name.lower() in {".env", "api_config.json"}
        if forbidden:
            blocked.append(event)
            raise PermissionError(f"Offline parser boundary rejected {event}")

    sys.addaudithook(reject_external_access)

    try:
        dist = importlib.metadata.distribution("mini-swe-agent")
        origin = json.loads(dist.read_text("direct_url.json") or "{}")
        check(origin.get("url") == UPSTREAM, "requires the fixed upstream VCS installation")
        check(origin.get("vcs_info", {}).get("commit_id") == UPSTREAM_SHA, "upstream SHA mismatch")
        check(dist.version == VERSION, "distribution version mismatch")

        import minisweagent
        from minisweagent.exceptions import FormatError
        from minisweagent.models.litellm_textbased_model import LitellmTextbasedModel
        from minisweagent.models.utils.actions_text import parse_regex_actions

        if blocked:
            raise PermissionError(f"Import attempted forbidden access: {blocked}")
        check(minisweagent.__version__ == VERSION, "import version mismatch")
        package = Path(dist.locate_file("minisweagent")).resolve()
        check(package.is_relative_to(Path(sys.prefix).resolve()), "package outside this virtualenv")
        for obj in (minisweagent, LitellmTextbasedModel, parse_regex_actions, FormatError):
            source = Path(inspect.getfile(obj)).resolve()
            check(source.is_relative_to(package), "import outside pinned distribution")
            print(f"source[{obj.__name__}]={source}")
        check(LitellmTextbasedModel._parse_actions.__globals__["parse_regex_actions"] is parse_regex_actions,
              "model must use the real upstream helper")
        model = LitellmTextbasedModel(
            model_name="robotgen/offline-parser-test", cost_tracking="ignore_errors"
        )
        if blocked:
            raise PermissionError(f"Construction attempted forbidden access: {blocked}")
        check(model.config.action_regex == EXPECTED_REGEX, "upstream default action_regex changed")
        print(f"minisweagent.__version__={minisweagent.__version__}")
        print(f"direct_url={json.dumps(origin)}")
        print(f"default action_regex={model.config.action_regex!r}")
        for name in ("litellm", "openai", "pydantic", "jinja2", "python-dotenv"):
            print(f"installed dependency: {name}=={importlib.metadata.version(name)}")
    except Exception as error:
        traceback.print_exc()
        status = "ENVIRONMENT_BLOCKED" if blocked or isinstance(error, (ImportError, OSError, importlib.metadata.PackageNotFoundError)) else "FAIL"
        print(f"Cases A-F not run: {status}; precondition failed")
        print(f"FINAL: {status}")
        return 2 if status == "ENVIRONMENT_BLOCKED" else 1

    # Commands remain inert strings; only _parse_actions is invoked for every case.
    cases = [
        ("A", "A plain explanation.\n```mswea_bash_command\necho robotgen_parser_ok\n```\nEnd.", "stop", "echo robotgen_parser_ok", None),
        ("B", "```mswea_bash_command\nprintf first\nprintf second\n```", "stop", "printf first\nprintf second", None),
        ("C", "Only ordinary text, with no action block.", "stop", None, 0),
        ("D", "```mswea_bash_command\necho first\n```\n```mswea_bash_command\necho second\n```", "stop", None, 2),
        ("E", "```mswea_bash_command\necho truncated\n", "length", None, 0),
        ("F", "```bash\necho wrong_fence\n```", "stop", None, 0),
    ]
    failed = False
    for label, content, finish_reason, command, count in cases:
        try:
            value = response(content, finish_reason)
            if command is not None:
                actions = model._parse_actions(value)
                check(actions == [{"command": command}], "expected exactly one unmodified command")
                print(f"Case {label}: PASS command={actions[0]['command']!r}")
            else:
                message = expect_format_error(model, value, FormatError, count)
                if label == "E":
                    control = expect_format_error(model, response(content, "stop"), FormatError, 0)
                    check(message["content"] == control["content"], "finish_reason affected the default error text")
                    print("Case E finish_reason length vs stop: default error text identical")
                print(f"Case {label}: PASS n_actions={count}")
                print(f"FormatError message={json.dumps(message)}")
        except Exception as error:
            traceback.print_exc()
            if blocked or isinstance(error, PermissionError):
                print(f"Case {label}: ENVIRONMENT_BLOCKED")
                print("FINAL: ENVIRONMENT_BLOCKED")
                return 2
            print(f"Case {label}: FAIL")
            failed = True
        if blocked:
            print(f"Forbidden access attempted: {blocked}")
            print("FINAL: ENVIRONMENT_BLOCKED")
            return 2

    print("Forbidden network/process/config-file access attempts: 0")
    print("No query, real API/key, Agent, shell command, native tools, or protocol freeze.")
    print(f"FINAL: {'FAIL' if failed else 'PASS'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
