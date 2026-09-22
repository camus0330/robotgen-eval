"""Fixed native Code-mode configuration and the single authorized CAD check."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time

from pilot_alt_access import config_args
from pilot_alt_network import CLIENT, client_environment
from pilot_alt_worker import clean

HOST = str(Path(CLIENT).with_name('codex-code-mode-host'))
MARKER = 'ROBOTGEN_CODE_MODE_CAD_OK'


def generation_argv(model, session, output, operator, kit, *, image=True):
    session, output, operator, kit = map(str, (session, output, operator, kit))
    args = [CLIENT, 'exec', '--ignore-user-config', '--ignore-rules', '--ephemeral',
            '--strict-config', '--skip-git-repo-check', '--dangerously-bypass-hook-trust',
            '--json', '--color', 'never', '-C', session, '-m', model]
    if image:
        args += ['-i', session + '/inputs/assets/reference.png']
    args += config_args(cad=True, python_executable='/usr/bin/python3',
                        guard_path=operator + '/pilot_alt_guard.py', native_linux=True)
    settings = {
        'default_permissions': 'robotgen-alt',
        'permissions.robotgen-alt.network.enabled': False,
        'mcp_servers.cad.command': '/usr/bin/python3',
        'mcp_servers.cad.args': ['-B', operator + '/pilot_alt_mcp.py', '--kit', kit, '--output', output],
        'mcp_servers.cad.required': True,
        'mcp_servers.cad.tool_timeout_sec': 90,
        'mcp_servers.cad.startup_timeout_sec': 20,
    }
    for key, value in settings.items():
        args += ['-c', key + '=' + json.dumps(value)]
    args += ['-c', 'permissions.robotgen-alt.filesystem={":minimal"="read",' +
             json.dumps(CLIENT) + '="read",' + json.dumps(HOST) +
             '="read",":workspace_roots"={"."="read"}}',
             '-c', 'permissions.robotgen-alt.workspace_roots={' + json.dumps(session) + '=true}',
             '-c', 'mcp_servers.cad.env={HOME="/tmp",PATH="/usr/bin:/bin"}', '-']
    assert args.count('features.code_mode_host=true') == 1
    assert not any('code_mode_host=false' in a for a in args)
    return args


def short_check(plan_path):
    plan = json.loads(plan_path.read_text())
    check = plan['short_tool_check']
    output = Path(check['output'])
    journal = output / 'check.json'
    if journal.exists():
        raise ValueError('single authorized check already started')
    state = {'argv': check['argv'], 'cwd': check['cwd'], 'started_at_unix': time.time(),
             'robot_quality_result': False, 'api_queries': None, 'provider_retries': None,
             'count_source': 'not_observed', 'status': 'STARTED'}
    def save():
        journal.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
    save()
    prompt = ('This is a tool connectivity check, not a robot design task. Use the registered CAD '
              'execute tool exactly once to run `echo ' + MARKER + '`. Inspect its real output. '
              'Then call the registered CAD submit tool and finish. Use no other tools or actions. '
              'Do not read task inputs or images, create files, or generate a design.')
    start = time.monotonic()
    child = subprocess.Popen(check['argv'], cwd=check['cwd'], env=client_environment(),
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, start_new_session=True)
    observed_hosts = set()
    stop_observer = threading.Event()
    def observe_host():
        while not stop_observer.wait(0.1):
            for entry in Path('/proc').iterdir():
                if entry.name.isdigit():
                    try:
                        if str((entry / 'exe').readlink()) == HOST:
                            observed_hosts.add(int(entry.name))
                    except OSError:
                        pass
    observer = threading.Thread(target=observe_host, daemon=True)
    observer.start()
    timed_out = False
    try:
        stdout, stderr = child.communicate(prompt, timeout=120)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(child.pid, signal.SIGTERM)
        try:
            stdout, stderr = child.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            stdout, stderr = child.communicate()
    finally:
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        stop_observer.set()
        observer.join(timeout=2)
    events = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get('item', {}).get('type') != 'reasoning':
            events.append(json.loads(clean(json.dumps(event))))
    path = output / 'tool_state.json'
    tools = json.loads(path.read_text()) if path.exists() else {}
    records = tools.get('records', [])
    passed = (not timed_out and child.returncode == 0 and tools.get('tool_calls') == 1
              and tools.get('submitted') is True and tools.get('tool_stopped') is True
              and bool(observed_hosts)
              and not any(e.get('item', {}).get('type') == 'command_execution' for e in events)
              and len(records) == 1 and records[0].get('exit_code') == 0
              and records[0].get('stdout', '').strip() == MARKER
              and records[0].get('command') == 'echo ' + MARKER
              and 'code-mode host is disabled' not in stdout + stderr)
    state.update(status='PASS' if passed else 'FAIL', os_exit_code=child.returncode,
                 timed_out=timed_out, elapsed_s=time.monotonic()-start,
                 ended_at_unix=time.time(), events=events, stderr=clean(stderr), tool_state=tools,
                 observed_runtime_host_pids=sorted(observed_hosts))
    save()
    print(json.dumps({k: state[k] for k in ('status', 'os_exit_code', 'elapsed_s')}))
    return 0 if passed else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--short-check', type=Path, required=True)
    raise SystemExit(short_check(parser.parse_args().short_check))
