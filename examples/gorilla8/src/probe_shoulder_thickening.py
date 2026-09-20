"""Check an in-memory shoulder bridge candidate against the full references."""
import inspect
import json
import argparse

import fcl

import build_robot as build
import verify_assembly as verify
from design import REPORTS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rectangular', action='store_true', help='Probe full-height 16x13 mm beam joining the shoulder cup')
    args = parser.parse_args()
    source = inspect.getsource(build.torso)
    replacements = {
        'box(x-28.5,x-16.5,min(0,y),max(0,y),z-32,z-28)':
        'box(x-28.5,x-16.5,min(0,y),max(0,y),z-37,z-28)',
        'box(-12,8.5,-29,29,z-32,z-24.8)':
        'box(-12,8.5,-29,29,z-37,z-24.8)',
    }
    purpose = 'In-memory P01 shoulder bridge bottom -32 to -37 mm; saved CAD unchanged'
    report_name = 'shoulder_thickening_probe.json'
    if args.rectangular:
        replacements = {
            'union(box(x-28.5,x-12.5,min(0,y),max(0,y),z-28,z-24.8),\n'
            '                    box(x-28.5,x-16.5,min(0,y),max(0,y),z-32,z-28),\n'
            '                    box(-12,8.5,-29,29,z-32,z-24.8))':
            'union(box(x-28.5,x-12.5,min(0,y),max(0,y),z-28,z-15),\n'
            '                    box(-12,8.5,-29,29,z-28,z-15))',
            'box(5.5,8.5,y0,y1,-31.1,-24.7)': 'box(5.5,8.5,y0,y1,-28.1,-14.9)',
        }
        purpose = 'In-memory P01 rectangular shoulder beam z[-28,-15] with full-height fork relief; saved CAD unchanged'
        report_name = 'shoulder_rectangular_probe.json'
    for old, new in replacements.items():
        if source.count(old) != 1:
            raise ValueError(f'Expected one source expression: {old}')
        source = source.replace(old, new)
    namespace = dict(vars(build))
    exec(source, namespace)
    candidate = namespace['torso']()
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
    original_loader = verify.load_exact

    def load_candidate(objects):
        original_loader(objects)
        next(o for o in objects if o['name'] == 'P01_torso_frame')['shape'] = candidate

    verify.load_exact = load_candidate
    motion_names = ['flat_palm_swing', 'flat_palm_wave']
    poses = verify.frames(motion_names)
    candidates, ground, excluded = verify.scan(records, poses)
    checks = verify.exact_checks(records, candidates, True)
    failures = [check['pair'] for check in checks if check['positive_interference']]
    ground_passed = all(g['min_mesh_z_mm'] >= -.05 for g in ground.values())
    report = {
        'purpose': purpose,
        'source_replacements': replacements,
        'candidate_torso_valid': candidate.isValid(),
        'candidate_torso_solid_count': len(candidate.Solids()),
        'candidate_torso_volume_mm3': candidate.Volume(),
        'motion_directories': motion_names, 'frame_count': len(poses),
        'exhaustive_exact': True, 'volume_tolerance_mm3': .001,
        'ground_penetration_tolerance_mm': .05,
        'ground': ground, 'pair_checks': checks,
        'excluded_stock_bearing_pairs': sorted(excluded),
        'positive_interference_pairs': failures,
        'self_collision_passed': not failures,
        'ground_passed': ground_passed, 'passed': not failures and ground_passed,
        'limitations': ['Discrete reference poses, not continuous collision checking.',
                       'Candidate CAD is not exported and its mass is not used for dynamics.',
                       'Added fasteners and cables are not solid geometry in this scan.'],
    }
    path = REPORTS / report_name
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'report': str(path), 'passed': report['passed'], 'failed_pairs': failures}), flush=True)
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
