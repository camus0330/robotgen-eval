#!/usr/bin/env python3
"""Read-only Gorilla8 evidence adapter. Standard library only; no CAD/simulation claims.

Reports are submission evidence (E1); recomputed trace/XML facts are E2.
This is a pilot audit, not a trusted simulator or a general robot evaluator.
"""
import argparse
import csv
import hashlib
import json
import math
import platform
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
CONFIG_ROOT = REPO_ROOT / 'configs' / 'benchmark'
DEFAULT_ROBOT_ROOT = REPO_ROOT / 'examples' / 'gorilla8'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def reject_constant(value):
    raise ValueError('Non-finite JSON constant: ' + value)


def norm(values):
    return math.sqrt(sum(v * v for v in values))


def segments(rows, predicate):
    out, start = [], None
    for i in range(len(rows) + 1):
        active = i < len(rows) and predicate(rows[i])
        if active and start is None:
            start = i
        if not active and start is not None:
            out.append(rows[start:i])
            start = None
    return out


def duration(rows):
    return rows[-1]['t'] - rows[0]['t'] if rows else 0.0


def trace_stats(rows, profile):
    if len(rows) < 2:
        raise ValueError('Trace must contain at least two frames')
    arrays = {'q': 8, 'target_q': 8, 'root': 3, 'target_root': 3,
              'root_linear_velocity_m_s': 3, 'root_angular_velocity_rad_s': 3,
              'torque': 8, 'joint_limit_force_abs_Nm': 8,
              'pad_contact': 4, 'pad_clearance_m': 4, 'pad_normal_force_N': 4}
    for r in rows:
        for key, count in arrays.items():
            if len(r[key]) != count:
                raise ValueError('Invalid vector length: ' + key)
            if key == 'pad_contact':
                if any(type(v) is not bool for v in r[key]):
                    raise ValueError('pad_contact must contain booleans')
            elif not all(isinstance(v, (int, float)) and math.isfinite(v) for v in r[key]):
                raise ValueError('Non-finite/non-numeric trace vector: ' + key)
        if not math.isfinite(r['t']) or not math.isfinite(r['up_z']):
            raise ValueError('Invalid time/orientation')
    for a, b in zip(rows, rows[1:]):
        if not math.isclose(b['t'] - a['t'], profile['sample_dt_s'], abs_tol=1e-7):
            raise ValueError('Non-monotone time or unexpected sampling gap')
    land = profile['landing']
    def stable(r):
        return (all(r['pad_contact']) and min(r['pad_normal_force_N']) > land['min_force_N']
                and r['nonpad_ground_contacts'] == 0 and r['up_z'] > land['min_up_z']
                and norm(r['root_linear_velocity_m_s']) < land['max_linear_speed_m_s']
                and norm(r['root_angular_velocity_rad_s']) < land['max_angular_speed_rad_s'])
    tail = []
    for r in reversed(rows):
        if not stable(r):
            break
        tail.append(r)
    landing_s = duration(list(reversed(tail)))
    s, w = profile['swing'], profile['wave']
    swings = segments(rows, lambda r: r['pad_contact'] == [True, True, False, False]
                      and min(r['pad_normal_force_N'][:2]) > land['min_force_N']
                      and min(r['pad_clearance_m'][2:]) > s['foot_clearance_m']
                      and r['nonpad_ground_contacts'] == 0)
    waves = segments(rows, lambda r: r['pad_contact'] == [False, True, True, True]
                     and min(r['pad_normal_force_N'][1:]) > land['min_force_N']
                     and r['pad_clearance_m'][0] > w['hand_clearance_m']
                     and r['nonpad_ground_contacts'] == 0)
    swing_events = [{'duration_s': duration(x), 'forward_mm': (x[-1]['root'][0] - x[0]['root'][0]) * 1000,
                     'min_foot_clearance_mm': min(min(r['pad_clearance_m'][2:]) for r in x) * 1000}
                    for x in swings]
    wave_events = [{'duration_s': duration(x), 'joint_excursions_rad':
                   [max(r['q'][j] for r in x) - min(r['q'][j] for r in x) for j in range(2)]}
                   for x in waves]
    no_cheat = (all(r['nonpad_ground_contacts'] == 0 for r in rows)
                and max(abs(v) for r in rows for v in r['joint_limit_force_abs_Nm']) <= profile['actuation']['max_limit_force_nm'])
    stable_landing = landing_s >= land['min_duration_s'] - 1e-9
    return {
        'frame_count': len(rows), 'duration_s': duration(rows), 'landing_s': landing_s,
        'forward_mm': (rows[-1]['root'][0] - rows[0]['root'][0]) * 1000,
        'swing_events': swing_events, 'wave_events': wave_events,
        'max_hand_height_mm': max(r['pad_clearance_m'][0] for r in rows) * 1000,
        'max_joint_error_deg': math.degrees(max(abs(a - b) for r in rows for a, b in zip(r['q'], r['target_q']))),
        'joint_rmse_deg': math.degrees(math.sqrt(sum((a - b) ** 2 for r in rows for a, b in zip(r['q'], r['target_q'])) / (8 * len(rows)))),
        'max_root_error_mm': max(norm([a - b for a, b in zip(r['root'], r['target_root'])]) for r in rows) * 1000,
        'sampled_torque_rms_nm_per_joint': [math.sqrt(sum(r['torque'][j] ** 2 for r in rows) / len(rows)) for j in range(8)],
        'sampled_peak_torque_nm': max(abs(v) for r in rows for v in r['torque']),
        'swing_pass': bool(no_cheat and stable_landing and rows[-1]['root'][0] > rows[0]['root'][0]
                           and any(x['duration_s'] >= s['min_airborne_s'] - 1e-9 and x['forward_mm'] >= s['min_forward_m'] * 1000 for x in swing_events)),
        'wave_pass': bool(no_cheat and stable_landing and any(x['duration_s'] >= w['min_contiguous_s'] - 1e-9
                          and min(x['joint_excursions_rad']) >= w['min_joint_excursion_rad'] for x in wave_events))}


class Audit:
    def __init__(self, root, profile):
        self.root, self.profile = root, profile
        self.used, self.rows, self.raw, self.errors = set(), {}, {}, []

    def path(self, name):
        path = (self.root / name).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('Evidence path escapes submission')
        if not path.is_file():
            raise FileNotFoundError(name)
        self.used.add(path)
        return path

    def read(self, name):
        return json.loads(self.path(name).read_text(), parse_constant=reject_constant)

    def check(self, ids, callback):
        try:
            callback()
        except (OSError, ValueError, KeyError, TypeError, IndexError, ET.ParseError) as e:
            reason = f'{type(e).__name__}: {e}'
            self.errors.append({'metrics': ids, 'reason': reason})
            for mid in ids:
                self.rows[mid] = dict(status='UNVERIFIED', level='E0', reason=reason, evidence=[])

    def put(self, mid, passed, reason, evidence, level='E1'):
        self.rows[mid] = dict(status='PASS' if passed else 'FAIL', level=level, reason=reason, evidence=evidence)

    def exports(self):
        f = 'reports/export_readback.json'
        rows = self.read(f)['parts']
        expected = self.read('reports/print_parts.json')
        complete = bool(rows) and len({r['name'] for r in rows}) == len(rows) and {r['name'] for r in rows} == {r['name'] for r in expected}
        for r in rows:
            self.path(f"output/parts/step/{r['name']}.step")
            self.path(f"output/parts/stl/{r['name']}.stl")
        self.put('A01', complete and all(r['step_valid'] is True and r['step_solid_count'] == 1 and r['step_volume_mm3'] > 0 for r in rows),
                 f'{len(rows)} 个回读记录；本次未重新加载CAD内核', [f])
        self.put('A02', complete and all(r['stl_watertight'] is True and r['stl_volume_mm3'] > 0 and r['positive_outer_shells'] == 1 and abs(r['print_min_z_mm']) < .001 for r in rows),
                 '闭合/正体积/单正向外壳/落台，允许负向空腔', [f])
        self.put('A03', complete and all(r['source_volume_mm3'] > 0 and abs(r['step_volume_mm3']/r['source_volume_mm3']-1) < .001
                 and abs(r['stl_volume_mm3']/r['source_volume_mm3']-1) < .015 for r in rows),
                 '提交报告中的同内核源体积与回读对比；不是跨CAD软件round-trip', [f])
        self.raw['exports'] = {'count': len(rows), 'max_step_relative_error': max(r['step_volume_relative_error'] for r in rows),
                               'max_stl_relative_error': max(r['stl_volume_relative_error'] for r in rows)}

    def bom(self):
        with self.path('bom.csv').open(newline='') as f:
            rows = [r for r in csv.DictReader(f) if r['category'] in ('print', 'print_coupon')]
        cat = self.read('reports/print_parts.json')
        a = {r['item_id']: int(r['quantity']) for r in rows}
        b = {r['name']: int(r['quantity']) for r in cat}
        for name in b:
            for ext in ('step', 'stl'):
                self.path(f'output/parts/{ext}/{name}.{ext}')
        passed = a == b and len(a) == len(rows) and bool(a) and all(v > 0 for v in a.values())
        self.put('A04', passed, f'正式件{sum(v for k,v in a.items() if k.startswith("P"))}件；试片另列；未代替采购件真实性审计', ['bom.csv', 'reports/print_parts.json'], 'E2')

    def urdf(self):
        f = 'output/simulation/gorilla8.urdf'
        tree = ET.parse(self.path(f)).getroot()
        joints = tree.findall('joint')
        c = self.read('output/simulation/contract.json')
        mass = self.read('reports/masslinks.json')
        good = [j.get('name') for j in joints] == self.profile['joint_order'] == c['joint_order']
        for j, lim in zip(joints, self.profile['joint_limits_deg']):
            good &= j.get('type') == 'revolute' and [float(x) for x in j.find('axis').get('xyz').split()] == [0, 1, 0]
            good &= all(abs(float(j.find('limit').get(k)) - math.radians(v)) < 1e-8 for k, v in zip(('lower', 'upper'), lim))
        m = sum(float(l.find('inertial/mass').get('value')) for l in tree.findall('link'))
        good &= abs(m - sum(x['mass_kg'] for x in mass.values())) < 1e-8
        for link in tree.findall('link'):
            inertial = link.find('inertial')
            good &= float(inertial.find('mass').get('value')) > 0
            i = inertial.find('inertia')
            a, b, c0, d, e, f0 = [float(i.get(k)) for k in ('ixx', 'iyy', 'izz', 'ixy', 'ixz', 'iyz')]
            def determinant(x, y, z, xy, xz, yz):
                return x*y*z + 2*xy*xz*yz - x*yz*yz - y*xz*xz - z*xy*xy
            good &= a > 0 and a*b-d*d > 0 and determinant(a,b,c0,d,e,f0) > 0
            # Physical inertia: 0.5*trace(I)*Identity-I is positive semidefinite.
            t = (a+b+c0)/2
            x,y,z = t-a,t-b,t-c0
            good &= min(x,y,z) >= -1e-14 and min(x*y-d*d,x*z-e*e,y*z-f0*f0) >= -1e-20 and determinant(x,y,z,-d,-e,-f0) >= -1e-26
        self.raw['mass_kg'] = m
        self.put('B01', bool(good), '直接解析URDF轴/顺序/限位/质量和惯量；未证明实机轴零位或CAD轴线', ['output/simulation/gorilla8.urdf', 'output/simulation/contract.json', 'reports/masslinks.json'], 'E2')

    def motions(self):
        stats, reports, evidence = [], [], []
        for index, run in enumerate(self.profile['runs']):
            folder = 'output/simulation_runs/' + run
            r, tr = self.read(folder + '/result.json'), self.read(folder + '/trace.json')
            model_path = folder + '/inputs/gorilla8.xml'
            model = ET.parse(self.path(model_path)).getroot()
            free = len(model.findall('.//freejoint')) == 1
            free &= [a.get('joint') for a in model.find('actuator')] == self.profile['joint_order']
            free &= not model.findall('.//equality/*') and not any(b.get('mocap') == 'true' for b in model.findall('.//body'))
            free &= abs(float(model.find('option').get('timestep')) - .002) < 1e-12
            s = trace_stats(tr, self.profile)
            s['input_xml_free_base_and_joint_actuators'] = bool(free)
            s['reported_saturation_fraction_2ms'] = r['torque_saturation_fraction']
            s['reported_peak_torque_nm_2ms'] = r['peak_torque_nm']
            # Reject truncated recordings instead of accepting a favourable prefix.
            s['complete'] = (free and r['completed'] is True and r['fell'] is False and abs(tr[-1]['t'] - r['requested_duration_s']) < 1e-7
                             and abs(tr[0]['t']) < 1e-7 and tr[-1]['t'] <= self.profile['max_motion_duration_s'][index]
                             and r['dt_s'] == .002 and r['control_hz'] == 25)
            stats.append(s); reports.append(r)
            evidence.extend([folder + '/trace.json', folder + '/result.json', model_path])
            self.raw[run] = s
        self.put('B02', stats[0]['complete'] and stats[0]['swing_pass'], '按profile复算连续腾足窗口及落地；仅记录帧', evidence[:3], 'E2')
        self.put('B03', stats[1]['complete'] and stats[1]['wave_pass'], '按profile复算连续三点支撑抬手窗口；仅记录帧', evidence[3:], 'E2')
        t = self.profile['tracking']
        self.put('B06', all(s['complete'] and s['max_joint_error_deg'] <= t['max_joint_error_deg'] and s['max_root_error_mm'] <= t['max_root_error_mm'] for s in stats),
                 '按trace重新计算最大误差；5deg/5mm为新benchmark门槛', evidence, 'E2')
        a = self.profile['actuation']
        good = all(s['complete'] and s['sampled_peak_torque_nm'] <= a['max_torque_nm'] and r['peak_torque_nm'] <= a['max_torque_nm']
                   and 0 <= r['torque_saturation_fraction'] <= a['max_saturation_fraction'] and r['joint_limit_support_observed'] is False
                   and max(r['peak_joint_limit_force_abs_Nm']) <= a['max_limit_force_nm'] for r,s in zip(reports,stats))
        self.put('B07', good, '2ms峰值/饱和来自提交统计；25Hz RMS仅诊断，不证明热额定', evidence)

    def collisions(self):
        files = ['reports/flat_reference_collision.json', 'reports/flat_swing_simulation_collision.json', 'reports/flat_wave_simulation_collision.json']
        p = self.profile['collision']; good = True
        for index, name in enumerate(files):
            r = self.read(name)
            limit = p['reference_ground_tolerance_mm'] if index == 0 else p['actual_ground_tolerance_mm']
            if index == 0:
                expected_frames = 1 + sum(len(self.read('output/motions/' + motion + '/poses.json')) for motion in self.profile['motion_names'])
                good &= r['input_kind'] == 'reference_poses'
            else:
                expected_frames = len(self.read('output/simulation_runs/' + self.profile['runs'][index-1] + '/trace.json'))
                good &= r['input_kind'] == 'actual_simulation_qpos'
            good &= r['frame_count'] == expected_frames
            good &= r['passed'] is True and r['exhaustive_exact'] is True and not r['positive_interference_pairs'] and r['frame_count'] > 0
            good &= r['volume_tolerance_mm3'] <= p['max_volume_tolerance_mm3'] and r['ground_penetration_tolerance_mm'] <= limit
            good &= all(x.get('reason') for x in r['excluded_pairs']) and all(x['all_candidate_frames_checked'] is True for x in r['pair_checks'])
        self.put('B04', bool(good), '导入三份采样碰撞报告；未复跑BREP；白名单合理性需独立审阅', files)

    def strength(self):
        f = 'reports/strength_actual_loads.json'; r = self.read(f)
        cases = r['cases']
        expected = {(run,arm,section) for run in self.profile['runs'] for arm in ('left_arm','right_arm')
                    for section in ('rear_extension','front_toe','root','notch','cup_interface')}
        actual = {(x['run'],x['arm'],x['section']) for x in cases}
        margin = min(x['envelope_stress']['margin_to_assumed_8_MPa'] for x in cases)
        self.raw['local_strength_min_margin'] = margin
        self.put('C03', r['passed'] is True and actual == expected and len(cases) == len(expected) and margin >= 1,
                 f'20个局部案例最小余量{margin:.6f}；许用8MPa是假设；不覆盖整机完整内力', [f])

    def disclosure(self):
        f = 'reports/release_status.json'; r = self.read(f)
        good = r['hardware_validated'] is False and r['physical_prints_made'] is False and isinstance(r['failures'], list) and len(r['limitations']) >= 4
        self.put('D05', good, '结构化声明未实装及四类限制；本项仅评价披露', [f])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROBOT_ROOT)
    parser.add_argument('--out', type=Path, default=REPO_ROOT / 'results' / 'legacy')
    parser.add_argument('--review', type=Path, help='Optional evaluator-authored JSON review; see sample_review.json')
    args = parser.parse_args()
    profile = json.loads((CONFIG_ROOT / 'profile.json').read_text())
    with (CONFIG_ROOT / 'metrics.csv').open(newline='') as f:
        catalog = list(csv.DictReader(f))
    assert len({m['id'] for m in catalog}) == len(catalog) and sum(int(m['weight']) for m in catalog) == 100
    audit = Audit(args.root.resolve(), profile)
    for ids, fn in [(['A01','A02','A03'],audit.exports), (['A04'],audit.bom), (['B01'],audit.urdf),
                    (['B02','B03','B06','B07'],audit.motions), (['B04'],audit.collisions), (['C03'],audit.strength), (['D05'],audit.disclosure)]:
        audit.check(ids, fn)
    if args.review:
        review = json.loads(args.review.read_text())
        for row in review:
            if row['metric_id'] not in {m['id'] for m in catalog} or row['metric_id'] in audit.rows:
                raise ValueError('Review may only fill non-automated metrics')
            if row['status'] not in ('PASS','FAIL','UNVERIFIED') or not row['reviewer'] or not row['reason'] or not row['evidence']:
                raise ValueError('Invalid manual review')
            for ev in row['evidence']:
                if sha(audit.path(ev['path'])) != ev['sha256']:
                    raise ValueError('Manual review evidence has changed: ' + ev['path'])
            audit.rows[row['metric_id']] = dict(status=row['status'], level=row['level'], reason=row['reason'], evidence=[e['path'] for e in row['evidence']])
    scores = []
    for metric in catalog:
        result = audit.rows.get(metric['id'], dict(status='UNVERIFIED', level='E0', reason='未提供满足该条完整判据的证据；不等于实际失败', evidence=[]))
        scores.append(dict(metric, **result, earned=int(metric['weight']) if result['status'] == 'PASS' else 0))
    by_id = {r['id']: r for r in scores}
    gates = {}
    for name, ids in profile['gates'].items():
        status = [by_id[mid]['status'] for mid in ids]
        gates[name] = 'FAIL' if 'FAIL' in status else ('UNVERIFIED' if 'UNVERIFIED' in status else 'PASS')
    lower = sum(r['earned'] for r in scores)
    unknown = sum(int(r['weight']) for r in scores if r['status'] == 'UNVERIFIED')
    coverage = 100 - unknown
    result = dict(benchmark_version=profile['benchmark_version'], profile_id=profile['profile_id'],
                  submission_path=str(audit.root), created_utc=datetime.now(timezone.utc).isoformat(),
                  evaluation_mode='pilot_evidence_audit_not_independent_simulation', official_ranking_eligible=False,
                  score_lower=lower, score_upper=lower+unknown, evidence_coverage_percent=coverage,
                  observed_quality_percent=round(100*lower/coverage, 3) if coverage else None,
                  gates=gates, metrics=scores, raw=audit.raw, errors=audit.errors,
                  environment={'python': sys.version, 'platform': platform.platform()},
                  evaluator_hashes={f.name: sha(f) for f in
                                    (HERE/'evaluate.py', CONFIG_ROOT/'profile.json', CONFIG_ROOT/'metrics.csv')})
    if args.review:
        result['manual_review_sha256'] = sha(args.review)
    args.out.mkdir(parents=True, exist_ok=True)
    def write_json(name, obj):
        (args.out / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    write_json('scorecard.json', result)
    write_json('evidence_manifest.json', {'scope':'Files read during this audit; newly recorded hashes do not prove original generation provenance',
               'files':[{'path':str(p.relative_to(audit.root)), 'bytes':p.stat().st_size, 'sha256':sha(p)} for p in sorted(audit.used)]})
    with (args.out / 'scorecard.csv').open('w', newline='', encoding='utf-8-sig') as f:
        fields = ['id','dimension','name','weight','status','earned','level','reason','evidence']
        writer = csv.DictWriter(f, fields, extrasaction='ignore'); writer.writeheader()
        for row in scores:
            writer.writerow(dict(row, evidence=';'.join(row['evidence'])))
    lines = ['# Gorilla8 benchmark 自动评分卡', '', '这是已有证据审计和轨迹复算，不是CAD/动力学独立重跑。', '',
             f'证据支持得分下界 **{lower}/100**；缺失证据带来的可能上界 **{lower+unknown}/100**；加权证据覆盖率 **{coverage}%**。',
             '上下界不是统计置信区间。UNVERIFIED不代表实物失败。当前样例不具备正式AI排名资格。', '',
             '| Gate | 状态 |','|---|---|'] + [f'| {k} | {v} |' for k,v in gates.items()]
    lines += ['', '| 指标 | 权重 | 状态 | 证据级别 | 得分 |', '|---|---:|---|---|---:|']
    lines += [f"| {r['id']} {r['name']} | {r['weight']} | {r['status']} | {r['level']} | {r['earned']} |" for r in scores]
    lines += ['', '详细数值、证据路径和判据见同目录 scorecard.json / scorecard.csv。']
    (args.out / 'scorecard.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({k: result[k] for k in ('score_lower','score_upper','evidence_coverage_percent','gates','errors')}, ensure_ascii=False, indent=2))
    return 2 if audit.errors else 0


if __name__ == '__main__':
    sys.exit(main())
