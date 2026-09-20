#!/usr/bin/env python3
"""One command to build, simulate, probe, stress-test and score a fresh submission."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
try:
    from .prepare_rebuild import prepare
except ImportError:  # Support direct execution.
    from prepare_rebuild import prepare

HERE=Path(__file__).resolve().parent
REPO_ROOT=HERE.parents[1]
CONFIG_ROOT=REPO_ROOT/'configs/benchmark'


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=REPO_ROOT/'examples/gorilla8')
    p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--workers',type=int,default=3);p.add_argument('--resume',action='store_true');args=p.parse_args()
    root=args.root.resolve();run=args.run.resolve();workspace=run/'rebuild'
    if workspace.exists():
        if not args.resume:raise FileExistsError('Run exists; use --resume or choose a new --run')
    else:prepare(root,workspace)
    commands=[['run_rebuild.py','--workspace',str(workspace)]+(['--resume'] if args.resume else []),
              ['digital_geometry.py','--root',str(workspace/'gorilla8'),'--out',str(run/'geometry_probes.json')],
              ['simulate_cases.py','--root',str(workspace/'gorilla8'),'--out',str(run/'robustness_original'),
               '--cases',str(CONFIG_ROOT/'robustness_cases_public.jsonl'),'--workers',str(args.workers)],
              ['evaluate_digital.py','--root',str(root),'--run',str(run),'--out',str(args.out.resolve())]]
    env=dict(os.environ,PYTHONPATH='',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    for cmd in commands:
        result=subprocess.run([sys.executable,str(HERE/cmd[0])]+cmd[1:],env=env)
        if result.returncode:raise SystemExit(result.returncode)


if __name__=='__main__':main()
