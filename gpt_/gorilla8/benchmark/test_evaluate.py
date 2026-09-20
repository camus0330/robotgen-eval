"""Regression checks for false-positive scoring and missing-evidence behaviour."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from evaluate import Audit, HERE, trace_stats

PROFILE = json.loads((HERE/'profile.json').read_text())


def trace():
    rows = []
    for i in range(101):
        airborne = 10 <= i <= 60
        q = [0.0] * 8
        r = dict(t=i*.04, q=q, target_q=q[:], root=[i*.0003,0,.15], target_root=[i*.0003,0,.15],
                 root_linear_velocity_m_s=[0,0,0], root_angular_velocity_rad_s=[0,0,0],
                 torque=[.01]*8, joint_limit_force_abs_Nm=[0]*8,
                 pad_contact=[True,True,False,False] if airborne else [True]*4,
                 pad_clearance_m=[0,0,.003,.003] if airborne else [0]*4,
                 pad_normal_force_N=[1]*4, nonpad_ground_contacts=0, up_z=1.0)
        rows.append(r)
    return rows


class ScoringTests(unittest.TestCase):
    def test_airborne_with_landing(self):
        self.assertTrue(trace_stats(trace(), PROFILE)['swing_pass'])

    def test_foot_support_is_not_airborne(self):
        rows = trace()
        for r in rows:
            r['pad_contact'] = [True]*4
        self.assertFalse(trace_stats(rows, PROFILE)['swing_pass'])

    def test_limit_assisted_motion_fails(self):
        rows = trace(); rows[30]['joint_limit_force_abs_Nm'][0] = .02
        self.assertFalse(trace_stats(rows, PROFILE)['swing_pass'])

    def test_no_landing_fails(self):
        rows = trace()[:65]
        self.assertFalse(trace_stats(rows, PROFILE)['swing_pass'])

    def test_timestamp_gap_rejected(self):
        rows = trace(); rows[10]['t'] += .2
        with self.assertRaises(ValueError):
            trace_stats(rows, PROFILE)

    def test_non_finite_rejected(self):
        rows = trace(); rows[4]['q'][0] = float('nan')
        with self.assertRaises(ValueError):
            trace_stats(rows, PROFILE)

    def test_wave_requires_contiguous_support(self):
        rows = trace()
        for i, r in enumerate(rows):
            if 10 <= i <= 60:
                r['pad_contact'] = [False,True,True,True]
                r['pad_clearance_m'][0] = .06
                r['q'] = [i*.01,i*.01]+[0]*6
        self.assertTrue(trace_stats(rows, PROFILE)['wave_pass'])
        for i in range(10,61,10):
            rows[i]['pad_contact'][2] = False
        self.assertFalse(trace_stats(rows, PROFILE)['wave_pass'])

    def test_missing_report_is_unverified(self):
        with tempfile.TemporaryDirectory() as folder:
            a = Audit(Path(folder), PROFILE)
            a.check(['A01','A02','A03'], a.exports)
            self.assertEqual(a.rows['A01']['status'], 'UNVERIFIED')
            self.assertTrue(a.errors)

    def test_source_is_not_modified(self):
        rows = trace(); original = copy.deepcopy(rows)
        trace_stats(rows, PROFILE)
        self.assertEqual(rows, original)


if __name__ == '__main__':
    unittest.main()
