"""Short free-base dynamics check; does not command physical motors."""
import os
os.environ.setdefault('MUJOCO_GL','egl')
import argparse, json
from pathlib import Path
import numpy as np
import mujoco
from design import OUT, LIMBS, JOINT_NAMES

PALM_SECTIONS={'rear_extension':np.array([-.011,0.,-.007344827586]),'front_toe':np.array([.011,0.,-.0085])}
SHOULDER_SECTIONS={'root':np.array([-.0005,.029,-.0215]),
                   'notch':np.array([-.0015,.035,-.0215]),
                   'cup_interface':np.array([.0066,.04875,-.0215])}

def contact_state(model,data,ground,pad_ids):
    grounded=set();pad_normal=np.zeros(4);positions=[];normals=[];palm_x=[]
    cop_numer=np.zeros(2);pitch_moment=np.zeros(2)
    palm_force=np.zeros((2,3));palm_moment=np.zeros((2,3));palm_centers=[];palm_rotations=[]
    regions=[{name:np.zeros(6) for name in PALM_SECTIONS} for _ in range(2)]
    for i,gid in enumerate(pad_ids[:2]):
        body=model.geom_bodyid[gid];rotation=data.xmat[body].reshape(3,3)
        palm_rotations.append(rotation);palm_centers.append(data.xpos[body]+rotation@np.array([0.,0.,-LIMBS[i]['lengths_mm'][1]/1000]))
    for ci,c in enumerate(data.contact):
        if c.geom1==ground:gid=int(c.geom2);sign=1.
        elif c.geom2==ground:gid=int(c.geom1);sign=-1.
        else:continue
        grounded.add(gid)
        force=np.zeros(6);mujoco.mj_contactForce(model,data,ci,force)
        if gid in pad_ids:pad_normal[pad_ids.index(gid)]+=force[0]
        if force[0]>1e-8:
            positions.append(c.pos.copy());normals.append(force[0])
            if gid in pad_ids[:2]:palm_x.append(float(c.pos[0]))
        if gid in pad_ids[:2]:
            i=pad_ids.index(gid);rotation=palm_rotations[i]
            arm=c.pos-palm_centers[i];frame=c.frame.reshape(3,3)
            world_force=sign*(frame.T@force[:3]);world_moment=sign*(frame.T@force[3:])
            cop_numer[i]+=float((rotation.T@arm)[0])*force[0]
            moment=np.cross(arm,world_force)+world_moment
            pitch_moment[i]+=float((rotation.T@moment)[1]);palm_force[i]+=world_force;palm_moment[i]+=moment
            local_arm=rotation.T@arm;local_force=rotation.T@world_force;local_moment=rotation.T@world_moment
            region='rear_extension' if local_arm[0]<-.011 else 'front_toe' if local_arm[0]>.011 else None
            if region:
                regions[i][region][:3]+=local_force
                regions[i][region][3:]+=np.cross(local_arm-PALM_SECTIONS[region],local_force)+local_moment
    clearance=[]
    for gid in pad_ids:
        rotation=data.geom_xmat[gid].reshape(3,3)
        if model.geom_type[gid]==mujoco.mjtGeom.mjGEOM_BOX:
            extent=float(np.abs(rotation[2])@model.geom_size[gid])
        elif model.geom_type[gid]==mujoco.mjtGeom.mjGEOM_CYLINDER:
            axis_z=float(rotation[2,2]);radius,halfwidth=model.geom_size[gid,:2]
            extent=radius*np.sqrt(max(0.,1-axis_z**2))+halfwidth*abs(axis_z)
        else:raise ValueError('Unsupported pad contact shape')
        clearance.append(float(data.geom_xpos[gid,2]-extent))
    palms=[dict(normal_force_N=float(pad_normal[i]),cop_x_relative_palm_m=float(cop_numer[i]/pad_normal[i]) if pad_normal[i]>1e-8 else None,
                normal_bending_moment_abs_Nm=float(abs(cop_numer[i])),pitch_contact_moment_Nm=float(pitch_moment[i]),
                palm_center_world_m=palm_centers[i].tolist(),force_world_N=palm_force[i].tolist(),moment_world_about_palm_Nm=palm_moment[i].tolist(),
                force_local_N=(palm_rotations[i].T@palm_force[i]).tolist(),moment_local_about_palm_Nm=(palm_rotations[i].T@palm_moment[i]).tolist(),
                section_loads={name:dict(section_point_relative_palm_m=PALM_SECTIONS[name].tolist(),force_local_N=load[:3].tolist(),
                                        moment_about_section_local_Nm=load[3:].tolist()) for name,load in regions[i].items()}) for i in range(2)]
    base=model.body('base').id;base_rotation=data.xmat[base].reshape(3,3)
    for i,palm in enumerate(palms):
        palm['shoulder_bridge_contact']={}
        for name,point in SHOULDER_SECTIONS.items():
            section=point.copy();section[1]*=LIMBS[i]['side']
            section_world=data.xpos[base]+base_rotation@section
            moment=palm_moment[i]+np.cross(palm_centers[i]-section_world,palm_force[i])
            palm['shoulder_bridge_contact'][name]=dict(section_point_base_m=section.tolist(),force_base_N=(base_rotation.T@palm_force[i]).tolist(),
                                                       moment_about_section_base_Nm=(base_rotation.T@moment).tolist())
    return dict(grounded=grounded,pad_normal=pad_normal,clearance=clearance,palms=palms,
                cop=np.average(positions,axis=0,weights=normals).tolist() if normals else None,
                palm_x_range=[min(palm_x),max(palm_x)] if palm_x else None)

def main():
    p=argparse.ArgumentParser();p.add_argument('--motion',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--render',action='store_true')
    p.add_argument('--hold-seconds',type=float,help='Required positive duration for a single-frame static reference')
    p.add_argument('--settle-seconds',type=float,default=1.0)
    p.add_argument('--gravity-feedforward',action='store_true',help='Apply matched poses.json quasi-static joint torque / actuator kp')
    p.add_argument('--balance-pitch',action='store_true',help='Bounded shoulder target correction from free-base pitch and pitch rate')
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    ref=np.load(args.motion);print('REFERENCE FIELDS',ref.files,flush=True)
    time=ref['time_s'];qref=ref['joint_pos_rad'];roots=ref['root_pos_m']
    if ref['joint_names'].tolist()!=JOINT_NAMES:raise ValueError('Reference joint order does not match design')
    if time[0]!=0 or np.any(np.diff(time)<=0):raise ValueError('Reference times must start at zero and increase')
    if qref.shape!=(len(time),8) or roots.shape!=(len(time),3):raise ValueError('Reference shapes do not match timestamps')
    if len(time)==1 and (args.hold_seconds is None or args.hold_seconds<=0):raise ValueError('Static reference requires --hold-seconds > 0')
    if len(time)>1 and args.hold_seconds is not None:raise ValueError('--hold-seconds is only for a single-frame reference')
    if args.settle_seconds<0:raise ValueError('--settle-seconds must be non-negative')
    duration=args.hold_seconds if len(time)==1 else float(time[-1])
    model=mujoco.MjModel.from_xml_path(str(OUT/'simulation/gorilla8.xml'));data=mujoco.MjData(model)
    tau_ref=np.zeros_like(qref)
    if args.gravity_feedforward:
        poses=json.loads(args.motion.with_name('poses.json').read_text())
        if len(poses)!=len(time):raise ValueError('poses.json frame count does not match NPZ')
        if not np.allclose([a['time_s'] for a in poses],time,rtol=0,atol=1e-10):raise ValueError('poses.json timestamps do not match NPZ')
        if not np.allclose([a['joint_rad'] for a in poses],qref,rtol=0,atol=1e-10):raise ValueError('poses.json joints do not match NPZ')
        if not np.allclose(np.array([a['root_mm'] for a in poses])*.001,roots,rtol=0,atol=1e-10):raise ValueError('poses.json roots do not match NPZ')
        if not np.allclose([a['statics']['mass_kg'] for a in poses],sum(model.body_mass),rtol=0,atol=1e-9):raise ValueError('Feedforward mass does not match model mass')
        tau_ref=np.array([a['statics']['joint_torque_Nm'] for a in poses])
        if tau_ref.shape!=qref.shape or not np.isfinite(tau_ref).all():raise ValueError('Invalid quasi-static torque array')
    kp=model.actuator_gainprm[:,0]
    data.qpos[:3]=roots[0];data.qpos[3:7]=ref['root_quat_wxyz'][0];data.qpos[7:]=qref[0];data.ctrl[:]=qref[0]
    data.ctrl[:]+=tau_ref[0]/kp
    mujoco.mj_forward(model,data)
    # Allow contact and compliant position control to settle before reference playback.
    for _ in range(round(args.settle_seconds/model.opt.timestep)):mujoco.mj_step(model,data)
    records=[];frames=[];torque_samples=[];peak_joint_limit_force=np.zeros(8)
    joint_slot={model.joint(name).id:i for i,name in enumerate(JOINT_NAMES)}
    ground=model.geom('ground').id
    pad_ids=[model.geom(l['name']+'_rocker').id for l in LIMBS]
    base_id=model.body('base').id
    load_peaks={phase:{limb['name']:{} for limb in LIMBS[:2]} for phase in ['all_steps','double_palms_only','single_palm_and_rear_feet']}
    settled_root=data.qpos[:3].copy()
    if args.render:
        renderer=mujoco.Renderer(model,height=720,width=960)
        camera=mujoco.MjvCamera();camera.lookat[:]=[.015,0,.095];camera.distance=.42;camera.azimuth=135;camera.elevation=-18
    steps=round(duration/.002)+1
    failed=False
    for k in range(steps):
        t=k*.002
        if k%20==0:
            desired_q=np.array([np.interp(t,time,qref[:,i]) for i in range(8)])
            tau_ff=np.array([np.interp(t,time,tau_ref[:,i]) for i in range(8)])
            data.ctrl[:]=desired_q+tau_ff/kp
            reference_index=min(np.searchsorted(time,t,side='right')-1,len(time)-1)
            balance_offset=0.0
            if args.balance_pitch and np.all(ref['contact_mask'][reference_index,:2]):
                qw,qx,qy,qz=data.qpos[3:7]
                pitch=np.arcsin(np.clip(2*(qw*qy-qz*qx),-1.,1.))
                tw,tx,ty,tz=ref['root_quat_wxyz'][reference_index]
                target_pitch=np.arcsin(np.clip(2*(tw*ty-tz*tx),-1.,1.))
                balance_offset=float(np.clip(pitch-target_pitch+.10*data.qvel[4],-.08,.08))
                data.ctrl[[0,2]]+=balance_offset
        mujoco.mj_step(model,data)
        applied_torque=data.actuator_force.copy()
        torque_samples.append(applied_torque)
        joint_limit_force=np.zeros(8)
        for ci in np.flatnonzero(data.efc_type==mujoco.mjtConstraint.mjCNSTR_LIMIT_JOINT):
            slot=joint_slot[int(data.efc_id[ci])]
            joint_limit_force[slot]+=abs(float(data.efc_force[ci]))
        peak_joint_limit_force=np.maximum(peak_joint_limit_force,joint_limit_force)
        cs=contact_state(model,data,ground,pad_ids)
        pad_contact=[gid in cs['grounded'] for gid in pad_ids]
        only_pads=not bool(cs['grounded']-set(pad_ids))
        phases=['all_steps']
        if pad_contact==[True,True,False,False] and min(cs['pad_normal'][:2])>.01 and min(cs['clearance'][2:])>.002 and only_pads:
            phases.append('double_palms_only')
        if sum(cs['pad_normal'][:2]>.01)==1 and min(cs['pad_normal'][2:])>.01 and only_pads:
            phases.append('single_palm_and_rear_feet')
        for phase in phases:
            for i,limb in enumerate(LIMBS[:2]):
                for metric in ['force_world_N','moment_world_about_palm_Nm','force_local_N','moment_local_about_palm_Nm']:
                    key=metric+'_component_abs_peak'
                    old=load_peaks[phase][limb['name']].get(key,[0.,0.,0.])
                    load_peaks[phase][limb['name']][key]=np.maximum(old,np.abs(cs['palms'][i][metric])).tolist()
                for metric in ['normal_force_N','normal_bending_moment_abs_Nm','pitch_contact_moment_Nm']:
                    old=load_peaks[phase][limb['name']].get(metric)
                    if old is None or abs(cs['palms'][i][metric])>abs(old[metric]):
                        load_peaks[phase][limb['name']][metric]=dict(time_s=t,**cs['palms'][i])
                region_peaks=load_peaks[phase][limb['name']].setdefault('section_loads',{})
                for name,load in cs['palms'][i]['section_loads'].items():
                    peaks=region_peaks.setdefault(name,{})
                    for metric in ['force_local_N','moment_about_section_local_Nm']:
                        key=metric+'_component_abs_peak'
                        peaks[key]=np.maximum(peaks.get(key,[0.,0.,0.]),np.abs(load[metric])).tolist()
                    for axis in range(3):
                        key='moment_'+'xyz'[axis]+'_peak_event';old=peaks.get(key)
                        if old is None or abs(load['moment_about_section_local_Nm'][axis])>abs(old['moment_about_section_local_Nm'][axis]):
                            peaks[key]=dict(time_s=t,**load)
                bridges=load_peaks[phase][limb['name']].setdefault('shoulder_bridge_contact',{})
                for name,load in cs['palms'][i]['shoulder_bridge_contact'].items():
                    peaks=bridges.setdefault(name,{})
                    for metric in ['force_base_N','moment_about_section_base_Nm']:
                        key=metric+'_component_abs_peak'
                        peaks[key]=np.maximum(peaks.get(key,[0.,0.,0.]),np.abs(load[metric])).tolist()
                    for axis in range(3):
                        key='moment_'+'xyz'[axis]+'_peak_event';old=peaks.get(key)
                        if old is None or abs(load['moment_about_section_base_Nm'][axis])>abs(old['moment_about_section_base_Nm'][axis]):
                            peaks[key]=dict(time_s=t,**load)
        if k%20==0:
            mujoco.mj_forward(model,data)
            desired=np.array([np.interp(t,time,roots[:,i]) for i in range(3)])
            qw,qx,qy,qz=data.qpos[3:7];up=1-2*(qx*qx+qy*qy)
            cs=contact_state(model,data,ground,pad_ids);grounded=cs['grounded'];clearance=cs['clearance']
            records.append(dict(t=t,root=data.qpos[:3].tolist(),target_root=desired.tolist(),
                                root_quat_wxyz=data.qpos[3:7].tolist(),q=data.qpos[7:].tolist(),target_q=desired_q.tolist(),
                                root_linear_velocity_m_s=data.qvel[:3].tolist(),root_angular_velocity_rad_s=data.qvel[3:6].tolist(),
                                center_of_mass_m=data.subtree_com[base_id].tolist(),pad_normal_force_N=cs['pad_normal'].tolist(),
                                contact_cop_m=cs['cop'],palm_contact_x_range_m=cs['palm_x_range'],palm_contact_loads=cs['palms'],
                                actuator_ctrl_rad=data.ctrl.tolist(),gravity_feedforward_nm=tau_ff.tolist(),
                                balance_pitch_offset_rad=balance_offset,
                                torque=applied_torque.tolist(),up_z=float(up),contacts=int(data.ncon),
                                joint_limit_force_abs_Nm=joint_limit_force.tolist(),
                                target_contact=ref['contact_mask'][min(np.searchsorted(time,t,side='right')-1,len(time)-1)].tolist(),
                                pad_contact=[gid in grounded for gid in pad_ids],pad_clearance_m=clearance,
                                nonpad_ground_contacts=len(grounded-set(pad_ids))))
            if args.render:
                camera.lookat[0]=data.qpos[0]+.015
                renderer.update_scene(data,camera);frames.append(renderer.render().copy())
            if up<.5 or data.qpos[2]<.055 or not np.isfinite(data.qpos).all():
                failed=True;break
    actual=np.array([r['root'] for r in records]);target=np.array([r['target_root'] for r in records])
    errors=np.linalg.norm(actual-target,axis=1)
    torques=np.array(torque_samples)
    palm_only=[r['pad_contact']==[True,True,False,False] and min(r['pad_normal_force_N'][:2])>.01 and min(r['pad_clearance_m'][2:])>.002
               and r['nonpad_ground_contacts']==0 for r in records]
    palm_intervals=[];start=None
    for i,active in enumerate(palm_only+[False]):
        if active and start is None:start=i
        if not active and start is not None:
            a,b=records[start],records[i-1]
            palm_intervals.append(dict(start_s=a['t'],end_s=b['t'],duration_s=b['t']-a['t'],
                                       forward_displacement_m=b['root'][0]-a['root'][0],
                                       min_foot_clearance_m=float(min(min(r['pad_clearance_m'][2:]) for r in records[start:i]))))
            start=None
    landing_start=len(records)
    for i in range(len(records)-1,-1,-1):
        r=records[i]
        if not (all(r['pad_contact']) and min(r['pad_normal_force_N'])>.01 and r['nonpad_ground_contacts']==0 and r['up_z']>.95
                and np.linalg.norm(r['root_linear_velocity_m_s'])<.02
                and np.linalg.norm(r['root_angular_velocity_rad_s'])<.2):break
        landing_start=i
    landing_duration=records[-1]['t']-records[landing_start]['t'] if landing_start<len(records) else 0.
    stable_landing=bool(not failed and landing_duration>=1.)
    airborne_forward=bool(any(p['duration_s']>=.08-1e-9 and p['forward_displacement_m']>.001 for p in palm_intervals))
    limit_support=bool(max(peak_joint_limit_force)>.001)
    report=dict(model='approximate contacts, uncalibrated position servos; free base',reference=str(args.motion),
                dt_s=.002,control_decimation=20,control_hz=25,reference_fps=float(ref['reference_fps']),
                duration_s=records[-1]['t'],requested_duration_s=duration,settle_seconds=args.settle_seconds,
                gravity_feedforward=args.gravity_feedforward,
                balance_pitch=args.balance_pitch,
                balance_pitch_gains=dict(kp=1.0,kd_s=.10,max_shoulder_offset_rad=.08,sign=1) if args.balance_pitch else None,
                settled_root_m=settled_root.tolist(),total_mass_kg=float(sum(model.body_mass)),
                fell=failed,completed=not failed,peak_root_error_m=float(max(errors)),
                final_root_error_m=float(errors[-1]),actual_forward_displacement_m=float(actual[-1,0]-actual[0,0]),
                min_up_z=float(min(r['up_z'] for r in records)),peak_torque_nm=float(np.max(np.abs(torques))),
                torque_saturation_fraction=float(np.mean(np.abs(torques)>=.09999)),
                peak_joint_error_rad=float(np.max(np.abs(np.array([r['q'] for r in records])-np.array([r['target_q'] for r in records])))),
                peak_joint_limit_force_abs_Nm=peak_joint_limit_force.tolist(),joint_limit_support_observed=limit_support,
                palm_contact_load_peaks_2ms=load_peaks,
                pad_order=[l['name'] for l in LIMBS],max_pad_clearance_m=np.max([r['pad_clearance_m'] for r in records],axis=0).tolist(),
                double_palms_only_fraction=float(np.mean(palm_only)),
                double_palms_only_intervals=palm_intervals,
                terminal_stable_four_contact_duration_s=landing_duration,
                stable_four_contact_landing=stable_landing,
                landing_criteria=dict(min_duration_s=1.,min_up_z=.95,min_pad_normal_force_N=.01,max_linear_speed_m_s=.02,max_angular_speed_rad_s=.2),
                dynamic_palm_swing_observed=bool(not failed and not limit_support and airborne_forward and stable_landing and actual[-1,0]-actual[0,0]>.001),
                static_double_palm_hold_pass=bool(len(time)==1 and duration>=2 and not failed and all(palm_only) and max(errors)<.02),
                root_tracking_under_20mm=bool(max(errors)<.02),hardware_validated=False)
    (args.out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    (args.out/'trace.json').write_text(json.dumps(records)+'\n')
    if args.render:
        import subprocess
        cmd=['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s','960x720','-r','25','-i','-',
             '-an','-c:v','libx264','-crf','21','-pix_fmt','yuv420p','-movflags','+faststart',str(args.out/'simulation.mp4')]
        proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
        for f in frames:proc.stdin.write(f.tobytes())
        proc.stdin.close()
        if proc.wait()!=0:raise RuntimeError('ffmpeg failed')
        renderer.close()
    print(json.dumps(report,indent=2))
    return 2 if failed else 0

if __name__=='__main__':raise SystemExit(main())
