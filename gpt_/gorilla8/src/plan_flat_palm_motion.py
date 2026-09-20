"""Independent flat-palm references with finite-area contact statics."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import linprog

from design import (JOINT_NAMES, LIMBS, OUT, PAD_RADIUS_MM, PALM_WIDTH_MM,
                    PALM_X_MAX_MM, PALM_X_MIN_MM, REPORTS, transforms)
from plan_motion import endpoints, ik, smooth, support_margin, write_motion

PALM_X = [PALM_X_MIN_MM, PALM_X_MAX_MM]
PALM_HALF_WIDTH = PALM_WIDTH_MM / 2.
NEUTRAL_SHOULDER_DEG = -10.
OLD_NEUTRAL_X = 35. + 60. * math.sin(math.radians(NEUTRAL_SHOULDER_DEG))
HAND_X = 55. - OLD_NEUTRAL_X
FOOT_X = -5. - OLD_NEUTRAL_X


def flat_root(shoulder_deg):
    angle = math.radians(shoulder_deg)
    return np.array([35. + 60. * math.sin(angle) - OLD_NEUTRAL_X, 0., 88. + 60. * math.cos(angle)])


def flat_statics(q, root, active, mass_links):
    ts = transforms(q, root)
    ends = endpoints(q, root)
    world_com = {name: ts[name][0] @ np.asarray(part['com_mm']) + ts[name][1]
                 for name, part in mass_links.items()}
    mass = sum(part['mass_kg'] for part in mass_links.values())
    com = sum(world_com[name] * part['mass_kg'] for name, part in mass_links.items()) / mass
    points, owners = [], []
    for index, contacting in enumerate(active):
        if not contacting:
            continue
        if index < 2:
            if abs(q[2 * index] + q[2 * index + 1]) > 1e-7:
                raise ValueError('A supporting flat palm must remain parallel to the ground')
            for dx in PALM_X:
                for dy in [-PALM_HALF_WIDTH, PALM_HALF_WIDTH]:
                    points.append(ends[index, :2] + [dx, dy])
                    owners.append(index)
        else:
            points.append(ends[index, :2])
            owners.append(index)
    points, owners = np.array(points), np.array(owners)
    equilibrium = np.vstack([np.ones(len(points)), points[:, 0] / 1000, points[:, 1] / 1000])
    target = mass * 9.81 * np.array([1, com[0] / 1000, com[1] / 1000])
    # Keep each palm's lateral CoP centered; optimize its fore-aft CoP and load.
    for index in [0, 1]:
        if active[0] and active[1]:
            row = np.where(owners == index, (points[:, 1] - ends[index, 1]) / 1000, 0.)
            equilibrium = np.vstack([equilibrium, row])
            target = np.r_[target, 0.]
    coefficients = np.zeros((8, len(points)))
    gravity = np.zeros(8)
    for index, limb in enumerate(LIMBS):
        upper, lower = limb['name'] + '_upper', limb['name'] + '_lower'
        for joint_index, joint in enumerate([ts[upper][1], ts[lower][1]]):
            for name in ([upper, lower] if joint_index == 0 else [lower]):
                gravity[2 * index + joint_index] -= mass_links[name]['mass_kg'] * 9.81 * (world_com[name][0] - joint[0]) / 1000
            selected = owners == index
            coefficients[2 * index + joint_index, selected] = (points[selected, 0] - joint[0]) / 1000
    result = linprog(np.r_[np.zeros(len(points)), 1.],
                     A_ub=np.vstack([np.c_[coefficients, -np.ones(8)], np.c_[-coefficients, -np.ones(8)]]),
                     b_ub=np.r_[-gravity, gravity], A_eq=np.c_[equilibrium, np.zeros(len(target))],
                     b_eq=target, bounds=[(0, None)] * (len(points) + 1), method='highs')
    forces, cop, torque = np.zeros(4), [None] * 4, None
    if result.success:
        loads = result.x[:-1]
        torque = coefficients @ loads + gravity
        for index in range(4):
            selected = owners == index
            forces[index] = sum(loads[selected])
            if forces[index] > 1e-10:
                cop[index] = (np.sum(points[selected] * loads[selected, None], axis=0) / forces[index]).tolist()
    return {'mass_kg': mass, 'com_mm': com.tolist(), 'support_margin_mm': support_margin(points, com[:2]),
            'vertical_force_equilibrium': bool(result.success), 'force_solver_message': result.message,
            'normal_force_N': forces.tolist() if result.success else None, 'contact_CoP_xy_mm': cop,
            'joint_torque_Nm': torque.tolist() if result.success else None,
            'peak_abs_torque_Nm': float(np.max(np.abs(torque))) if result.success else None,
            'contact_model': 'flat palm rectangle with optimized fore-aft CoP; rear rocker center points'}


class FlatPlanner:
    def __init__(self, mass_links, fps=25):
        self.mass_links, self.fps = mass_links, fps
        self.root = flat_root(NEUTRAL_SHOULDER_DEG)
        self.q = np.radians([NEUTRAL_SHOULDER_DEG, -NEUTRAL_SHOULDER_DEG] * 2 + [0., 0.] * 2)
        for index in [2, 3]:
            self.q[2 * index:2 * index + 2] = self.leg_ik(index, FOOT_X, PAD_RADIUS_MM)
        self.frames = []

    def leg_ik(self, index, x, z):
        return ik(LIMBS[index], self.root, [x, LIMBS[index]['origin_mm'][1], z])

    def append(self, stage, active):
        limits = np.radians(np.array([pair for limb in LIMBS for pair in limb['limits_deg']]))
        if np.any(self.q < limits[:, 0] - 1e-8) or np.any(self.q > limits[:, 1] + 1e-8):
            raise ValueError(f'{stage}: configured joint limits exceeded: {np.degrees(self.q).tolist()}')
        ends = endpoints(self.q, self.root)
        for index in range(4):
            if index < 2:
                angle = self.q[2 * index] + self.q[2 * index + 1]
                bottom = min(ends[index, 2] - math.sin(angle) * dx - PAD_RADIUS_MM * math.cos(angle) for dx in PALM_X)
            else:
                bottom = ends[index, 2] - PAD_RADIUS_MM
            if bottom < -1e-6:
                raise ValueError(f'{stage}: {LIMBS[index]["name"]} pad bottom below ground: {bottom} mm')
        residual = max(abs(ends[index, 2] - PAD_RADIUS_MM) for index in range(4) if active[index])
        self.frames.append({'time_s': len(self.frames) / self.fps, 'stage': stage, 'root_mm': self.root.tolist(),
                            'joint_rad': self.q.tolist(), 'end_center_mm': ends.tolist(), 'contact_mask': list(active),
                            'contact_error_mm': float(residual),
                            'statics': flat_statics(self.q, self.root, active, self.mass_links)})

    def hold(self, stage, active, duration):
        for _ in range(round(duration * self.fps)):
            self.append(stage, active)

    def ground_shift(self, target_shoulder, duration):
        start = math.degrees(self.q[0])
        for alpha in np.linspace(0, 1, round(duration * self.fps) + 1)[1:]:
            shoulder = start + smooth(alpha) * (target_shoulder - start)
            self.root = flat_root(shoulder)
            self.q[:4] = np.radians([shoulder, -shoulder] * 2)
            for index in [2, 3]:
                self.q[2 * index:2 * index + 2] = self.leg_ik(index, FOOT_X, PAD_RADIUS_MM)
            self.append('four_contact_prepare', [1, 1, 1, 1])

    def move_foot(self, index, target_xz, stage, active, duration):
        start = endpoints(self.q, self.root)[index, [0, 2]]
        target = np.asarray(target_xz)
        for alpha in np.linspace(0, 1, round(duration * self.fps) + 1)[1:]:
            pos = start + smooth(alpha) * (target - start)
            self.q[2 * index:2 * index + 2] = self.leg_ik(index, *pos)
            self.append(stage, active)

    def move_arm(self, target, stage, active, duration):
        start, target = self.q[:2].copy(), np.radians(target)
        for alpha in np.linspace(0, 1, round(duration * self.fps) + 1)[1:]:
            self.q[:2] = start + smooth(alpha) * (target - start)
            self.append(stage, active)


def swing(mass_links, end_shoulder):
    planner = FlatPlanner(mass_links)
    planner.append('flat_neutral', [1, 1, 1, 1])
    planner.hold('initial_four_contact_hold', [1, 1, 1, 1], 1.)
    planner.ground_shift(NEUTRAL_SHOULDER_DEG, 1.)
    rear_start = np.radians([50., -90.])
    air_q = planner.q.copy()
    air_q[4:6] = rear_start
    air_q[6:8] = rear_start
    raised_xz = endpoints(air_q, planner.root)[2, [0, 2]]
    for index in [2, 3]:
        active = [1, 1, 0, 1] if index == 2 else [1, 1, 0, 0]
        planner.move_foot(index, [FOOT_X, 24.], f'lift_{index}_clear_palm_extension', active, .8)
        planner.move_foot(index, raised_xz, f'lift_{index}_tuck', active, 1.2)
    flight_entry = planner.root.copy()
    rear_change = 10. * (end_shoulder - NEUTRAL_SHOULDER_DEG) / 20.
    rear_end = np.radians([50. + rear_change, -90. - rear_change])
    for alpha in np.linspace(0, 1, 76)[1:]:
        blend = smooth(alpha)
        shoulder = NEUTRAL_SHOULDER_DEG + (end_shoulder - NEUTRAL_SHOULDER_DEG) * blend
        planner.root = flat_root(shoulder)
        planner.q[:4] = np.radians([shoulder, -shoulder] * 2)
        planner.q[4:6] = rear_start * (1 - blend) + rear_end * blend
        planner.q[6:8] = planner.q[4:6]
        planner.append('both_feet_airborne_forward_stroke', [1, 1, 0, 0])
    planner.hold('airborne_end_hold', [1, 1, 0, 0], .4)
    for index in [2, 3]:
        active = [1, 1, 0, 0] if index == 2 else [1, 1, 1, 0]
        planner.move_foot(index, [FOOT_X - 3., 35.], f'land_{index}_behind_palm_extension', active, 1.)
        planner.move_foot(index, [FOOT_X, PAD_RADIUS_MM], f'land_{index}_lower', active, 1.)
        planner.append(f'land_{index}_contact_restored', [1, 1, 1, 0] if index == 2 else [1, 1, 1, 1])
    planner.hold('final_four_contact_hold', [1, 1, 1, 1], 2.4)
    return planner.frames, flight_entry


def wave(mass_links):
    planner = FlatPlanner(mass_links)
    planner.append('flat_neutral', [1, 1, 1, 1])
    planner.hold('initial_four_contact_hold', [1, 1, 1, 1], 1.)
    planner.ground_shift(-20., 1.)
    active = [0, 1, 1, 1]
    planner.move_arm([-75, 75], 'lift_hand_while_palm_parallel', active, 1.5)
    planner.move_arm([-115, 50], 'raise_left_hand', active, 1.2)
    for index in range(2):
        planner.move_arm([-125, 40], f'wave_{index + 1}_forward', active, 1.)
        planner.move_arm([-110, 70], f'wave_{index + 1}_back', active, 1.)
    planner.move_arm([-75, 75], 'restore_parallel_palm_above_ground', active, 1.2)
    planner.move_arm([-20, 20], 'lower_parallel_palm', active, 1.5)
    planner.append('all_contacts_restored', [1, 1, 1, 1])
    planner.ground_shift(NEUTRAL_SHOULDER_DEG, 1.)
    planner.hold('final_four_contact_hold', [1, 1, 1, 1], 2.4)
    return planner.frames


def save(name, frames, mass_links, extra):
    destination = OUT / 'motions' / name
    report = write_motion(destination, frames, 25)
    report.update(extra)
    report.update({'contact_model': f'front flat rectangles, each X{PALM_X} mm, Y[-{PALM_HALF_WIDTH},+{PALM_HALF_WIDTH}] mm; rear rocker points',
                   'sagittal_CoP_is_optimized': True, 'desired_static_margin_target_Nm': .08,
                   'desired_static_margin_target_met': report['maximum_quasistatic_joint_torque_Nm'] <= .08,
                   'neutral_root_mm': flat_root(NEUTRAL_SHOULDER_DEG).tolist(),
                   'neutral_joint_deg': np.degrees(frames[0]['joint_rad']).tolist()})
    report['limitations'] = ['Finite-area vertical-force statics do not establish dynamic tracking or hardware capability.',
                             'Exact modified CAD collision and free-base dynamics are separate required checks.',
                             'The reference is a finite forward stroke with both rear feet airborne; cyclic hand recovery is not implemented.']
    if name == 'flat_palm_wave':
        report['limitations'][-1] = 'The raised hand waves only in the sagittal plane while the other hand and rear feet support.'
    (destination / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    (destination / 'masslinks_used.json').write_text(json.dumps(mass_links, indent=2) + '\n')
    (destination / 'design_used.json').write_text(json.dumps({'limbs': LIMBS, 'joint_names': JOINT_NAMES,
                                                             'palm_x_mm': PALM_X, 'palm_half_width_mm': PALM_HALF_WIDTH,
                                                             'pad_radius_mm': PAD_RADIUS_MM}, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--end-shoulder-deg', type=float, default=10., help='Must be inside independently verified design limits')
    args = parser.parse_args()
    mass_links = json.loads((REPORTS / 'masslinks.json').read_text())
    frames, entry = swing(mass_links, args.end_shoulder_deg)
    active = [frame for frame in frames if frame['contact_mask'] == [1, 1, 0, 0]]
    reports = {'flat_palm_swing': save('flat_palm_swing', frames, mass_links,
        {'role': 'finite_flat_palm_airborne_forward_stroke', 'palm_only_start_time_s': active[0]['time_s'],
         'palm_only_end_time_s': active[-1]['time_s'], 'airborne_stroke_root_forward_mm': frames[-1]['root_mm'][0] - entry[0],
         'total_reference_root_forward_mm': frames[-1]['root_mm'][0],
         'dynamic_forward_transfer_verified': False})}
    reports['flat_palm_wave'] = save('flat_palm_wave', wave(mass_links), mass_links, {'role': 'flat_palm_supported_wave'})
    print(json.dumps(reports, indent=2))
    if any(not report['quasistatic_support_feasible'] or not report['quasistatic_torque_target_met'] for report in reports.values()):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
