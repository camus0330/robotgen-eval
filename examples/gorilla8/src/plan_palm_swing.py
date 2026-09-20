"""Independent two-palm transfer attempt; existing supported motions are untouched."""
from __future__ import annotations

import json
import traceback

import numpy as np
from scipy.optimize import brentq

from design import LIMBS, OUT, PAD_RADIUS_MM, REPORTS, transforms
from plan_motion import Planner, endpoints, ik, neutral_contacts, smooth, write_motion


def center_of_mass(q, root, mass_links):
    ts = transforms(q, root)
    mass = sum(part['mass_kg'] for part in mass_links.values())
    return sum((ts[name][0] @ np.asarray(part['com_mm']) + ts[name][1]) * part['mass_kg']
               for name, part in mass_links.items()) / mass


def palm_line_pose(height, contacts, mass_links, rear_q=None):
    def evaluate(root_x):
        root = np.array([root_x, 0., height])
        q = np.concatenate([ik(limb, root, contact) if index < 2 or rear_q is None else rear_q
                            for index, (limb, contact) in enumerate(zip(LIMBS, contacts))])
        return center_of_mass(q, root, mass_links)[0] - contacts[0, 0], q, root
    bracket = []
    for root_x in np.arange(0., 92., 1.):
        try:
            bracket.append((root_x, evaluate(root_x)[0]))
        except ValueError:
            continue
    for left, right in zip(bracket, bracket[1:]):
        if left[1] * right[1] > 0:
            continue
        root_x = brentq(lambda value: evaluate(value)[0], left[0], right[0], xtol=1e-10)
        _, q, root = evaluate(root_x)
        return q, root
    raise ValueError(f'No reachable pose with CoM on palm line at root z={height} mm')


def fixed_rear_entry_scan(mass_links):
    contacts = neutral_contacts()
    results = []
    for height in [106., 108., 112., 114., 116., 118.]:
        candidates = []
        for root_x in np.arange(0., 91., .25):
            root = np.array([root_x, 0., height])
            try:
                q = np.concatenate([ik(l, root, p) for l, p in zip(LIMBS, contacts)])
            except ValueError:
                continue
            candidates.append((float(center_of_mass(q, root, mass_links)[0]), float(root_x)))
        maximum, root_x = max(candidates)
        results.append({'root_z_mm': height, 'maximum_reachable_com_x_mm': maximum,
                        'root_x_at_maximum_mm': root_x, 'required_com_x_mm': 55.,
                        'grid_resolution_mm': .25, 'palm_line_reached_in_grid': maximum >= 55.})
    return results


def generate(mass_links, fps=25):
    planner = Planner(fps, mass_links)
    planner.append('neutral', [1, 1, 1, 1])
    planner.move_root('lower_for_rear_step_setup', [0, 0, 128], 1.5)
    planner.move_root('forward_weight_shift_for_rear_steps', [46, 0, 128], 2.5)
    planner.step('left_rear_pre_step', 2, 45, 10, 1.5)
    planner.step('right_rear_pre_step', 3, 45, 10, 1.5)

    entry_q, entry_root = palm_line_pose(134., planner.contacts, mass_links)
    planner.move_root('unload_both_rear_feet', entry_root, 2.5)
    rear_start = entry_q[4:6]
    rear_apex = np.radians([75., -85.])
    for alpha in np.linspace(0, 1, 2 * fps + 1)[1:]:
        blend = smooth(alpha)
        rear_q = rear_start * (1 - blend) + rear_apex * blend
        _, planner.root = palm_line_pose(134. + 3 * blend, planner.contacts, mass_links, rear_q)
        planner.append('both_feet_airborne_forward_transfer', [1, 1, 0, 0], {2: rear_q, 3: rear_q})
    for _ in range(round(.4 * fps)):
        planner.append('both_feet_airborne_apex', [1, 1, 0, 0], {2: rear_apex, 3: rear_apex})

    landing_contacts = planner.contacts.copy()
    landing_contacts[2:, 0] = -5.
    landing_q, _ = palm_line_pose(134., landing_contacts, mass_links)
    rear_landing = landing_q[4:6]
    for alpha in np.linspace(0, 1, 2 * fps + 1)[1:]:
        blend = smooth(alpha)
        rear_q = rear_apex * (1 - blend) + rear_landing * blend
        _, planner.root = palm_line_pose(137. - 3 * blend, planner.contacts, mass_links, rear_q)
        planner.append('lower_rear_feet_to_forward_landings', [1, 1, 0, 0], {2: rear_q, 3: rear_q})
    planner.contacts = landing_contacts
    planner.append('rear_feet_landed', [1, 1, 1, 1])
    planner.move_root('settle_on_four_contacts', [42., 0., 137.], 2.)
    for _ in range(2 * fps):
        planner.append('final_four_contact_hold', [1, 1, 1, 1])
    return planner.frames, entry_root


def main():
    destination = OUT / 'motions' / 'palm_swing'
    destination.mkdir(parents=True, exist_ok=True)
    mass_links = json.loads((REPORTS / 'masslinks.json').read_text())
    (destination / 'masslinks_used.json').write_text(json.dumps(mass_links, indent=2) + '\n')
    (destination / 'design_used.json').write_text(json.dumps({'limbs': LIMBS, 'pad_radius_mm': PAD_RADIUS_MM}, indent=2) + '\n')
    scan = fixed_rear_entry_scan(mass_links)
    (destination / 'fixed_rear_feet_entry_scan.json').write_text(json.dumps(scan, indent=2) + '\n')
    try:
        frames, entry_root = generate(mass_links)
        report = write_motion(destination, frames, 25)
        air = [frame for frame in frames if frame['contact_mask'] == [1, 1, 0, 0]]
        transfer = [frame for frame in frames if frame['stage'] == 'both_feet_airborne_forward_transfer']
        apex = transfer[-1]
        contact_error = max(abs(frame['statics']['com_mm'][0] - 55.) for frame in air)
        report.update({
            'role': 'independent_two_palm_transfer_attempt',
            'default_supported_motions_unchanged': True,
            'palm_only_entry_root_mm': entry_root.tolist(),
            'palm_only_start_time_s': air[0]['time_s'],
            'palm_only_end_time_s': air[-1]['time_s'],
            'airborne_apex_body_forward_mm': apex['root_mm'][0] - float(entry_root[0]),
            'airborne_landing_body_net_forward_mm': air[-1]['root_mm'][0] - float(entry_root[0]),
            'maximum_rear_pad_center_clearance_mm': max(min(np.array(f['end_center_mm'])[2:, 2]) - PAD_RADIUS_MM for f in air),
            'maximum_palm_line_com_error_mm': contact_error,
            'total_body_forward_mm': frames[-1]['root_mm'][0] - frames[0]['root_mm'][0],
            'rear_foot_net_advance_mm': 35.,
            'fore_aft_point_support_margin_during_palm_only_mm': 0.,
            'dynamic_forward_transfer_verified': False,
        })
        report['limitations'].extend([
            'The rear feet pre-step forward before unloading; only the later palm-only stage is the swing attempt.',
            'CoM alignment gives zero fore-aft point-contact stability margin and does not prove dynamic balance.',
            'Positive body movement is prescribed kinematics until checked in a free-base physical simulation.',
            'The 0.10 Nm target is a conservative estimated continuous target, not a tested hardware rating.',
        ])
        (destination / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        (destination / 'attempt_status.json').write_text(json.dumps({'status': 'trajectory_generated', 'frame_count': len(frames)}, indent=2) + '\n')
        print(json.dumps(report, indent=2))
        if not report['quasistatic_support_feasible'] or not report['quasistatic_torque_target_met']:
            raise SystemExit(2)
    except Exception as error:
        (destination / 'attempt_status.json').write_text(json.dumps({'status': 'generation_failed', 'error': str(error),
                                                                    'traceback': traceback.format_exc()}, indent=2) + '\n')
        raise


if __name__ == '__main__':
    main()
