"""Reproducible ideal-section screening of the final simulation contact loads.

This is a sectional arithmetic screen, not an FEA or a hardware strength test.
The component envelopes bound every recorded 2 ms sample even when their
individual peaks occur at different times. Coherent peak events are also kept.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np

from design import ROOT, REPORTS


def rectangle_torsion(a, b):
    a, b = max(a, b), min(a, b)
    return a*b**3*(1/3-.21*(b/a)*(1-b**4/(12*a**4)))


def section(name, rectangles, beam_axis, reference_mm, torsion_J, torsion_t, shear_areas):
    """Rectangles are (u_min,u_max,v_min,v_max) in the section plane."""
    area = sum((u1-u0)*(v1-v0) for u0,u1,v0,v1 in rectangles)
    center = sum(np.array([(u0+u1)/2,(v0+v1)/2])*(u1-u0)*(v1-v0)
                 for u0,u1,v0,v1 in rectangles)/area
    inertia = np.zeros((2,2))
    vertices = []
    for u0,u1,v0,v1 in rectangles:
        w,h = u1-u0,v1-v0
        offset = np.array([(u0+u1)/2,(v0+v1)/2])-center
        inertia += np.diag([h*w**3/12,w*h**3/12])+w*h*np.outer(offset,offset)
        vertices.extend([[u-center[0],v-center[1]] for u in [u0,u1] for v in [v0,v1]])
    return dict(name=name,area_mm2=area,section_center_uv_mm=center.tolist(),
                inertia_uv_mm4=inertia.tolist(),vertices_from_center_mm=vertices,
                beam_axis=beam_axis,reference_mm=reference_mm,
                torsion_J_mm4=torsion_J,torsion_stress_coefficient_per_mm3=torsion_t/torsion_J,
                shear_areas_mm2=shear_areas)


def sections(side):
    # These are explicit dimensions of the full-height shoulder bridge release.
    rear_z = (68*(-9)+48*(-5))/116
    return {
        'rear_extension': section('rear_extension', [(-17,17,-10,-8),(-17,-13,-8,-2),(13,17,-8,-2)],
                                  0,[-11,0,rear_z],rectangle_torsion(34,2)+2*rectangle_torsion(6,4),4,[68,48]),
        'front_toe': section('front_toe',[(-17,17,-10,-7)],0,[11,0,-8.5],rectangle_torsion(34,3),3,[102,102]),
        'root': section('root',[(-8.5,7.5,-28,-15)],1,[-.5,side*29,-21.5],rectangle_torsion(16,13),13,[208,208]),
        'notch': section('notch',[(-8.5,5.5,-28,-15)],1,[-1.5,side*35,-21.5],rectangle_torsion(14,13),13,[182,182]),
        'cup_interface': section('cup_interface',[(41.5,56,-28,-15)],0,[6.6,side*48.75,-21.5],
                                 rectangle_torsion(14.5,13),13,[188.5,188.5]),
    }


def stress(sec, force, moment_nm, envelope):
    force, moment = np.asarray(force),1000*np.asarray(moment_nm)
    axis = sec['beam_axis']
    transverse = [1,2] if axis==0 else [0,2]
    # Stress-resultant signs from r cross (sigma * beam_axis).
    bending = np.array([-moment[2],moment[1]]) if axis==0 else np.array([moment[2],-moment[0]])
    coeff = np.asarray(sec['vertices_from_center_mm'])@np.linalg.inv(sec['inertia_uv_mm4'])
    axial = force[axis]/sec['area_mm2']
    if envelope:
        normal = abs(axial)+float(np.max(np.abs(coeff)@np.abs(bending)))
    else:
        normal = float(np.max(np.abs(axial+coeff@bending)))
    torsion = abs(moment[axis])*sec['torsion_stress_coefficient_per_mm3']
    shear = 1.5*sum(abs(force[i])/area for i,area in zip(transverse,sec['shear_areas_mm2']))
    equivalent = math.sqrt(normal**2+3*(torsion+shear)**2)
    return dict(normal_stress_bound_MPa=normal,torsion_shear_estimate_MPa=torsion,
                transverse_shear_bound_MPa=shear,von_mises_bound_MPa=equivalent,
                stress_with_concentration_2_MPa=2*equivalent,
                stress_with_concentration_2_and_reserve_3_MPa=6*equivalent,
                margin_to_assumed_8_MPa=8/(6*equivalent) if equivalent else None,
                passed=6*equivalent<=8)


def check_section_geometry():
    """Verify the assumed material prisms are contained in the exported STEP."""
    import cadquery as cq
    folder=ROOT/'output/parts/step'
    torso=cq.importers.importStep(str(folder/'P01_torso_frame.step')).val()
    palm=cq.importers.importStep(str(folder/'P03_forearm_hand.step')).val()
    checks=[]
    def check(name,body,bounds):
        x0,x1,y0,y1,z0,z1=bounds
        prism=cq.Solid.makeBox(x1-x0,y1-y0,z1-z0,cq.Vector(x0,y0,z0))
        missing=max(0.,prism.Volume()-body.intersect(prism).Volume())
        checks.append(dict(section=name,prism_bounds_mm=bounds,missing_material_mm3=missing,passed=missing<1e-6))
    for side in (1,-1):
        for name,x0,x1,y0,y1 in [('root',-8.5,7.5,29,29.02),('notch',-8.5,5.5,35.01,35.03),('cup_interface',6.6,6.62,41.5,56)]:
            y0,y1=sorted([side*y0,side*y1])
            check(f'{name}_{side}',torso,[x0,x1,y0,y1,-28,-15])
    for name,x0,x1,rectangles in [('rear_extension',-11.03,-11.01,[(-17,17,-10,-8),(-17,-13,-8,-2),(13,17,-8,-2)]),
                                 ('front_toe',11.01,11.03,[(-17,17,-10,-7)])]:
        for y0,y1,z0,z1 in rectangles:
            check(name,palm,[x0,x1,y0,y1,z0-76,z1-76])
    return checks


def audit(paths):
    mass = json.loads((REPORTS/'cad_checks.json').read_text())['total_mass_kg']
    cases, errors, sources = [], [], []
    for path in paths:
        data = json.loads(path.read_text())
        if not math.isclose(data['total_mass_kg'],mass,abs_tol=1e-9):
            errors.append(f'{path.name}: simulation mass differs from CAD mass')
        if data['dt_s']!=.002:
            errors.append(f'{path.name}: expected explicitly instrumented 0.002 s load sample interval')
        sources.append(dict(path=str(path.relative_to(ROOT)),mass_kg=data['total_mass_kg'],
                            timestep_s=data['dt_s'],duration_s=data['duration_s']))
        for arm,loads in data['palm_contact_load_peaks_2ms']['all_steps'].items():
            side = {'left_arm':1,'right_arm':-1}[arm]
            for name,sec in sections(side).items():
                palm = name in ('rear_extension','front_toe')
                load = loads['section_loads' if palm else 'shoulder_bridge_contact'][name]
                frame = 'local' if palm else 'base'
                force_key = f'force_{frame}_N'
                moment_key = f'moment_about_section_{frame}_Nm'
                point_key = 'section_point_relative_palm_m' if palm else 'section_point_base_m'
                peak_events=[]
                for component in 'xyz':
                    event = load[f'moment_{component}_peak_event']
                    if not np.allclose(np.array(event[point_key])*1000,sec['reference_mm'],rtol=0,atol=1e-6):
                        errors.append(f'{path.parent.name}/{arm}/{name}: section reference does not match geometry')
                    peak_events.append(dict(component=component,event=event,
                                            stress=stress(sec,event[force_key],event[moment_key],False)))
                force = load[force_key+'_component_abs_peak']
                moment = load[moment_key+'_component_abs_peak']
                cases.append(dict(run=path.parent.name,arm=arm,section=name,
                                  force_component_abs_envelope_N=force,moment_component_abs_envelope_Nm=moment,
                                  envelope_stress=stress(sec,force,moment,True),coherent_peak_events=peak_events))
    if len(cases)!=20:
        errors.append('Expected two motions x two arms x five section cases.')
    geometry=check_section_geometry()
    return dict(passed=bool(cases) and not errors and all(c['envelope_stress']['passed'] for c in cases) and all(g['passed'] for g in geometry),
                mass_kg=mass,errors=errors,sources=sources,case_count=len(cases),cases=cases,
                sections=sections(1),exported_STEP_section_material_checks=geometry,
                method=dict(loads='Actual 2 ms contact loads, all_steps; no assumed equal sharing between hands.',
                            envelope='Per-component absolute maxima form a conservative envelope over all recorded samples; not a simultaneous measured wrench.',
                            normal='Axial plus biaxial bending from the full 2x2 section inertia matrix; evaluate section vertices.',
                            torsion='Saint-Venant rectangle J approximation; tau approximately T*short_side/J. Rear open U uses the sum of its three finite-width rectangle J values.',
                            transverse_shear='1.5*(abs(Vu)/Au + abs(Vv)/Av); rear U uses base area 68 and combined rib area 48 mm2.',
                            combination='von Mises upper estimate sqrt(sigma_bound^2 + 3*(tau_torsion + tau_transverse_bound)^2).',
                            stress_concentration_assumption=2,additional_reserve_multiplier=3,
                            reserve_meaning='The simulation already contains modeled dynamics. Factor 3 is an extra conservative reserve, not a measured dynamic amplification.',
                            assumed_allowable_MPa=8,assumed_isotropic_PETG=True,full_infill_required=True),
                limitations=['Ideal beam-section arithmetic only; not full 3D FEA or material certification.',
                             'Shoulder and cup cases contain the contact-wrench contribution only; full limb gravity/inertia internal stress is not reconstructed.',
                             'Does not certify creep, fatigue, print anisotropy, local warping, notch stresses, screw bearing, screw pullout or motor plastic.',
                             'Does not validate glue strength, TPU friction or hardware temperature and durability.',
                             'Other printed components and fasteners are outside this actual-load audit; see the separate simple strength_screen report.'],
                hardware_validated=False,
                references=['https://ocw.mit.edu/courses/16-20-structural-mechanics-fall-2002/15610a00dfce40d899a2ea0cbe414e57_unit11.pdf',
                            'https://www.mdpi.com/2075-5309/15/21/3926'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulation-result',action='append',type=Path,required=True)
    args=parser.parse_args()
    paths=[p.resolve() for p in args.simulation_result]
    if len(paths)!=2 or len(set(paths))!=2:
        parser.error('Provide the two distinct final motion result.json paths.')
    for path in paths:
        path.relative_to(ROOT)
    report=audit(paths)
    (REPORTS/'strength_actual_loads.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(passed=report['passed'],mass_kg=report['mass_kg'],case_count=report['case_count'],
                          errors=report['errors'],worst_screen_MPa=max(c['envelope_stress']['stress_with_concentration_2_and_reserve_3_MPa'] for c in report['cases'])),indent=2))
    raise SystemExit(0 if report['passed'] else 1)


if __name__=='__main__':
    main()
