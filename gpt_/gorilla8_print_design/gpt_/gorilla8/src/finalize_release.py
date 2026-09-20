"""Aggregate delivered geometry and motion evidence; never infer hardware validation."""
import json
from datetime import datetime, timezone
import numpy as np
from design import ROOT, OUT, REPORTS, JOINT_NAMES


def read(path):
    return json.loads(path.read_text())


def main():
    cad=read(REPORTS/'cad_checks.json')
    exported=read(REPORTS/'export_readback.json')
    strength=read(REPORTS/'strength_actual_loads.json')
    collisions={name:read(REPORTS/f'{name}.json') for name in
                ['flat_reference_collision','flat_swing_simulation_collision','flat_wave_simulation_collision']}
    failures=[]
    if not strength['passed'] or abs(strength['mass_kg']-cad['total_mass_kg'])>1e-9:
        failures.append('Actual-load structural screening')
    if cad['failures'] or not exported['all_exported_parts_pass']:failures.append('Manufacturing export validation')
    if exported['urdf_joint_count']!=8 or exported['all_joint_axes']!=['0 1 0']*8:failures.append('Eight pitch axes')
    if not all(exported[k] for k in ['urdf_limits_match_design','urdf_joint_order_matches_design','urdf_mass_matches_CAD']):
        failures.append('URDF design contract')
    if not all(item['passed'] and item['exhaustive_exact'] for item in collisions.values()):failures.append('Reference/actual CAD collision')
    motions=['flat_palm_swing','flat_palm_wave']
    runs=['flat_palm_swing_release','flat_palm_wave_release']
    evidence={}
    for motion,run in zip(motions,runs):
        directory=OUT/'simulation_runs'/run
        result=read(directory/'result.json')
        media=read(directory/'media_check.json')
        reference=read(OUT/'motions'/motion/'report.json')
        poses=read(OUT/'motions'/motion/'poses.json')
        trace=read(directory/'trace.json')
        if not result['completed'] or result['fell'] or not result['stable_four_contact_landing']:
            failures.append(run+': completion/stable landing')
        if abs(result['total_mass_kg']-cad['total_mass_kg'])>1e-9 or any(abs(p['statics']['mass_kg']-cad['total_mass_kg'])>1e-9 for p in poses):
            failures.append(run+': inconsistent mass')
        if not reference['quasistatic_support_feasible'] or not reference['quasistatic_torque_target_met']:
            failures.append(motion+': quasi-static support or torque')
        if result['joint_limit_support_observed'] or result['peak_torque_nm']>.100001:
            failures.append(run+': actuator/limit force')
        if not media['decode_ok'] or not media['faststart'] or media['streams'][0]['codec_name']!='h264' or media['streams'][0]['pix_fmt']!='yuv420p':
            failures.append(run+': video validation')
        if motion=='flat_palm_swing':
            if not result['dynamic_palm_swing_observed'] or result['actual_forward_displacement_m']<=.001:
                failures.append(run+': airborne forward transfer')
        else:
            raised=[r for r in trace if r['pad_clearance_m'][0]>.05 and not r['pad_contact'][0] and r['nonpad_ground_contacts']==0]
            variation=np.ptp(np.array([r['q'][:2] for r in raised]),axis=0) if raised else np.zeros(2)
            if len(raised)<25 or min(variation)<.1:failures.append(run+': lifted hand movement')
        evidence[motion]={'result':result,'quasistatic_peak_Nm':reference['maximum_quasistatic_joint_torque_Nm'],
                          'video':f'output/simulation_runs/{run}/simulation.mp4',
                          'actual_trace_cad_collision_passed':collisions['flat_swing_simulation_collision' if motion=='flat_palm_swing' else 'flat_wave_simulation_collision']['passed']}
    status={'created_utc':datetime.now(timezone.utc).isoformat(),
            'status':'manufacturing_design_and_requested_finite_motions_verified_in_model' if not failures else 'not_released',
            'workspace_scope':'All project reads/writes limited to gpt_; no personal skills used',
            'full_requested_motion_release':not failures,
            'manufacturing_exports_passed':not cad['failures'] and exported['all_exported_parts_pass'],
            'failures':failures,'motor_count':8,'motor_model':'XL330-M288-T','joint_order':JOINT_NAMES,
            'joint_axes':'all pitch, URDF +Y','printed_assembly_piece_count':17,'additional_interface_coupon_count':2,
            'mass_estimate_kg':cad['total_mass_kg'],'neutral_bbox_xyz_mm':exported['neutral_assembly_bbox_mm'],
            'current_motion_names':motions,'current_simulation_runs':runs,'motion_evidence':evidence,
            'hardware_validated':False,'physical_prints_made':False,
            'limitations':['Forward transfer is a finite stroke with both rear feet airborne and stable landing; repeated hand-recovery walking is not provided.',
                           'Dynamics uses uncalibrated servo, friction and contact parameters; no hardware motion or thermal validation.',
                           'Sampled CAD checks exclude added fastener/cable solids and continuous motion between samples.',
                           'Print coupons, plastic-thread retention, adhesive bonding and layer strength need physical checks.'],
            'evidence':['reports/export_readback.json','reports/strength_actual_loads.json']+[f'reports/{name}.json' for name in collisions]}
    (REPORTS/'release_status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(json.dumps({'released':not failures,'failures':failures,'mass_kg':cad['total_mass_kg']},indent=2))
    if failures:raise SystemExit(2)


if __name__=='__main__':main()
