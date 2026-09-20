#!/usr/bin/env python3
"""Create a new immutable-input workspace; never overwrite an existing run."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

REPO_ROOT = Path(__file__).resolve().parents[2]


def prepare(root,workspace):
    if workspace.exists():raise FileExistsError('Choose a new workspace or resume the existing rebuild')
    robot=workspace/'gorilla8';robot.mkdir(parents=True)
    for name in ['src','docs']:shutil.copytree(root/name,robot/name,ignore=shutil.ignore_patterns('__pycache__'))
    for name in ['bom.csv','README.md']:shutil.copy2(root/name,robot/name)
    shutil.copy2(REPO_ROOT/'requirements.txt',robot/'requirements.txt')
    data=workspace/'data';data.mkdir()
    for name in ['xl330_m288_t.step','xl330_m288_t_assembly.json']:
        shutil.copy2(REPO_ROOT/'data'/name,data/name)
    rows=[]
    for path in sorted(workspace.rglob('*')):
        if path.is_file():
            with path.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
            rows.append(dict(path=str(path.relative_to(workspace)),sha256=digest))
    (workspace/'input_manifest.json').write_text(json.dumps(dict(created_utc=datetime.now(timezone.utc).isoformat(),
                                                              scope='frozen inputs before generation',files=rows),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--workspace',type=Path,required=True)
    args=p.parse_args();prepare(args.root.resolve(),args.workspace.resolve())
