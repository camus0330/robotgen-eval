"""No-model native Linux filesystem and CAD-MCP boundary acceptance."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import uuid

BINARY = "/home/camus/robotgen-alt-client-20260923/codex-x86_64-unknown-linux-musl"
BASE = Path("/home/camus/robotgen-alt-runtime/continuation_20260923_0332")


def main():
    run = BASE / "boundary" / uuid.uuid4().hex
    work, external, client = [run / n for n in ("work", "external", "client-state")]
    for p in (work, external, client):
        p.mkdir(parents=True)
    marker = external / "synthetic.txt"
    marker.write_text("SYNTHETIC_EXTERNAL_ONLY")
    (work / "allowed.txt").write_text("allowed")
    source = (
        "from pathlib import Path; import json\n"
        "assert Path('allowed.txt').read_text() == 'allowed'\n"
        "try:\n Path(" + repr(str(marker)) + ").read_text(); raise AssertionError('external read allowed')\n"
        "except (PermissionError, FileNotFoundError): pass\n"
        "try:\n Path(" + repr(str(external / 'forbidden.txt')) + ").write_text('synthetic'); raise AssertionError('external write allowed')\n"
        "except (PermissionError, FileNotFoundError): pass\n"
        "print(json.dumps({'inside_read':True,'outside_read_denied':True,'outside_write_denied':True}))\n")
    profile = ['-c', 'default_permissions="robotgen-alt"', '-c',
               'permissions.robotgen-alt.filesystem={":minimal"="read",' + json.dumps(BINARY) + '="read",":workspace_roots"={"."="read"}}',
               '-c', 'permissions.robotgen-alt.network.enabled=false', '-c',
               'permissions.robotgen-alt.workspace_roots={' + json.dumps(str(work)) + '=true}']
    argv = [BINARY, 'sandbox', '-P', 'robotgen-alt', '-C', str(work)] + profile + ['/usr/bin/python3', '-I', '-B', '-c', source]
    child = subprocess.run(argv, cwd=work, env={'PATH':'/usr/bin:/bin','HOME':'/home/camus','CODEX_HOME':str(client)},
                           capture_output=True, text=True, timeout=60)
    evidence = {'platform':'WSL2 native Linux', 'run_id':run.name, 'python_parent_cwd':os.getcwd(),
                'subprocess_cwd':str(work), 'codex_C':str(work), 'config_source':'explicit profile; empty per-check CODEX_HOME',
                'profile':'robotgen-alt', 'legacy_sandbox_mode':False, 'argv':argv, 'os_exit_code':child.returncode,
                'stdout':child.stdout, 'stderr':child.stderr, 'model_requests':0,
                'external_marker_outside_allowed_and_minimal':str(marker), 'filesystem_passed':False}
    if child.returncode == 0:
        flags = json.loads(child.stdout)
        evidence['filesystem_passed'] = flags == {'inside_read':True,'outside_read_denied':True,'outside_write_denied':True}
    output = run / 'cad-mcp'
    (output/'work').mkdir(parents=True)
    source = "import os,pathlib,json,importlib.metadata as m; assert pathlib.Path('/kit/inputs/TASK_SPEC.md').is_file(); assert not pathlib.Path('/mnt').exists(); assert not pathlib.Path('/home/camus').exists(); assert 'ROBOTGEN_SYNTHETIC_CREDENTIAL' not in os.environ; assert os.environ['HOME']=='/tmp'; assert os.statvfs('/cad').f_flag & os.ST_RDONLY; assert os.statvfs('/kit').f_flag & os.ST_RDONLY; pathlib.Path('/work/synthetic_output.txt').write_text('BOUNDARY_ONLY'); print(json.dumps({'namespace_boundary':'PASS','cad_readonly':True,'kit_readonly':True,'python':__import__('sys').version.split()[0],'cadquery':m.version('cadquery'),'ocp':m.version('cadquery-ocp')}))"
    requests = [
        {'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05'}},
        {'jsonrpc':'2.0','id':2,'method':'tools/list'},
        {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'execute','arguments':{'command':'/cad/bin/python -I -B -c '+shlex.quote(source)}}},
        {'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'submit','arguments':{}}},
        {'jsonrpc':'2.0','id':5,'method':'tools/call','params':{'name':'execute','arguments':{'command':'must-not-execute-after-submit'}}}]
    argv = ['/usr/bin/python3','-B',str(BASE/'operator/pilot_alt_mcp.py'),'--kit',str(BASE/'public'),'--output',str(output)]
    child = subprocess.run(argv,cwd=BASE/'operator',env={'PATH':'/usr/bin:/bin','ROBOTGEN_SYNTHETIC_CREDENTIAL':'SYNTHETIC_ONLY'},
                           input=''.join(json.dumps(x)+'\n' for x in requests),capture_output=True,text=True,timeout=90)
    messages = [json.loads(x) for x in child.stdout.splitlines()]
    state = json.loads((output/'tool_state.json').read_text())
    value = json.loads(messages[2]['result']['content'][0]['text']) if len(messages)>2 and 'result' in messages[2] else {}
    evidence['mcp'] = {'argv':argv,'cwd':str(BASE/'operator'),'os_exit_code':child.returncode,'responses':messages,'stderr':child.stderr,'state':state,
                       'passed':child.returncode==0 and value.get('exit_code')==0 and '"namespace_boundary": "PASS"' in value.get('stdout','')
                       and len(messages)==5 and 'error' in messages[4] and state['tool_calls']==1 and state['submitted'] and state['tool_stopped']}
    print(json.dumps(evidence))
    return 0 if evidence['filesystem_passed'] and evidence['mcp']['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
