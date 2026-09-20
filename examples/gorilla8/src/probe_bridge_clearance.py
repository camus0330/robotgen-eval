"""Independent candidate torso reconstruction; manufacturing CAD is not changed."""
import inspect
import json
import argparse
import fcl
import numpy as np
import build_robot as build
import verify_assembly as verify
from design import REPORTS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stepped-shoulder', action='store_true')
    parser.add_argument('--fork-relief', action='store_true')
    args = parser.parse_args()
    source = inspect.getsource(build.torso)
    replacements = {
        'box(x-28.5,x-12.5,min(0,y),max(0,y),z-28,z-24.8)':
        'box(x-28.5,x-12.5,min(0,y),max(0,y),z-31,z-24.8)',
        'box(-12,8.5,-29,29,z-28,z-24.8)':
        'box(-12,8.5,-29,29,z-31,z-24.8)',
        'box(x+12.5,x+32,min(0,y),max(0,y),z-28,z-24.8)':
        'box(-13,-5,min(0,y),max(0,y),-64,-57.8)',
    }
    if args.stepped_shoulder:
        original = 'box(x-28.5,x-12.5,min(0,y),max(0,y),z-28,z-24.8)'
        replacements[original] = 'union('+original+',box(x-28.5,x-16.5,min(0,y),max(0,y),z-31,z-28))'
    for old, new in replacements.items():
        if source.count(old) != 1:
            raise ValueError(f'Expected one source expression: {old}')
        source = source.replace(old, new)
    namespace = dict(vars(build))
    exec(source, namespace)
    candidate = namespace['torso']()
    reliefs = []
    if args.fork_relief:
        for y0,y1 in [(35,40),(-40,-35)]:
            reliefs.append([5.5,8.5,y0,y1,-31.1,-24.7])
            candidate = candidate.cut(build.box(*reliefs[-1])).clean()
    if not candidate.isValid() or len(candidate.Solids()) != 1:
        raise ValueError('Candidate torso must be one valid solid')
    records = verify.load_objects()
    torso = next(o for o in records if o['name'] == 'P01_torso_frame')
    mesh = build.tm(candidate)
    geometry = fcl.BVHModel()
    geometry.beginModel(len(mesh.vertices), len(mesh.faces))
    geometry.addSubModel(mesh.vertices, mesh.faces)
    geometry.endModel()
    torso['mesh_obj'], torso['fcl_obj'] = mesh, fcl.CollisionObject(geometry)
    # This hook is local to this process and makes exact follow-up use the same candidate torso.
    original_loader = verify.load_exact
    def load_candidate(objects):
        original_loader(objects)
        next(o for o in objects if o['name'] == 'P01_torso_frame')['shape'] = candidate
    verify.load_exact = load_candidate
    poses = []
    def add(run, index, shoulder, hip, knee, contacts):
        a = np.radians(shoulder)
        poses.append((run, index, {
            'time_s': float(index), 'stage': 'candidate_bridge_probe',
            'joint_rad': np.radians([shoulder, -shoulder]*2+[hip, knee]*2).tolist(),
            'root_mm': [35+60*np.sin(a), 0., 88+60*np.cos(a)],
            'contact_mask': contacts
        }))
    add('neutral_legs', 0, -10, 21.495, -33.226, [1,1,1,1])
    for i, shoulder in enumerate(range(-10, 13)):
        fraction = i/22
        add('interpolated_air_legs', i, shoulder, 50+10*fraction, -90-10*fraction, [1,1,0,0])
        add('fixed_50_minus90', i, shoulder, 50, -90, [1,1,0,0])
        add('fixed_60_minus100', i, shoulder, 60, -100, [1,1,0,0])
    candidates, ground, excluded = verify.scan(records, poses)
    checks = verify.exact_checks(records, candidates, True)
    failures = [c for c in checks if c['positive_interference']]
    report = dict(purpose='Candidate torso only; no saved CAD, meshes or limits changed',
                  source_replacements=replacements, torso_valid=candidate.isValid(),
                  relief_boxes_x0_x1_y0_y1_z0_z1=reliefs,
                  torso_solid_count=len(candidate.Solids()), torso_volume_mm3=candidate.Volume(),
                  pose_count=len(poses), shoulder_range_deg=[-10,12], elbow='minus shoulder',
                  ground=ground,pair_checks=checks,positive_interference_pairs=failures,
                  self_collision_passed=not failures,
                  ground_passed=all(g['min_mesh_z_mm']>=-.05 for g in ground.values()),
                  limitations=['One degree static sampling only.', 'Not a final exported candidate or a dynamics result.'])
    report['passed'] = report['self_collision_passed'] and report['ground_passed']
    name = 'flat_palm_relief_bridge_clearance_probe.json' if args.fork_relief else ('flat_palm_stepped_bridge_clearance_probe.json' if args.stepped_shoulder else 'flat_palm_bridge_clearance_probe.json')
    path = REPORTS/name
    path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'report':str(path),'passed':report['passed'],'failed_pairs':[p['pair'] for p in failures]}))
    raise SystemExit(0 if report['passed'] else 2)


if __name__ == '__main__':
    main()
