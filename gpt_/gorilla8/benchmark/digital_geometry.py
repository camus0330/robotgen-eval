#!/usr/bin/env python3
"""BREP probes for explicitly enumerated Gorilla8 nominal interfaces, in mm."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import cadquery as cq


def cylinder(radius, height, start, direction=(0,1,0)):
    return cq.Solid.makeCylinder(radius,height,cq.Vector(*start),cq.Vector(*direction))


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();folder=args.root/'output/parts/step';checks=[];inputs={}
    def load(name):
        path=folder/(name+'.step');inputs[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        return cq.importers.importStep(str(path)).val()
    def probe(name,shape,solid,kind='void'):
        measured=shape.intersect(solid).Volume();expected=solid.Volume()
        passed=measured<1e-5 if kind=='void' else abs(measured-expected)<1e-5
        checks.append(dict(id=name,type=kind,intersection_mm3=measured,probe_volume_mm3=expected,passed=passed))
    for name in ['P02_upper_arm','P03_forearm_hand','P04_thigh','P05_shin_foot','C01_horn_fit_coupon']:
        shape=load(name)
        for side in ([1] if name.startswith('C01') else [-1,1]):
            lo=14.51 if side==1 else -19.99
            for x,z in [(6,0),(-6,0),(0,6),(0,-6)]:
                probe(f'{name}/side{side}/horn_hole_{x}_{z}',shape,cylinder(1.14,5.48,(x,lo,z)))
                ring=cylinder(1.5,.02,(x,18*side,z)).cut(cylinder(1.3,.02,(x,18*side,z)))
                probe(f'{name}/side{side}/support_ring_{x}_{z}',shape,ring,'material')
            probe(f'{name}/side{side}/center_tool',shape,cylinder(3.59,5.48,(0,lo,0)))
    saddle=load('C02_body_fit_coupon')
    for side in [-1,1]:
        lo=11.51 if side==1 else -14.49
        for x in [-8,8]:
            probe(f'C02/side{side}/case_hole_{x}',saddle,cylinder(1.14,2.98,(x,lo,-22.5)))
    # Measure grip on solid material beside the holes rather than at the empty axis.
    coupon=load('C01_horn_fit_coupon');radius=.04
    horn_grip=coupon.intersect(cylinder(radius,12,(7.5,10,0))).Volume()/(math.pi*radius**2)
    case_grip=saddle.intersect(cylinder(radius,5,(9.5,10,-22.5))).Volume()/(math.pi*radius**2)
    lengths=[dict(interface='horn',screw_length_mm=8,measured_grip_mm=horn_grip,
                  penetration_mm=8-horn_grip,max_penetration_mm=3,passed=0<8-horn_grip<=3),
             dict(interface='case_front',screw_length_mm=8,measured_grip_mm=case_grip,
                  cover_clearance_mm=3.5,engagement_mm=8-case_grip-3.5,available_pilot_depth_mm=15,
                  passed=0<8-case_grip-3.5<15),
             dict(interface='case_rear',screw_length_mm=8,measured_grip_mm=case_grip,
                  cover_clearance_mm=4.5,engagement_mm=8-case_grip-4.5,available_pilot_depth_mm=15,
                  passed=0<8-case_grip-4.5<15)]
    sensitivity=[dict(assumed_grip_error_mm=e,horn_max_penetration_mm=8-(horn_grip-e),
                      horn_max3mm_met=8-(horn_grip-e)<=3) for e in [.05,.1,.2,.5]]
    report=dict(units='mm',checks=checks,nominal_interface_pass=all(r['passed'] for r in checks),
                length_chains=lengths,length_chain_pass=all(r['passed'] for r in lengths),
                sensitivity=sensitivity,input_sha256=inputs,
                limitations=['Nominal geometric probes; not a full tool insertion sweep or assembly sequence.',
                             'Only OEM horn and case mounting chains; no assertion about every added fastener.',
                             'Screw length and OEM pilot geometry are nominal; plastic pullout strength is not tested.',
                             'Sensitivity uses assumed errors, not measured print tolerances.'])
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,indent=2))
    print(json.dumps({'probes':len(checks),'interfaces_pass':report['nominal_interface_pass'],
                      'lengths_pass':report['length_chain_pass'],'failed_probes':[r['id'] for r in checks if not r['passed']]},indent=2))


if __name__=='__main__':main()
