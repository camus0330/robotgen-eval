"""Gorilla8 mechanical contract. CAD uses mm; dynamics uses SI."""
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent if (ROOT.parent / 'data').is_dir() else ROOT.parents[1]
INPUT_STEP = WORKSPACE / 'data' / 'xl330_m288_t.step'
OUT = ROOT / 'output'
REPORTS = ROOT / 'reports'
PAD_RADIUS_MM = 12.0
PALM_X_MIN_MM = -45.0
PALM_X_MAX_MM = 20.0
PALM_WIDTH_MM = 34.0
ROOT_HEIGHT_MM = 147.08846518
LIMBS = [
    dict(name='left_arm', origin_mm=[20,56,0], lengths_mm=[60,76], limits_deg=[[-135,12],[-12,125]], q2_sign=1, side=1),
    dict(name='right_arm', origin_mm=[20,-56,0], lengths_mm=[60,76], limits_deg=[[-135,12],[-12,125]], q2_sign=1, side=-1),
    dict(name='left_leg', origin_mm=[-20,52,-33], lengths_mm=[55,52], limits_deg=[[5,85],[-125,-5]], q2_sign=-1, side=1),
    dict(name='right_leg', origin_mm=[-20,-52,-33], lengths_mm=[55,52], limits_deg=[[5,85],[-125,-5]], q2_sign=-1, side=-1),
]
JOINT_NAMES = ['left_shoulder_pitch','left_elbow_pitch','right_shoulder_pitch','right_elbow_pitch',
               'left_hip_pitch','left_knee_pitch','right_hip_pitch','right_knee_pitch']
NEUTRAL_DEG = [-10.,10.,-10.,10.,21.49543967,-33.22632387,21.49543967,-33.22632387]
COLORS = {'PETG': [0.62,0.66,0.71,1], 'TPU':[0.10,0.12,0.15,1],
          'motor':[0.075,0.085,0.10,1], 'horn':[0.24,0.27,0.31,1],
          'face':[0.78,0.80,0.82,1], 'eyes':[0.025,0.035,0.045,1], 'metal':[0.55,0.59,0.63,1]}

def ry(a):
    c,s = np.cos(a), np.sin(a)
    return np.array([[c,0,s],[0,1,0],[-s,0,c]])

def transforms(q_rad=None, root_xyz_mm=None):
    q = np.radians(NEUTRAL_DEG) if q_rad is None else np.asarray(q_rad)
    root = np.array([0.,0.,ROOT_HEIGHT_MM]) if root_xyz_mm is None else np.asarray(root_xyz_mm)
    ts = {'base': (np.eye(3),root)}
    for i,l in enumerate(LIMBS):
        r1,r2 = ry(q[2*i]),ry(q[2*i]+q[2*i+1])
        o=root+np.array(l['origin_mm'])
        ts[l['name']+'_upper']=(r1,o)
        ts[l['name']+'_lower']=(r2,o+r1@np.array([0.,0.,-l['lengths_mm'][0]]))
    return ts
