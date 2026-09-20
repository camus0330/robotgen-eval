"""Package this isolated work area, excluding runtimes, caches and scratch runs."""
import json,zipfile
from pathlib import Path
from design import ROOT,OUT,REPORTS

def main():
    workspace=ROOT.parent
    status=json.loads((REPORTS/'release_status.json').read_text())
    if not status['manufacturing_exports_passed']:
        raise RuntimeError('Printing files have not passed export read-back')
    if not status['full_requested_motion_release']:
        raise RuntimeError('Both airborne palm swing and hand wave must pass before final packaging')
    files=[ROOT/'README.md',ROOT/'bom.csv',ROOT/'requirements.txt',workspace/'README.md',
           workspace/'ChatGPT Image 2026年9月16日 16_31_44 (3).png',
           workspace/'xl330_m288_t/xl330_m288_t.step',
           workspace/'xl330_m288_t/__cadgen__/models/xl330_m288_t.step/assembly.json']
    for sub in ['src','docs','reports','output/parts','output/assembly','output/meshes','output/renders',
                'output/drawings','output/simulation']:
        for p in (ROOT/sub).rglob('*'):
            if p.is_file() and not any(x.startswith('.') or x=='__pycache__' for x in p.relative_to(ROOT).parts):
                if p == OUT/'renders/walk_three_quarter.png':
                    continue  # Historical rear-foot-supported motion, outside this release.
                files.append(p)
    for kind,key in [('motions','current_motion_names'),('simulation_runs','current_simulation_runs')]:
        for name in status[key]:
            directory=OUT/kind/name
            if not directory.is_dir():raise RuntimeError('Missing released output: '+str(directory))
            files.extend(p for p in directory.rglob('*') if p.is_file() and p.suffix not in ['.log'])
    files=sorted(set(files))
    inventory=[dict(path='gpt_/'+str(p.relative_to(workspace)),bytes=p.stat().st_size) for p in files]
    manifest=OUT/'delivery/file_inventory.json';manifest.parent.mkdir(exist_ok=True)
    manifest.write_text(json.dumps(dict(files=inventory,file_count=len(files),total_bytes=sum(p['bytes'] for p in inventory),
                                       scope='gpt_ only; runtime/cache and intermediate kinematic run excluded',
                                       hardware_validated=False,full_requested_motion_release=status['full_requested_motion_release']),indent=2)+'\n')
    archive=workspace/'gorilla8_print_design.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p,row in zip(files,inventory):z.write(p,row['path'])
        z.write(manifest,'gpt_/gorilla8/output/delivery/file_inventory.json')
    # Read directory entries and sizes back. No checksum/hash computation or comparison.
    with zipfile.ZipFile(archive) as z:
        entries={i.filename:i.file_size for i in z.infolist()}
    if len(entries)!=len(inventory)+1:raise RuntimeError('Archive file count differs from inventory')
    if any(entries[row['path']]!=row['bytes'] for row in inventory):raise RuntimeError('Archive file sizes differ from inventory')
    print(json.dumps(dict(archive=str(archive),bytes=archive.stat().st_size,files=len(entries),inventory_readback=True),indent=2))

if __name__=='__main__':main()
