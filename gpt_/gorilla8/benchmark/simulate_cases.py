#!/usr/bin/env python3
"""Independent replay and public perturbation runner. Never sends motor commands.

Matches original control/step/sample ordering. Does not compute local stress loads.
All 2ms torque/limit summaries are retained; trajectories are recorded at 25Hz.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import xml.etree.ElementTree as ET

os.environ.setdefault('MUJOCO_GL','egl')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import mujoco
import numpy as np
from evaluate import trace_stats

HERE=Path(__file__).resolve().parent
PROFILE=json.loads((HERE/'profile.json').read_text())


def hashfile(path):
    with path.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def apply_case(model, case, controller):
    model.actuator_gainprm[:,0] *= controller['kp_scale']*case.get('servo_gain_scale',1)
    model.actuator_biasprm[:,1] = -model.actuator_gainprm[:,0]
    model.actuator_biasprm[:,2] *= controller['kv_scale']*case.get('servo_gain_scale',1)
    if 'friction' in case:
        # Change both members: MuJoCo's default geom-pair combination uses max.
        model.geom_friction[:,0]=case['friction']
    scale=case.get('mass_and_inertia_scale',1)
    model.body_mass[1:]*=scale; model.body_inertia[1:]*=scale
    delta=np.array(case.get('equivalent_accessory_com_offset_mm',[0,0,0]))*.001
    if np.any(delta):
        bid=model.body('base').id; total=model.body_mass[bid]; accessory=.035*scale
        old_com=model.body_ipos[bid].copy(); com_delta=accessory/total*delta
        rot=np.zeros(9);mujoco.mju_quat2Mat(rot,model.body_iquat[bid]);rot=rot.reshape(3,3)
        inertia=rot@np.diag(model.body_inertia[bid])@rot.T
        r=np.array([0,0,-.046])-old_com
        def parallel(v): return np.dot(v,v)*np.eye(3)-np.outer(v,v)
        inertia+=accessory*(parallel(r+delta)-parallel(r))-total*parallel(com_delta)
        eigen,vectors=np.linalg.eigh(inertia)
        if min(eigen)<=0 or max(eigen)>sum(eigen)-max(eigen)+1e-10:
            raise ValueError('Perturbation produced invalid inertia')
        if np.linalg.det(vectors)<0: vectors[:,0]*=-1
        quat=np.zeros(4);mujoco.mju_mat2Quat(quat,vectors.ravel())
        model.body_inertia[bid]=eigen;model.body_iquat[bid]=quat;model.body_ipos[bid]+=com_delta
    data=mujoco.MjData(model);mujoco.mj_setConst(model,data)
    return data


def contact_record(model,data,ground,pad_ids):
    grounded=set();normal=np.zeros(4)
    for ci,c in enumerate(data.contact):
        if c.geom1==ground: gid=int(c.geom2)
        elif c.geom2==ground: gid=int(c.geom1)
        else:continue
        grounded.add(gid)
        if gid in pad_ids:
            force=np.zeros(6);mujoco.mj_contactForce(model,data,ci,force);normal[pad_ids.index(gid)]+=force[0]
    clearance=[]
    for gid in pad_ids:
        rotation=data.geom_xmat[gid].reshape(3,3)
        if model.geom_type[gid]==mujoco.mjtGeom.mjGEOM_BOX:
            extent=float(np.abs(rotation[2])@model.geom_size[gid])
        else:
            z=rotation[2,2];r,h=model.geom_size[gid,:2];extent=r*np.sqrt(max(0,1-z*z))+h*abs(z)
        clearance.append(float(data.geom_xpos[gid,2]-extent))
    return dict(pad_contact=[gid in grounded for gid in pad_ids],pad_normal_force_N=normal.tolist(),pad_clearance_m=clearance,
                nonpad_ground_contacts=len(grounded-set(pad_ids)))


def run_one(job):
    root,out,case,controller,motion=job;root=Path(root);out=Path(out)
    started=time.time();model_file=root/'output/simulation/gorilla8.xml'
    model=mujoco.MjModel.from_xml_path(str(model_file));data=apply_case(model,case,controller)
    folder=root/'output/motions'/motion;ref=np.load(folder/'motion.npz');times=ref['time_s'];q=ref['joint_pos_rad'];roots=ref['root_pos_m']
    tau=np.array([p['statics']['joint_torque_Nm'] for p in json.loads((folder/'poses.json').read_text())]) if motion.endswith('swing') else np.zeros_like(q)
    # Controller stays frozen under disturbances: no oracle recomputation of tau.
    delay=case.get('added_command_delay_ms',0)*.001
    bias=np.radians(case.get('encoder_zero_error_deg',[0]*8))
    data.qpos[:3]=roots[0];data.qpos[3:7]=ref['root_quat_wxyz'][0];data.qpos[7:]=q[0]
    nominal_kp=2*controller['kp_scale']
    data.ctrl[:]=q[0]+tau[0]/nominal_kp-bias
    mujoco.mj_forward(model,data)
    for _ in range(500):mujoco.mj_step(model,data)
    ground=model.geom('ground').id
    pad_ids=[model.geom(n+'_rocker').id for n in ('left_arm','right_arm','left_leg','right_leg')]
    joint_slot={model.joint(n).id:i for i,n in enumerate(PROFILE['joint_order'])}
    rows=[];torques=[];limits=np.zeros(8);fell=False
    for k in range(round(float(times[-1])/.002)+1):
        t=k*.002
        if k%20==0:
            target=np.array([np.interp(t,times,q[:,i]) for i in range(8)])
        if k%20==round(delay/.002)%20:
            command_time=max(0,(k//20)*.04-(.04 if delay>=.04 else 0))
            command=np.array([np.interp(command_time,times,q[:,i]) for i in range(8)])
            ff=np.array([np.interp(command_time,times,tau[:,i]) for i in range(8)])
            data.ctrl[:]=command+ff/nominal_kp-bias
        mujoco.mj_step(model,data);torque=data.actuator_force.copy();torques.append(torque)
        limit=np.zeros(8)
        for ci in np.flatnonzero(data.efc_type==mujoco.mjtConstraint.mjCNSTR_LIMIT_JOINT):
            limit[joint_slot[int(data.efc_id[ci])]]+=abs(float(data.efc_force[ci]))
        limits=np.maximum(limits,limit)
        if k%20==0:
            mujoco.mj_forward(model,data)
            contacts=contact_record(model,data,ground,pad_ids)
            up=float(1-2*(data.qpos[4]**2+data.qpos[5]**2))
            rows.append(dict(t=t,q=data.qpos[7:].tolist(),target_q=target.tolist(),root=data.qpos[:3].tolist(),
                             root_quat_wxyz=data.qpos[3:7].tolist(),target_root=[float(np.interp(t,times,roots[:,i])) for i in range(3)],
                             root_linear_velocity_m_s=data.qvel[:3].tolist(),root_angular_velocity_rad_s=data.qvel[3:6].tolist(),
                             up_z=up,torque=torque.tolist(),joint_limit_force_abs_Nm=limit.tolist(),**contacts))
            if up<.5 or data.qpos[2]<.055 or not np.isfinite(data.qpos).all():fell=True;break
    stats=trace_stats(rows,PROFILE);torques=np.array(torques)
    complete=not fell and abs(rows[-1]['t']-float(times[-1]))<1e-9
    task=stats['swing_pass' if motion.endswith('swing') else 'wave_pass'] and complete
    actuation=(np.max(np.abs(torques))<=.100001 and np.mean(np.abs(torques)>=.09999)<=.001 and max(limits)<=.001)
    stats.update(completed=complete,fell=fell,task_pass=bool(task),actuation_pass=bool(actuation),
                 peak_torque_nm=float(np.max(np.abs(torques))),torque_saturation_fraction=float(np.mean(np.abs(torques)>=.09999)),
                 torque_rms_2ms_nm=np.sqrt(np.mean(torques**2,axis=0)).tolist(),peak_limit_force_nm=float(max(limits)),
                 elapsed_s=time.time()-started,total_mass_kg=float(sum(model.body_mass)))
    target_out=out/case['case_id']/motion;target_out.mkdir(parents=True,exist_ok=True)
    tracefile=target_out/'trace.json';tracefile.write_text(json.dumps(rows,allow_nan=False))
    result=dict(case=case,controller=controller,motion=motion,metrics=stats,trace_sha256=hashfile(tracefile),
                model_sha256=hashfile(model_file),motion_sha256=hashfile(folder/'motion.npz'),
                runner_sha256=hashfile(Path(__file__)),mujoco_version=mujoco.__version__,scope='approximate_contact_simulation_not_hardware')
    (target_out/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    return dict(case_id=case['case_id'],motion=motion,**stats)


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cases',type=Path);p.add_argument('--kp-scale',type=float,default=1);p.add_argument('--kv-scale',type=float,default=1)
    p.add_argument('--workers',type=int,default=2);args=p.parse_args()
    cases=[json.loads(line) for line in args.cases.read_text().splitlines()] if args.cases else [dict(case_id='nominal')]
    controller=dict(kp_scale=args.kp_scale,kv_scale=args.kv_scale)
    args.out.mkdir(parents=True,exist_ok=True)
    jobs=[(str(args.root.resolve()),str(args.out.resolve()),c,controller,m) for c in cases for m in PROFILE['motion_names']]
    rows=[]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for row in pool.map(run_one,jobs):
            rows.append(row);print(row['case_id'],row['motion'],'task',row['task_pass'],'actuation',row['actuation_pass'],flush=True)
            (args.out/'progress.json').write_text(json.dumps({'completed':len(rows),'expected':len(jobs)}))
    successes=sum(all(r['task_pass'] and r['actuation_pass'] for r in rows if r['case_id']==c['case_id']) for c in cases)
    n=len(cases);phat=successes/n;z=1.96;center=(phat+z*z/(2*n))/(1+z*z/n)
    half=z*math.sqrt(phat*(1-phat)/n+z*z/(4*n*n))/(1+z*z/n)
    report=dict(case_count=n,simulation_count=len(rows),joint_successes=successes,success_rate=phat,
                wilson95=[center-half,center+half],controller=controller,rows=rows,
                cases_sha256=hashfile(args.cases) if args.cases else None,
                runner_sha256=hashfile(Path(__file__)),passed=n==100 and successes>=90,
                split='public_development' if args.cases else 'nominal')
    (args.out/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print('DONE',successes,'/',n,flush=True)


if __name__=='__main__':main()
