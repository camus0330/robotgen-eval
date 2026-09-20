"""Plan pitch-only contact motion; report kinematics and vertical-force statics."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import brentq, linprog

from design import JOINT_NAMES, LIMBS, OUT, PAD_RADIUS_MM, ROOT_HEIGHT_MM, transforms


def ik(limb, root, target):
    """Exact 2R IK: both axes +Y; zero links point along -Z; units mm/rad."""
    delta = np.asarray(target) - np.asarray(root) - limb['origin_mm']
    if abs(delta[1]) > 1e-6:
        raise ValueError(f"{limb['name']}: lateral target requires an unavailable DoF")
    a, b = limb['lengths_mm']
    cosine = (delta[0] ** 2 + delta[2] ** 2 - a * a - b * b) / (2 * a * b)
    if not -1 <= cosine <= 1:
        raise ValueError(f"{limb['name']}: endpoint outside 2R workspace")
    q2 = limb['q2_sign'] * math.acos(cosine)
    q1 = math.atan2(-delta[0], -delta[2]) - math.atan2(b * math.sin(q2), a + b * math.cos(q2))
    values = np.array([q1, q2])
    limits = np.radians(limb['limits_deg'])
    if np.any(values < limits[:, 0] - 1e-8) or np.any(values > limits[:, 1] + 1e-8):
        raise ValueError(f"{limb['name']}: target violates joint limits: {np.degrees(values).tolist()}")
    return values


def endpoints(q, root):
    ts = transforms(q, root)
    return np.array([ts[l['name'] + '_lower'][1] + ts[l['name'] + '_lower'][0] @
                     np.array([0., 0., -l['lengths_mm'][1]]) for l in LIMBS])


def hull(points):
    points = sorted(set(tuple(p) for p in points))
    if len(points) < 3:
        return []
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def support_margin(points, com):
    polygon = hull(points)
    if len(polygon) < 3:
        return None
    distances = []
    for p, n in zip(polygon, polygon[1:] + polygon[:1]):
        dx, dy = n[0] - p[0], n[1] - p[1]
        distances.append((dx * (com[1] - p[1]) - dy * (com[0] - p[0])) / math.hypot(dx, dy))
    return min(distances)


def statics(q, root, contacts, active, mass_links):
    ts = transforms(q, root)
    if set(mass_links) != set(ts):
        raise ValueError(f"Mass links differ from design links: {set(mass_links) ^ set(ts)}")
    world_com = {name: rotation @ np.asarray(mass_links[name]['com_mm']) + origin
                 for name, (rotation, origin) in ts.items()}
    mass = sum(part['mass_kg'] for part in mass_links.values())
    com = sum(world_com[name] * part['mass_kg'] for name, part in mass_links.items()) / mass
    contact_ids = np.flatnonzero(active)
    points = np.asarray(contacts)[contact_ids]
    # Pure vertical contact forces only: this is quasi-static, with no friction claim.
    equilibrium = np.vstack([np.ones(len(points)), points[:, 0] / 1000, points[:, 1] / 1000])
    target = mass * 9.81 * np.array([1, com[0] / 1000, com[1] / 1000])
    moment = np.zeros((8, len(points)))
    self_weight = np.zeros(8)
    for i, limb in enumerate(LIMBS):
        upper, lower = limb['name'] + '_upper', limb['name'] + '_lower'
        for j, joint in enumerate([ts[upper][1], ts[lower][1]]):
            for name in ([upper, lower] if j == 0 else [lower]):
                self_weight[2 * i + j] -= mass_links[name]['mass_kg'] * 9.81 * (world_com[name][0] - joint[0]) / 1000
            if i in contact_ids:
                moment[2 * i + j, np.flatnonzero(contact_ids == i)[0]] = (contacts[i][0] - joint[0]) / 1000
    # Minimize the largest absolute actuator torque over valid load distributions.
    constraints = np.vstack([np.column_stack([moment, -np.ones(8)]),
                             np.column_stack([-moment, -np.ones(8)])])
    result = linprog(np.r_[np.zeros(len(points)), 1.], A_ub=constraints,
                     b_ub=np.r_[-self_weight, self_weight],
                     A_eq=np.column_stack([equilibrium, np.zeros(3)]), b_eq=target,
                     bounds=[(0, None)] * (len(points) + 1), method='highs')
    margin = support_margin(points[:, :2], com[:2])
    forces = np.zeros(4)
    torques = None
    if result.success:
        forces[contact_ids] = result.x[:-1]
        torques = moment @ result.x[:-1] + self_weight
    return {'mass_kg': mass, 'com_mm': com.tolist(), 'support_margin_mm': margin,
            'support_dimension': 2 if len(hull(points[:, :2])) >= 3 else 1,
            'vertical_force_equilibrium': bool(result.success),
            'force_solver_message': result.message, 'normal_force_N': forces.tolist() if result.success else None,
            'joint_torque_Nm': torques.tolist() if result.success else None,
            'peak_abs_torque_Nm': float(np.max(np.abs(torques))) if result.success else None}


def neutral_contacts():
    return np.array([[55. if 'arm' in l['name'] else -40., l['origin_mm'][1], PAD_RADIUS_MM] for l in LIMBS])


def scan_neutral():
    result = []
    for height in np.arange(122., 143., 1.):
        try:
            q = np.concatenate([ik(l, [0, 0, height], p) for l, p in zip(LIMBS, neutral_contacts())])
            result.append({'root_z_mm': float(height), 'joint_deg': np.degrees(q).tolist()})
        except ValueError:
            continue
    return result


def smooth(t):
    return t * t * (3 - 2 * t)


class Planner:
    def __init__(self, fps, mass_links):
        self.fps, self.mass_links = fps, mass_links
        self.root = np.array([0., 0., ROOT_HEIGHT_MM])
        self.contacts = neutral_contacts()
        self.frames = []
        self.q = np.concatenate([ik(l, self.root, p) for l, p in zip(LIMBS, self.contacts)])

    def append(self, stage, active, q_override=None):
        q = np.concatenate([ik(l, self.root, p) if q_override is None or i not in q_override else q_override[i]
                            for i, (l, p) in enumerate(zip(LIMBS, self.contacts))])
        limits = np.radians(np.array([pair for limb in LIMBS for pair in limb['limits_deg']]))
        if np.any(q < limits[:, 0] - 1e-8) or np.any(q > limits[:, 1] + 1e-8):
            raise ValueError(f'{stage}: joint interpolation violates limits')
        actual = endpoints(q, self.root)
        if np.any(actual[:, 2] < PAD_RADIUS_MM - 1e-6):
            raise ValueError(f'{stage}: pad center lies below the ground clearance')
        residual = np.linalg.norm(actual[np.asarray(active, dtype=bool)] - self.contacts[np.asarray(active, dtype=bool)], axis=1)
        frame = {'time_s': len(self.frames) / self.fps, 'stage': stage, 'root_mm': self.root.tolist(),
                 'joint_rad': q.tolist(), 'end_center_mm': actual.tolist(), 'contact_mask': list(active),
                 'contact_error_mm': float(np.max(residual))}
        if self.mass_links is not None:
            frame['statics'] = statics(q, self.root, actual, active, self.mass_links)
        self.frames.append(frame)
        self.q = q

    def move_root(self, stage, target, duration):
        start = self.root.copy()
        for alpha in np.linspace(0, 1, round(duration * self.fps) + 1)[1:]:
            self.root = start + smooth(alpha) * (np.asarray(target) - start)
            self.append(stage, [1, 1, 1, 1])

    def step(self, stage, limb_index, advance, lift, duration):
        start = self.contacts[limb_index].copy()
        active = [1, 1, 1, 1]
        active[limb_index] = 0
        for alpha in np.linspace(0, 1, round(duration * self.fps) + 1)[1:]:
            self.contacts[limb_index] = start + np.array([advance * smooth(alpha), 0, lift * math.sin(math.pi * alpha) ** 2])
            self.append(stage, active if alpha < 1 else [1, 1, 1, 1])

    def arm_joint_motion(self, stage, target_deg, duration):
        start = self.q[:2].copy()
        target = np.radians(target_deg)
        for alpha in np.linspace(0, 1, round(duration * self.fps) + 1)[1:]:
            q = start + smooth(alpha) * (target - start)
            self.append(stage, [0, 1, 1, 1], {0: q})


def make_walk(fps, mass_links):
    planner = Planner(fps, mass_links)
    planner.append('neutral', [1, 1, 1, 1])
    planner.move_root('lower_for_reach', [0, 0, 132], 1)
    planner.move_root('both_palms_push_body_12mm', [12, 0, 132], 1.5)
    planner.move_root('shift_forward_for_rear_steps', [30, 0, 132], 1)
    planner.step('left_rear_step', 2, 12, 8, 1)
    planner.step('right_rear_step', 3, 12, 8, 1)
    planner.move_root('shift_back_for_hand_steps', [-18, 0, 130], 2)
    planner.step('left_hand_step', 0, 12, 8, 1)
    planner.step('right_hand_step', 1, 12, 8, 1)
    planner.move_root('finish_translated_neutral', [12, 0, ROOT_HEIGHT_MM], 2)
    return planner.frames


def make_wave(fps, mass_links):
    planner = Planner(fps, mass_links)
    planner.append('neutral', [1, 1, 1, 1])
    planner.move_root('shift_back_for_wave', [-27, 0, 130], 2)
    stance_q = np.degrees(planner.q[:2]).tolist()
    planner.arm_joint_motion('raise_left_hand', [-115, 50], 1.5)
    for cycle in range(2):
        planner.arm_joint_motion(f'wave_{cycle + 1}_forward', [-125, 40], 1)
        planner.arm_joint_motion(f'wave_{cycle + 1}_back', [-110, 70], 1)
    planner.arm_joint_motion('lower_left_hand', stance_q, 1.5)
    planner.append('all_contacts_restored', [1, 1, 1, 1])
    planner.move_root('return_neutral', [0, 0, ROOT_HEIGHT_MM], 2)
    return planner.frames


def double_palms_pose(mass_links):
    """Search a single static feet-raised pose; this is not a swing trajectory."""
    if mass_links is None:
        return {'status': 'pending mass link file', 'dynamics_validated': False}
    mass = sum(part['mass_kg'] for part in mass_links.values())
    contacts = neutral_contacts()
    candidates = []
    for height in range(112, 139, 2):
        for hip in range(5, 86, 10):
            for knee in range(-125, -44, 10):
                def evaluate(root_x):
                    root = np.array([root_x, 0., float(height)])
                    arm = ik(LIMBS[0], root, contacts[0])
                    q = np.r_[arm, arm, np.radians([hip, knee, hip, knee])]
                    ts = transforms(q, root)
                    com = sum((ts[name][0] @ np.asarray(part['com_mm']) + ts[name][1]) * part['mass_kg']
                              for name, part in mass_links.items()) / mass
                    return com[0] - contacts[0, 0], q, root
                bracket = []
                for root_x in range(10, 91, 10):
                    try:
                        delta, _, _ = evaluate(root_x)
                        bracket.append((root_x, delta))
                    except ValueError:
                        continue
                for left, right in zip(bracket, bracket[1:]):
                    if left[1] * right[1] > 0:
                        continue
                    root_x = brentq(lambda value: evaluate(value)[0], left[0], right[0], xtol=1e-10)
                    _, q, root = evaluate(root_x)
                    actual = endpoints(q, root)
                    clearance = float(min(actual[2:, 2]) - PAD_RADIUS_MM)
                    # Arc ends at local z=-3 mm: the downward normal must remain inside the arc.
                    if clearance < 8 or abs(q[0] + q[1]) > math.acos(3 / PAD_RADIUS_MM):
                        continue
                    static = statics(q, root, actual, [1, 1, 0, 0], mass_links)
                    if not static['vertical_force_equilibrium']:
                        continue
                    candidates.append({'root_mm': root.tolist(), 'joint_rad': q.tolist(),
                                       'joint_deg': np.degrees(q).tolist(), 'end_center_mm': actual.tolist(),
                                       'contact_mask': [1, 1, 0, 0], 'rear_pad_clearance_mm': clearance,
                                       'statics': static})
                    break
    candidates.sort(key=lambda pose: pose['statics']['peak_abs_torque_Nm'])
    return {'status': 'static_candidates_found' if candidates else 'no_static_candidate_found',
            'candidate_count': len(candidates), 'best_candidates': candidates[:10],
            'fore_aft_point_support_margin_mm': 0., 'entry_transition_validated': False,
            'self_collision_validated': False, 'dynamics_validated': False, 'hardware_validated': False,
            'interpretation': 'Feet-raised static equilibrium at one configuration. CoM lies on the two-palm line; '
                              'fore-aft point-contact stability margin is zero. This does not establish a forward swing.'}


def write_motion(destination, frames, fps):
    destination.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(destination / 'motion.npz', time_s=[f['time_s'] for f in frames],
                        joint_pos_rad=[f['joint_rad'] for f in frames], joint_names=np.array(JOINT_NAMES),
                        root_pos_m=np.array([f['root_mm'] for f in frames]) / 1000,
                        root_quat_wxyz=np.tile([1., 0., 0., 0.], (len(frames), 1)),
                        contact_mask=[f['contact_mask'] for f in frames],
                        end_center_m=np.array([f['end_center_mm'] for f in frames]) / 1000,
                        reference_fps=float(fps))
    with (destination / 'poses.csv').open('w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['time_s', 'stage', 'root_x_mm', 'root_y_mm', 'root_z_mm'] +
                        [name + '_deg' for name in JOINT_NAMES] + [l['name'] + '_contact' for l in LIMBS])
        for frame in frames:
            writer.writerow([frame['time_s'], frame['stage']] + frame['root_mm'] +
                            np.degrees(frame['joint_rad']).tolist() + frame['contact_mask'])
    (destination / 'poses.json').write_text(json.dumps(frames, indent=2) + '\n')
    static_frames = [f['statics'] for f in frames if 'statics' in f]
    failed = [i for i, f in enumerate(frames) if 'statics' in f and not f['statics']['vertical_force_equilibrium']]
    overload = [i for i, f in enumerate(frames) if 'statics' in f and
                f['statics']['peak_abs_torque_Nm'] is not None and f['statics']['peak_abs_torque_Nm'] > 0.10]
    torques = [f['peak_abs_torque_Nm'] for f in static_frames if f['peak_abs_torque_Nm'] is not None]
    margins = [f['support_margin_mm'] for f in static_frames if f['support_margin_mm'] is not None]
    report = {'reference_fps': fps, 'source_fps': None, 'simulation_timestep': None, 'control_decimation': None,
              'policy_frequency': None, 'joint_order': JOINT_NAMES, 'frame': '+X forward, +Y left, +Z up',
              'joint_axes': '+Y for all eight joints', 'rotation': 'joint radians; root quaternion wxyz',
              'scale': 'CAD mm converted to SI m in NPZ; no motion retarget scale',
              'root_alignment': 'world initial root x=y=0, ground z=0; fixed root orientation',
              'frame_count': len(frames), 'duration_s': frames[-1]['time_s'],
              'maximum_contact_error_mm': max(f['contact_error_mm'] for f in frames),
              'kinematics': 'all sampled poses satisfy configured joint limits and required contact positions',
              'mass_validation': 'computed from supplied mass link file' if static_frames else 'pending mass link file',
              'total_mass_kg': static_frames[0]['mass_kg'] if static_frames else None,
              'infeasible_static_frame_indices': failed,
              'frames_above_sustained_torque_target': overload,
              'quasistatic_support_feasible': not failed if static_frames else None,
              'quasistatic_torque_target_met': not failed and not overload if static_frames else None,
              'minimum_point_support_margin_mm': min(margins) if margins else None,
              'support_margin_target_mm': 10.,
              'support_margin_target_met': bool(min(margins) >= 10) if margins else None,
              'maximum_quasistatic_joint_torque_Nm': max(torques) if torques else None,
              'sustained_design_target_Nm': 0.10,
              'dynamics_validated': False, 'self_collision_validated': False, 'hardware_validated': False,
              'limitations': ['Sampled kinematics are not a continuous collision proof.',
                              'Statics use vertical forces only and point contact centers; no slip or impact validation.']}
    if destination.name == 'supported_palm_walk':
        report['limitations'].append('Gait retains supporting feet; it does not prove a two-hand airborne swing.')
    elif destination.name == 'left_hand_wave':
        report['limitations'].append('Wave is in the sagittal plane with the other hand and both feet supporting.')
    (destination / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mass-file', type=Path, help='JSON mapping design link name to mass_kg/com_mm')
    parser.add_argument('--out', type=Path, default=OUT / 'motions')
    parser.add_argument('--fps', type=int, default=25, help='Reference sampling rate; not hardware policy frequency')
    args = parser.parse_args()
    if args.fps <= 0:
        parser.error('--fps must be positive')
    mass_links = json.loads(args.mass_file.read_text()) if args.mass_file else None
    if mass_links is not None:
        if any(float(part['mass_kg']) < 0 for part in mass_links.values()) or sum(float(part['mass_kg']) for part in mass_links.values()) <= 0:
            parser.error('Mass link values must be nonnegative with a positive total mass')
    args.out.mkdir(parents=True, exist_ok=True)
    if mass_links is not None:
        (args.out / 'masslinks_used.json').write_text(json.dumps(mass_links, indent=2) + '\n')
    (args.out / 'design_used.json').write_text(json.dumps({'limbs': LIMBS, 'joint_names': JOINT_NAMES,
                                                         'pad_radius_mm': PAD_RADIUS_MM,
                                                         'neutral_root_height_mm': ROOT_HEIGHT_MM}, indent=2) + '\n')
    (args.out / 'neutral_scan.json').write_text(json.dumps(scan_neutral(), indent=2) + '\n')
    reports = {}
    for name, generator in [('supported_palm_walk', make_walk), ('left_hand_wave', make_wave)]:
        frames = generator(args.fps, mass_links)
        reports[name] = write_motion(args.out / name, frames, args.fps)
    palms = double_palms_pose(mass_links)
    (args.out / 'double_palms_only_static_search.json').write_text(json.dumps(palms, indent=2) + '\n')
    if palms.get('best_candidates'):
        best = palms['best_candidates'][0]
        best_frame = {'time_s': 0., 'stage': 'double_palms_only_static_pose', 'contact_error_mm': 0., **best}
        report = write_motion(args.out / 'double_palms_only_static_pose', [best_frame], args.fps)
        report['limitations'].append(palms['interpretation'])
        report['entry_transition_validated'] = False
        report['fore_aft_point_support_margin_mm'] = 0.
        report['support_margin_target_met'] = False
        (args.out / 'double_palms_only_static_pose' / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        reports['double_palms_only_static_pose'] = report
    print(json.dumps(reports, indent=2))
    if any(reports[name]['quasistatic_support_feasible'] is False or reports[name]['quasistatic_torque_target_met'] is False
           or reports[name]['support_margin_target_met'] is False
           for name in ('supported_palm_walk', 'left_hand_wave')):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
