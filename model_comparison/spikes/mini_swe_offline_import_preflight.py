"""Prepare a tokenizer resource, then probe real model import in a fresh offline process."""

import argparse
import hashlib
import importlib.metadata
import inspect
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import tempfile
import traceback


UPSTREAM_SHA = "04d809ceab9df28f9adaed044884180159172930"
RESOURCE_HOST = "openaipublic.blob.core.windows.net"
RESOURCE_PATH = "/encodings/cl100k_base.tiktoken"
RESOURCE_URL = f"https://{RESOURCE_HOST}{RESOURCE_PATH}"
CACHE_NAME = hashlib.sha1(RESOURCE_URL.encode()).hexdigest()
RESOURCE_SHA256 = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def clean_environment():
    # Only enumerate names; never inspect discarded credential/config values.
    allowed = {"PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP"}
    for name in tuple(os.environ):
        if name.upper() not in allowed:
            del os.environ[name]
    os.environ.update({
        "MSWEA_SILENT_STARTUP": "1", "PYTHON_DOTENV_DISABLED": "1",
        "LITELLM_MODE": "PRODUCTION", "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        "NO_PROXY": "*", "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1",
    })


def provenance():
    dist = importlib.metadata.distribution("mini-swe-agent")
    origin = json.loads(dist.read_text("direct_url.json") or "{}")
    check(origin.get("url") == "https://github.com/SWE-agent/mini-swe-agent.git", "unexpected upstream")
    check(origin.get("vcs_info", {}).get("commit_id") == UPSTREAM_SHA, "upstream SHA mismatch")
    check(dist.version == "2.4.6", "mini-swe version mismatch")
    package = Path(dist.locate_file("minisweagent")).resolve()
    check(package.is_relative_to(Path(sys.prefix).resolve()), "package outside virtualenv")
    print(f"Python={sys.version}; platform={platform.platform()}; machine={platform.machine()}")
    print(f"executable={sys.executable}; pid={os.getpid()}")
    print(f"mini-swe-agent={dist.version}; package={package}; direct_url={json.dumps(origin)}")
    for name in ("litellm", "tiktoken"):
        print(f"{name}={importlib.metadata.version(name)}")
    print(f"installed LiteLLM constraint={[r for r in dist.requires or [] if r.lower().startswith('litellm')]}")
    return package


def inspect_resources():
    # Read actual installed source, without importing LiteLLM or loading any tokenizer.
    dist = importlib.metadata.distribution("litellm")
    source = Path(dist.locate_file("litellm/litellm_core_utils/default_encoding.py"))
    content = source.read_text(encoding="utf-8")
    print(f"Phase 1 source={source}")
    print(content)
    if 'os.getenv("CUSTOM_TIKTOKEN_CACHE_DIR")' not in content:
        raise RuntimeError("Current installed source does not show the inspected custom-cache mechanism")
    bundled = source.parent / "tokenizers"
    print(f"bundled directory={bundled}; cl100k cache exists={(bundled / CACHE_NAME).exists()}")


def audit_boundary(mode, forbidden, network_events, resource_ips):
    http_target_approved = False

    def audit(event, args):
        nonlocal http_target_approved
        reason = None
        if event == "open" and isinstance(args[0], (str, os.PathLike)):
            if Path(args[0]).name.lower() in {".env", "api_config.json"}:
                reason = "sensitive configuration file"
        elif event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"}:
            reason = "child process/shell forbidden within worker"
        elif event in {"socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr",
                       "socket.connect", "socket.sendto", "socket.sendmsg",
                       "http.client.connect", "http.client.send"}:
            target = None
            if event == "http.client.connect":
                target = [args[1], args[2]]
            elif event in {"socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr"}:
                target = str(args[0])
            elif event == "socket.connect":
                target = args[1]
            elif event == "http.client.send":
                # Record/allow only this GET path, never dump headers or credentials.
                target = bytes(args[1]).split(b"\r\n", 1)[0].decode("ascii", errors="replace")
            network_events.append({"event": event, "target": target})
            if mode == "offline":
                reason = "all runtime network access forbidden"
            elif event == "http.client.connect":
                http_target_approved = target == [RESOURCE_HOST, 443]
                if not http_target_approved:
                    reason = "non-tokenizer HTTP target"
            elif event == "socket.getaddrinfo":
                if target != RESOURCE_HOST or args[1] != 443:
                    reason = "non-tokenizer DNS target"
            elif event == "socket.connect":
                if args[1][0] not in resource_ips or args[1][1] != 443:
                    reason = "connection outside approved tokenizer HTTPS request"
            elif event == "http.client.send":
                if not http_target_approved or target != f"GET {RESOURCE_PATH} HTTP/1.1":
                    reason = "non-tokenizer HTTP request"
            else:
                reason = "unexpected network operation"
        if reason:
            forbidden.append({"event": event, "reason": reason})
            raise PermissionError(f"{mode} boundary rejected {event}: {reason}")

    sys.addaudithook(audit)


def worker(mode, cache):
    forbidden, network_events = [], []
    resource_ips = set()
    stage = "setup"
    os.environ["CUSTOM_TIKTOKEN_CACHE_DIR"] = str(cache)
    os.environ["MSWEA_GLOBAL_CONFIG_DIR"] = tempfile.mkdtemp(prefix="robotgen-import-config-")
    if mode == "prepare":
        # tiktoken's native cache setting; LiteLLM maps CUSTOM_* to this in the runtime.
        os.environ["TIKTOKEN_CACHE_DIR"] = str(cache)
    audit_boundary(mode, forbidden, network_events, resource_ips)
    code = 0
    try:
        print(f"worker={mode}; pid={os.getpid()}; cache={cache}")
        if mode == "prepare":
            stage = "tiktoken resource preparation"
            # Resolve only the authorized resource host for the connection allowlist.
            resource_ips.update(row[4][0] for row in socket.getaddrinfo(RESOURCE_HOST, 443, type=socket.SOCK_STREAM))
            before = {p.name for p in cache.iterdir()}
            import tiktoken
            encoding = tiktoken.get_encoding("cl100k_base")
            check(encoding.name == "cl100k_base", "wrong encoding")
            artifact = cache / CACHE_NAME
            data = artifact.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            check(digest == RESOURCE_SHA256, "tokenizer SHA-256 mismatch")
            print(f"new cache files={sorted(p.name for p in cache.iterdir() if p.name not in before)}")
            print(f"resource={RESOURCE_URL}; filename={artifact.name}; bytes={len(data)}; sha256={digest}")
        else:
            stage = "import minisweagent"
            import minisweagent
            print(f"minisweagent import=PASS; version={minisweagent.__version__}; path={minisweagent.__file__}")
            stage = "import LitellmTextbasedModel"
            from minisweagent.models.litellm_textbased_model import LitellmTextbasedModel
            print(f"LitellmTextbasedModel import=PASS; path={inspect.getfile(LitellmTextbasedModel)}")
            stage = "constructor"
            model = LitellmTextbasedModel(model_name="robotgen/offline-import-test", cost_tracking="ignore_errors")
            print("constructor=PASS")
            print(f"runtime action_regex={model.config.action_regex!r}")
            check(os.environ.get("TIKTOKEN_CACHE_DIR") == str(cache), "LiteLLM did not select prepared cache")
            print(f"runtime TIKTOKEN_CACHE_DIR={os.environ['TIKTOKEN_CACHE_DIR']}")
        if forbidden:
            raise PermissionError("Dependency suppressed a forbidden-access exception")
    except Exception as error:
        traceback.print_exc()
        print(f"failure stage={stage}")
        code = 1 if isinstance(error, AssertionError) and not forbidden else 2
    print(f"network events={json.dumps(network_events)}")
    print(f"forbidden accesses={json.dumps(forbidden)}")
    print(f"forbidden network attempt count={sum(e['event'].startswith(('socket.', 'http.')) for e in forbidden)}")
    print(f"{mode} result={ {0: 'PASS', 1: 'FAIL', 2: 'ENVIRONMENT_BLOCKED'}[code] }")
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("prepare", "offline"))
    parser.add_argument("--cache", type=Path)
    args = parser.parse_args()
    clean_environment()
    if args.phase:
        if not args.cache or not args.cache.is_dir():
            print("FAIL: worker requires an existing cache directory")
            return 1
        return worker(args.phase, args.cache.resolve())
    try:
        provenance()
        inspect_resources()
        cache = Path(tempfile.mkdtemp(prefix="robotgen-tokenizer-cache-"))
        print(f"prepared cache path={cache}")
        for phase in ("prepare", "offline"):
            command = [sys.executable, "-B", "-u", str(Path(__file__).resolve()), "--phase", phase, "--cache", str(cache)]
            print(f"fresh process command={json.dumps(command)}", flush=True)
            result = subprocess.run(command, shell=False)
            print(f"{phase} process exit code={result.returncode}", flush=True)
            if result.returncode:
                code = 1 if result.returncode == 1 else 2
                print(f"FINAL: {'FAIL' if code == 1 else 'ENVIRONMENT_BLOCKED'}")
                return code
        print("FINAL: PASS (resource preparation + fresh offline import/constructor only)")
        return 0
    except Exception as error:
        traceback.print_exc()
        code = 1 if isinstance(error, AssertionError) else 2
        print(f"FINAL: {'FAIL' if code == 1 else 'ENVIRONMENT_BLOCKED'}")
        return code


if __name__ == "__main__":
    raise SystemExit(main())
