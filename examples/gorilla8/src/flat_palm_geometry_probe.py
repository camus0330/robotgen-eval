"""Independent static envelope probe; does not edit the manufacturing CAD."""
import json
import math

import cadquery as cq
import fcl
import numpy as np

from design import REPORTS, transforms
from verify_assembly import is_stock_bearing_pair, load_exact, load_objects, locate_shape


records = load_objects()
load_exact(records)
by_name = {o['name']: o for o in records}
cache = {}
box_cache = {}


def common(a, b, ts):
    ra, ta = ts[a['link']]
    rb, tb = ts[b['link']]
    r, t = ra.T @ rb, ra.T @ (tb - ta)
    key = (a['name'], b['name'], *np.round(r.ravel(), 8), *np.round(t, 8))
    if key not in cache:
        cache[key] = max(0.0, a['shape'].intersect(locate_shape(b['shape'], r, t)).Volume())
    return cache[key]


def overlap(aa, bb):
    return not (np.any(aa[1] < bb[0] - 1e-6) or np.any(bb[1] < aa[0] - 1e-6))


def box_conflicts(extension, ts, bounds):
    conflicts = []
    for side, y in [('left', 56), ('right', -56)]:
        low = np.array([55-extension, y-17, 0.])
        high = np.array([75., y+17, 9.])
        box = fcl.CollisionObject(fcl.Box(extension+20, 34, 9), fcl.Transform((low+high)/2))
        shape = cq.Solid.makeBox(extension+20, 34, 9, cq.Vector(*low))
        for o in records:
            # The proposed pad replaces the current pad; its rigid carrier remains checked.
            if o['name'] == f'{side}_arm_P06_palm_pad':
                continue
            if not overlap((low, high), bounds[o['name']]):
                continue
            if not fcl.collide(box, o['fcl_obj'], fcl.CollisionRequest(), fcl.CollisionResult()):
                continue
            r, t = ts[o['link']]
            key = (extension, side, o['name'], *np.round(r.ravel(), 8), *np.round(t, 8))
            if key not in box_cache:
                box_cache[key] = max(0.0, shape.intersect(locate_shape(o['shape'], r, t)).Volume())
            if box_cache[key] > 1e-3:
                conflicts.append({'palm': side, 'part': o['name'], 'intersection_mm3': box_cache[key]})
    return conflicts


rows = []
for shoulder in [-25, -20, -15, -10, -5]:
    for hip in range(40, 76, 5):
        for knee in range(-80, -121, -5):
            q = np.radians([shoulder, -shoulder]*2 + [hip, knee]*2)
            a = math.radians(shoulder)
            root = np.array([35+60*math.sin(a), 0., 88+60*math.cos(a)])
            ts = transforms(q, root)
            bounds = {}
            foot_clearances = {}
            for o in records:
                r, t = ts[o['link']]
                o['fcl_obj'].setTransform(fcl.Transform(r, t))
                v = o['mesh_obj'].vertices @ r.T + t
                bounds[o['name']] = np.array([v.min(0), v.max(0)])
                if 'leg_P07_foot_pad' in o['name']:
                    foot_clearances[o['name']] = float(v[:, 2].min())
            row = {'shoulder_deg': shoulder, 'elbow_deg': -shoulder,
                   'hip_deg': hip, 'knee_deg': knee, 'root_mm': root.tolist(),
                   'min_foot_clearance_mm': min(foot_clearances.values()),
                   'body_interference': [], 'envelope_interference': [],
                   'body_min_z_mm': min(float(v[0,2]) for v in bounds.values())}
            if row['min_foot_clearance_mm'] <= 5:
                row['eligible'] = False
                row['reason'] = 'rear foot clearance <= 5 mm'
                rows.append(row)
                continue
            for i, first in enumerate(records):
                for second in records[i+1:]:
                    if first['link'] == second['link'] or is_stock_bearing_pair(first['name'], second['name']):
                        continue
                    if not overlap(bounds[first['name']], bounds[second['name']]):
                        continue
                    if not fcl.collide(first['fcl_obj'], second['fcl_obj'], fcl.CollisionRequest(), fcl.CollisionResult()):
                        continue
                    volume = common(first, second, ts)
                    if volume > 1e-3:
                        row['body_interference'].append({'pair': [first['name'], second['name']], 'intersection_mm3': volume})
            row['envelope_interference'] = box_conflicts(45, ts, bounds)
            row['eligible'] = not row['body_interference'] and not row['envelope_interference'] and row['body_min_z_mm'] >= -0.05
            if row['eligible']:
                far = box_conflicts(250, ts, bounds)
                if not far:
                    row['rear_extension_clear_through_mm'] = 250
                    row['rear_extension_first_collision_mm'] = None
                else:
                    low, high = 45., 250.
                    while high-low > 0.1:
                        mid = (low+high)/2
                        if box_conflicts(mid, ts, bounds):
                            high = mid
                        else:
                            low = mid
                    row['rear_extension_clear_through_mm'] = low
                    row['rear_extension_first_collision_mm'] = high
                    row['rear_extension_limiting_parts'] = box_conflicts(high, ts, bounds)
            rows.append(row)
    selected = [r for r in rows if r['shoulder_deg'] == shoulder]
    print(json.dumps({'shoulder_deg': shoulder, 'tested': len(selected), 'eligible': sum(r['eligible'] for r in selected)}, ensure_ascii=False), flush=True)

groups = []
for hip in range(40, 76, 5):
    for knee in range(-80, -121, -5):
        selected = [r for r in rows if r['hip_deg'] == hip and r['knee_deg'] == knee]
        if all(r['eligible'] for r in selected):
            groups.append({'hip_deg': hip, 'knee_deg': knee,
                           'minimum_foot_clearance_all_shoulders_mm': min(r['min_foot_clearance_mm'] for r in selected),
                           'rear_extension_clear_all_shoulders_mm': min(r['rear_extension_clear_through_mm'] for r in selected)})
report = {
    'purpose': 'Static candidate envelope only; no manufacturing CAD changed and no dynamics claim',
    'units': {'length': 'mm', 'angle': 'deg', 'volume': 'mm^3'},
    'method': 'Delivered mesh FCL candidates and exact STEP BREP intersection on all candidates; actual mesh vertices for ground/foot clearance.',
    'root_orientation': 'identity; world +X forward, +Y left, +Z up',
    'root_formula': 'x=35+60*sin(shoulder); z=88+60*cos(shoulder)',
    'flat_palm_box_relative_end_mm': {'x': [-45,20], 'y': [-17,17], 'z': [-12,-3]},
    'flat_palm_box_world_mm': {'left': [[10,39,0],[75,73,9]], 'right': [[10,-73,0],[75,-39,9]]},
    'own_attachment_exceptions': 'Each future envelope replaces only its own P06 pad. Its own P03 rigid carrier and every other object remain checked.',
    'same_link_existing_parts': 'Previously exhaustive-validated fixed assembly; only changing cross-link pairs are rescanned here.',
    'source_oem_bearing_exceptions': 'Matching original motor case/rotor pairs only, preserving source bearing engagement.',
    'intersection_tolerance_mm3': 0.001,
    'required_rear_foot_clearance_mm': 5,
    'envelope_ground': 'Bottom plane exactly z=0 in every candidate pose; no penetration.',
    'candidate_count': len(rows), 'eligible_count': sum(r['eligible'] for r in rows),
    'fixed_leg_postures_valid_at_all_5_shoulders': groups,
    'candidates': rows,
    'limitations': ['Discrete static poses, not a continuous trajectory.',
                    'Envelope is not an engineered pad/carrier and omits fasteners/cables.',
                    '250 mm extension is only a geometric search bound, not a manufacture or strength recommendation.',
                    'No balance, motor torque or dynamics validation.']
}
path = REPORTS/'flat_palm_geometry_probe.json'
path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps({'report': str(path), 'eligible': report['eligible_count'], 'fixed_leg_postures': groups}, ensure_ascii=False), flush=True)
