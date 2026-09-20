"""Read delivered STEP/STL back; preserve inward cavity shells in volume checks."""
import json
import xml.etree.ElementTree as E
import cadquery as cq
import trimesh
import numpy as np
from design import ROOT,OUT,REPORTS,LIMBS,JOINT_NAMES

def main():
    catalog={r['name']:r for r in json.loads((REPORTS/'print_parts.json').read_text())}
    rows=[]
    for p in sorted((OUT/'parts/stl').glob('*.stl')):
        mesh=trimesh.load_mesh(p)
        shape=cq.importers.importStep(str(OUT/'parts/step'/f'{p.stem}.step')).val()
        shells=[c.volume for c in mesh.split(only_watertight=False)]
        source_volume=catalog[p.stem]['volume_mm3']
        rows.append(dict(name=p.stem,stl_watertight=bool(mesh.is_watertight),
                         stl_volume_mm3=float(mesh.volume),positive_outer_shells=int(sum(v>1e-6 for v in shells)),
                         negative_cavity_shells=int(sum(v< -1e-6 for v in shells)),
                         step_valid=bool(shape.isValid()),step_solid_count=len(shape.Solids()),
                         step_volume_mm3=shape.Volume(),source_volume_mm3=source_volume,
                         step_volume_relative_error=abs(shape.Volume()/source_volume-1),
                         stl_volume_relative_error=abs(mesh.volume/source_volume-1),
                         print_min_z_mm=float(mesh.bounds[0,2])))
    for p in (ROOT/'src').glob('*.py'):compile(p.read_text(),str(p),'exec')
    scene=trimesh.load(OUT/'assembly/gorilla8_neutral.glb',force='scene')
    urdf=E.parse(OUT/'simulation/gorilla8.urdf').getroot()
    joints=urdf.findall('joint')
    expected_limits=np.radians([pair for limb in LIMBS for pair in limb['limits_deg']])
    actual_limits=np.array([[float(j.find('limit').get(k)) for k in ['lower','upper']] for j in joints])
    urdf_mass=sum(float(link.find('inertial/mass').get('value')) for link in urdf.findall('link'))
    cad_mass=sum(p['mass_kg'] for p in json.loads((REPORTS/'masslinks.json').read_text()).values())
    failures=[r['name'] for r in rows if not(r['stl_watertight'] and r['stl_volume_mm3']>0 and
               r['positive_outer_shells']==1 and r['step_valid'] and r['step_solid_count']==1 and
               r['step_volume_relative_error']<.001 and r['stl_volume_relative_error']<.015 and abs(r['print_min_z_mm'])<.001)]
    result=dict(parts=rows,all_exported_parts_pass=not failures,failures=failures,
                urdf_joint_count=len(joints),all_joint_axes=[j.find('axis').get('xyz') for j in joints],
                neutral_assembly_bbox_mm=(scene.extents*1000).tolist(),syntax_passed=True,
                urdf_limits_match_design=bool(np.allclose(actual_limits,expected_limits,rtol=0,atol=1e-8)),
                urdf_joint_order_matches_design=[j.get('name') for j in joints]==JOINT_NAMES,
                urdf_mass_kg=urdf_mass,urdf_mass_matches_CAD=abs(urdf_mass-cad_mass)<1e-8,
                volume_tolerances=dict(STEP_relative=.001,STL_relative=.015),
                note='One positive outer STL shell; negative closed cavity shells are intentional voids, not detached parts.')
    (REPORTS/'export_readback.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if failures:raise RuntimeError('Delivered export read-back failed: '+str(failures))
    if len(joints)!=8 or any(j.find('axis').get('xyz')!='0 1 0' for j in joints):raise RuntimeError('Joint contract mismatch')
    if not result['urdf_limits_match_design'] or not result['urdf_joint_order_matches_design'] or not result['urdf_mass_matches_CAD']:
        raise RuntimeError('URDF differs from final design/mass contract')

if __name__=='__main__':main()
