"""Geometry-only proposed elbow over-center range; does not change joint limits."""
import json
import argparse
import numpy as np
from design import REPORTS
from verify_assembly import load_objects, scan, exact_checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--leg', nargs=2, type=float, action='append', metavar=('HIP', 'KNEE'))
    parser.add_argument('--report-name', default='flat_palm_elbow_overcenter_probe.json')
    args = parser.parse_args()
    legs = args.leg or [(29, -110), (30, -110)]
    poses = []
    for hip, knee in legs:
        for i, shoulder in enumerate(range(-10, 21)):
            a = np.radians(shoulder)
            poses.append((f'hip_{hip}_knee_{knee}', i, {
                'time_s': float(i), 'stage': 'overcenter_static_probe',
                'joint_rad': np.radians([shoulder, -shoulder]*2+[hip, knee]*2).tolist(),
                'root_mm': [35+60*np.sin(a), 0., 88+60*np.cos(a)],
                'contact_mask': [1, 1, 0, 0]
            }))
    records = load_objects()
    candidates, ground, excluded = scan(records, poses)
    checks = exact_checks(records, candidates, True)
    failed = [p for p in checks if p['positive_interference']]
    report = {
        'purpose': 'Independent proposed joint-range geometry probe; no CAD or joint limits changed.',
        'input': 'Current delivered actual mesh and matching STEP assembly',
        'pose_count': len(poses), 'shoulder_deg': [-10, 20], 'shoulder_step_deg': 1,
        'elbow_deg': 'minus shoulder', 'leg_postures_hip_knee_deg': legs,
        'root_orientation': 'identity',
        'root_formula_mm': 'x=35+60*sin(shoulder); z=88+60*cos(shoulder)',
        'root_x_progress_minus10_to_plus10_mm': float(120*np.sin(np.radians(10))),
        'method': 'FCL candidate detection at all poses; exact STEP common volume for every candidate relative transform.',
        'interference_tolerance_mm3': 0.001,
        'ground': ground, 'pair_checks': checks, 'positive_interference_pairs': failed,
        'stock_bearing_pairs_excluded': sorted(excluded),
        'passed': not failed and all(g['min_mesh_z_mm'] >= -0.05 for g in ground.values()),
        'limitations': ['Static one-degree sampling, not continuous collision checking.',
                        'No new joint range approved by this probe.',
                        'No torque, dead-center load controllability or dynamics validation.']
    }
    path = REPORTS/args.report_name
    path.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'report': str(path), 'passed': report['passed'], 'positive_interference_pairs': failed}))
    raise SystemExit(0 if report['passed'] else 2)


if __name__ == '__main__':
    main()
