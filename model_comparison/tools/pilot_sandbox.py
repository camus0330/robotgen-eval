"""Fixed WSL/bubblewrap preflight/evaluator sandbox; not a generation environment.

Only immutable operator checks run here. Whole-attempt resource containment and
CAD/simulation dependencies are not yet validated for untrusted robot code.
"""
import os
from pathlib import Path
import shlex
import subprocess


def child_environment():
    # No model credential, inherited proxy, home, or Python startup variables.
    return {name: os.environ[name] for name in ("SystemRoot", "WINDIR") if name in os.environ}


def linux_path(path):
    path = Path(path).resolve()
    if not path.drive or path.is_symlink():
        raise ValueError("Expected regular absolute Windows path")
    return "/mnt/" + path.drive[0].lower() + path.as_posix()[2:]


def execute_python(source, *, kit, submission=None, seconds=10):
    executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/wsl.exe"
    inner = ["/usr/bin/timeout", "--kill-after=2", str(seconds),
               "/usr/bin/bwrap", "--unshare-all", "--die-with-parent", "--new-session",
               "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin",
               "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
               "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--clearenv",
               "--setenv", "PATH", "/usr/bin", "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
               "--ro-bind", linux_path(kit), "/kit"]
    if submission is not None:
        inner += ["--ro-bind", linux_path(submission), "/submission"]
    inner += ["--chdir", "/tmp", "/usr/bin/python3", "-B", "-c", source]
    command = [str(executable), "-d", "Ubuntu-24.04", "--", "sh", "-c", shlex.join(inner)]
    # Linux timeout owns the namespace/process group; the outer timeout bounds a
    # stuck WSL launch for these fixed checks. No generated commands are accepted.
    return subprocess.run(command, env=child_environment(), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=seconds + 20)
