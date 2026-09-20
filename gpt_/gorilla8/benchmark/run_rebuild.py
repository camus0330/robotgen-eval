#!/usr/bin/env python3
"""Rebuild frozen source in a separate workspace, logging every stage and hash."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(p):
    return hashlib.file_digest(p.open('rb'), 'sha256').hexdigest()


def main():
    p = argparse.ArgumentParser(); p.add_argument('--workspace', type=Path, required=True)
    p.add_argument('--resume', action='store_true', help='Continue completed stages from this exact frozen input snapshot')
    args = p.parse_args(); workspace = args.workspace.resolve(); robot = workspace/'gorilla8'
    logdir = workspace/'logs'; logdir.mkdir(exist_ok=True)
    frozen = json.loads((workspace/'input_manifest.json').read_text())
    assert all(sha(workspace/r['path']) == r['sha256'] for r in frozen['files']), 'Frozen input changed'
    stages = [('build', ['build_robot.py']), ('plan', ['plan_flat_palm_motion.py']),
              ('export', ['export_simulation.py']), ('readback', ['verify_exports.py'])]
    for name in ('swing','wave'):
        motion = 'flat_palm_'+name
        stages.append(('simulate_'+name, ['simulate.py','--motion',str(robot/'output/motions'/motion/'motion.npz'),
                       '--out',str(robot/'output/simulation_runs'/f'{motion}_release')]+(['--gravity-feedforward'] if name=='swing' else [])))
    stages += [('reference_collision',['verify_assembly.py','--motion','flat_palm_swing','--motion','flat_palm_wave',
                                      '--exhaustive-exact','--skip-render','--report',str(robot/'reports/flat_reference_collision.json')])]
    for name in ('swing','wave'):
        stages.append(('collision_'+name,['verify_assembly.py','--exhaustive-exact','--skip-render',
                      '--simulation-trace',str(robot/f'output/simulation_runs/flat_palm_{name}_release/trace.json'),
                      '--report',str(robot/f'reports/flat_{name}_simulation_collision.json')]))
    stages.append(('strength',['audit_strength.py','--simulation-result',str(robot/'output/simulation_runs/flat_palm_swing_release/result.json'),
                              '--simulation-result',str(robot/'output/simulation_runs/flat_palm_wave_release/result.json')]))
    report = dict(python=sys.version, input_manifest_sha256=sha(workspace/'input_manifest.json'), stages=[], complete=False)
    if args.resume and (workspace/'rebuild_report.json').exists():
        previous = json.loads((workspace/'rebuild_report.json').read_text())
        assert previous['input_manifest_sha256'] == report['input_manifest_sha256']
        report['stages'] = [s for s in previous['stages'] if s['returncode'] == 0]
    completed = {s['stage'] for s in report['stages']}
    env = dict(os.environ, MUJOCO_GL='egl', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
    for name, params in stages:
        if name in completed:
            print('RESUME completed', name, flush=True)
            continue
        cmd = [sys.executable, str(robot/'src'/params[0])] + params[1:]
        started = time.time(); print('START', name, flush=True)
        with (logdir/(name+'.log')).open('w') as log:
            result = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, env=env)
        item = dict(stage=name, command=cmd, started_unix=started, elapsed_s=time.time()-started,
                    returncode=result.returncode, log=str((logdir/(name+'.log')).relative_to(workspace)))
        report['stages'].append(item)
        (workspace/'rebuild_report.json').write_text(json.dumps(report,indent=2))
        print('END', name, item['returncode'], round(item['elapsed_s'],2), flush=True)
        if result.returncode:
            raise SystemExit(result.returncode)
    report['complete'] = True
    report['input_unchanged'] = all(sha(workspace/r['path']) == r['sha256'] for r in frozen['files'])
    outputs = [f for sub in ('output','reports') for f in (robot/sub).rglob('*') if f.is_file()]
    manifest = [{'path':str(f.relative_to(workspace)), 'sha256':sha(f)} for f in sorted(outputs)]
    (workspace/'output_manifest.json').write_text(json.dumps(manifest,indent=2))
    report['output_manifest_sha256'] = sha(workspace/'output_manifest.json')
    (workspace/'rebuild_report.json').write_text(json.dumps(report,indent=2))
    print('COMPLETE',flush=True)


if __name__=='__main__': main()
