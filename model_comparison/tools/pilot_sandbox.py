"""Pilot native Linux/bubblewrap actions and independent CAD checks.

No inherited credentials, host home or external network; optional dedicated CAD
venv is read-only. Each tool namespace has its own bounded lifetime.
"""
import os
from pathlib import Path, PurePosixPath
import shlex
import subprocess

CAD_VENV = os.environ.get("ROBOTGEN_CAD_VENV", "/home/camus/robotgen-pilot-runtime-20260922")


def cad_mount():
    # Reuse the dedicated, existing CAD venv read-only; never mount user home.
    runtime = Path(CAD_VENV)
    if not PurePosixPath(CAD_VENV).is_absolute() or str(runtime) == "/cad":
        raise ValueError("ROBOTGEN_CAD_VENV must name a dedicated host virtualenv, not /cad")
    if os.name != "nt" and not ((runtime / "pyvenv.cfg").is_file()
                                  and (runtime / "bin/python").is_file()):
        raise FileNotFoundError("CAD host virtualenv unavailable; set ROBOTGEN_CAD_VENV to an existing environment")
    return ["--ro-bind", CAD_VENV, "/cad", "--setenv", "PATH", "/cad/bin:/usr/bin",
            "--setenv", "HOME", "/tmp", "--setenv", "XDG_CONFIG_HOME", "/tmp/config"]


def child_environment():
    # No model credential, inherited proxy, home, or Python startup variables.
    return {name: os.environ[name] for name in ("SystemRoot", "WINDIR") if name in os.environ}


def host_command(inner):
    if os.name != "nt":
        return inner
    executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/wsl.exe"
    return [str(executable), "-d", "Ubuntu-24.04", "--", "sh", "-c", shlex.join(inner)]


def linux_path(path):
    path = Path(path).resolve()
    if os.name != "nt":
        if not path.is_absolute():
            raise ValueError("Expected absolute Linux path")
        return str(path)
    if not path.drive or path.is_symlink():
        raise ValueError("Expected regular absolute Windows path")
    return "/mnt/" + path.drive[0].lower() + path.as_posix()[2:]


def execute_python(source, *, kit, submission=None, writable_output=None, seconds=10, cad=False):
    inner = ["/usr/bin/timeout", "--kill-after=2", str(seconds),
               "/usr/bin/bwrap", "--unshare-all", "--die-with-parent", "--new-session",
               "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin",
               "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
               "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--clearenv",
               "--setenv", "PATH", "/usr/bin", "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
               "--ro-bind", linux_path(kit), "/kit"]
    if submission is not None:
        inner += ["--ro-bind", linux_path(submission), "/submission"]
    if writable_output is not None:
        inner += ["--bind", linux_path(writable_output), "/work"]
    if cad:
        inner += cad_mount()
    inner += ["--chdir", "/tmp", "/cad/bin/python" if cad else "/usr/bin/python3", "-I", "-B", "-c", source]
    command = host_command(inner)
    # Linux timeout owns the namespace/process group; the outer timeout bounds a
    # stuck WSL launch for these checks. execute_command handles design actions.
    return subprocess.run(command, env=child_environment(), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=seconds + 20)


def execute_command(command_text, *, kit, writable_output, seconds=30, cad=False):
    """Execute one model action inside the no-network, no-credential namespace."""
    if not isinstance(command_text, str) or not command_text.strip():
        raise ValueError("empty action")
    limits = "ulimit -t 30 -f 10240 -n 128 -u 32; "
    inner = ["/usr/bin/timeout", "--kill-after=2", str(seconds),
             "/usr/bin/bwrap", "--unshare-all", "--die-with-parent", "--new-session",
             "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin",
             "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
             "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--clearenv",
             "--setenv", "PATH", "/usr/bin", "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
             "--ro-bind", linux_path(kit), "/kit", "--bind", linux_path(writable_output), "/work"]
    if cad:
        inner += cad_mount()
    inner += ["--chdir", "/work", "/bin/sh", "-c", limits + "exec /bin/sh -c " + shlex.quote(command_text)]
    cmd = host_command(inner)
    return subprocess.run(cmd, env=child_environment(), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=seconds + 20)
