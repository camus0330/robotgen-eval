"""Export eight-axis URDF and a deliberately documented approximate MuJoCo model."""
import json, math, xml.etree.ElementTree as E
import numpy as np
import trimesh
from design import OUT, REPORTS, LIMBS, JOINT_NAMES, NEUTRAL_DEG, COLORS, ROOT_HEIGHT_MM

def s(v): return ' '.join(f'{float(x):.9g}' for x in v)

def inertia(link,d,index):
    c=np.array(d['com_mm'])/1000
    I=np.zeros((3,3))
    byname={o['name']:o for o in index}
    for a in d['items']:
        m=a['mass_kg']; ca=np.array(a['com_mm'])/1000
        if a.get('name') in byname:
            mesh=trimesh.load_mesh(OUT/byname[a['name']]['mesh'])
            mesh.apply_scale(.001)
            # Uniform shape-density inertia, with explicitly assigned component mass.
            prop=mesh.mass_properties
            ii=prop.inertia*(m/prop.mass)
        else:
            ii=np.eye(3)*m*.005**2/6
        dr=ca-c; I+=ii+m*((dr@dr)*np.eye(3)-np.outer(dr,dr))
    if min(np.linalg.eigvalsh(I))<=0: raise ValueError(f'Non-positive inertia {link}')
    return I

def main():
    mass=json.loads((REPORTS/'masslinks.json').read_text())
    index=json.loads((OUT/'assembly/objects.json').read_text())
    inertias={name:inertia(name,d,index) for name,d in mass.items()}
    r=E.Element('robot',name='gorilla8')
    for name,d in mass.items():
        l=E.SubElement(r,'link',name=name)
        ine=E.SubElement(l,'inertial'); E.SubElement(ine,'origin',xyz=s(np.array(d['com_mm'])/1000),rpy='0 0 0')
        E.SubElement(ine,'mass',value=str(d['mass_kg'])); ii=inertias[name]
        E.SubElement(ine,'inertia',**{k:f'{ii[i,j]:.10g}' for k,i,j in [('ixx',0,0),('ixy',0,1),('ixz',0,2),('iyy',1,1),('iyz',1,2),('izz',2,2)]})
        for o in [o for o in index if o['link']==name]:
            for typ in ['visual','collision']:
                node=E.SubElement(l,typ,name=o['name']); g=E.SubElement(node,'geometry')
                E.SubElement(g,'mesh',filename='../'+o['mesh'],scale='.001 .001 .001')
                if typ=='visual':
                    color=E.SubElement(node,'material',name=o['material']);E.SubElement(color,'color',rgba=s(COLORS[o['material']]))
    for i,l in enumerate(LIMBS):
        for j in [0,1]:
            joint=E.SubElement(r,'joint',name=JOINT_NAMES[i*2+j],type='revolute')
            E.SubElement(joint,'parent',link='base' if j==0 else l['name']+'_upper')
            E.SubElement(joint,'child',link=l['name']+('_upper' if j==0 else '_lower'))
            origin=l['origin_mm'] if j==0 else [0,0,-l['lengths_mm'][0]]
            E.SubElement(joint,'origin',xyz=s(np.array(origin)/1000),rpy='0 0 0')
            E.SubElement(joint,'axis',xyz='0 1 0')
            E.SubElement(joint,'limit',lower=str(math.radians(l['limits_deg'][j][0])),upper=str(math.radians(l['limits_deg'][j][1])),effort='.10',velocity='1.5')
            E.SubElement(joint,'dynamics',damping='.015',friction='.002')
    dest=OUT/'simulation';dest.mkdir(exist_ok=True)
    E.indent(r);E.ElementTree(r).write(dest/'gorilla8.urdf',encoding='utf-8',xml_declaration=True)
    m=E.Element('mujoco',model='gorilla8_approximate_contact')
    E.SubElement(m,'compiler',angle='radian',meshdir='../meshes',autolimits='true')
    E.SubElement(m,'option',timestep='.002',gravity='0 0 -9.81',integrator='implicitfast',iterations='60')
    visual=E.SubElement(m,'visual');E.SubElement(visual,'global',offwidth='1280',offheight='960')
    E.SubElement(visual,'headlight',ambient='.45 .45 .45',diffuse='.7 .7 .7',specular='.25 .25 .25')
    asset=E.SubElement(m,'asset')
    E.SubElement(asset,'texture',name='ground_texture',type='2d',builtin='checker',rgb1='.88 .9 .92',rgb2='.78 .81 .84',width='512',height='512')
    E.SubElement(asset,'material',name='ground_material',texture='ground_texture',texrepeat='12 12',reflectance='.05')
    for o in index: E.SubElement(asset,'mesh',name=o['name'],file=o['name']+'.stl',scale='.001 .001 .001')
    world=E.SubElement(m,'worldbody');E.SubElement(world,'light',pos='.2 -.3 .7',dir='-.2 .3 -.7')
    E.SubElement(world,'geom',name='ground',type='plane',size='1 1 .02',material='ground_material',contype='1',conaffinity='2',friction='.8 .01 .001',condim='3')
    base=E.SubElement(world,'body',name='base',pos=f'0 0 {ROOT_HEIGHT_MM/1000}')
    E.SubElement(base,'freejoint',name='floating_base')
    nodes={'base':base}
    for i,l in enumerate(LIMBS):
        up=E.SubElement(base,'body',name=l['name']+'_upper',pos=s(np.array(l['origin_mm'])/1000))
        lo=E.SubElement(up,'body',name=l['name']+'_lower',pos=f"0 0 {-l['lengths_mm'][0]/1000}")
        for j,node in enumerate([up,lo]):
            E.SubElement(node,'joint',name=JOINT_NAMES[2*i+j],type='hinge',axis='0 1 0',range=s(np.radians(l['limits_deg'][j])),damping='.015',armature='.000015',frictionloss='.002')
            nodes[l['name']+('_upper' if j==0 else '_lower')]=node
        # Front pad bounds relative to the palm: X[-45,20], Y[-17,17], Z[-12,-10] mm.
        # Keep geom names stable; rear pads retain their original cylindrical contact.
        contact=dict(name=l['name']+'_rocker',rgba='0 0 0 0',group='3',contype='2',conaffinity='1',
                     friction='.8 .01 .001',condim='3',solref='.008 1')
        if i<2:
            E.SubElement(lo,'geom',type='box',pos=s([-.0125,0,-l['lengths_mm'][1]/1000-.011]),
                         size='.0325 .017 .001',**contact)
        else:
            E.SubElement(lo,'geom',type='cylinder',pos=f"0 0 {-l['lengths_mm'][1]/1000}",
                         quat='.707106781 .707106781 0 0',size='.012 .019',**contact)
        # Capsules approximate limb ground impacts, NOT the CAD self-collision contract.
        for node,length in [(up,l['lengths_mm'][0]),(lo,l['lengths_mm'][1])]:
            E.SubElement(node,'geom',type='capsule',fromto=f'0 0 0 0 0 {-length/1000}',size='.006',rgba='0 0 0 0',group='3',contype='2',conaffinity='1')
    E.SubElement(base,'geom',type='box',pos='0 0 -.024',size='.014 .031 .033',rgba='0 0 0 0',group='3',contype='2',conaffinity='1')
    for name,d in mass.items():
        ii=inertias[name]
        E.SubElement(nodes[name],'inertial',pos=s(np.array(d['com_mm'])/1000),mass=str(d['mass_kg']),fullinertia=s([ii[0,0],ii[1,1],ii[2,2],ii[0,1],ii[0,2],ii[1,2]]))
        for o in [o for o in index if o['link']==name]:
            E.SubElement(nodes[name],'geom',name=o['name'],type='mesh',mesh=o['name'],rgba=s(COLORS[o['material']]),contype='0',conaffinity='0',group='1')
    act=E.SubElement(m,'actuator')
    for name in JOINT_NAMES:
        E.SubElement(act,'position',name=name+'_pd',joint=name,kp='2.0',kv='.055',forcerange='-.10 .10')
    key=E.SubElement(m,'keyframe');qpos=[0,0,ROOT_HEIGHT_MM/1000,1,0,0,0]+np.radians(NEUTRAL_DEG).tolist()
    E.SubElement(key,'key',name='neutral',qpos=s(qpos),ctrl=s(np.radians(NEUTRAL_DEG)))
    E.indent(m);E.ElementTree(m).write(dest/'gorilla8.xml',encoding='utf-8',xml_declaration=True)
    contract=dict(units='SI, radian',joint_order=JOINT_NAMES,axis=[0,1,0],root_frame='X forward, Y left, Z up',
                  neutral_deg=NEUTRAL_DEG,simulation_dt_s=.002,control_decimation=20,control_hz=25,
                  servo='XL330-M288-T, 5.0 V',continuous_torque_design_target_nm=.10,
                  current_mapping_calibrated=False,contact_friction_assumed=.8,self_contact_in_mujoco=False,
                  front_palm_contact=dict(shape='box',bounds_relative_to_palm_mm=[[-45,20],[-17,17],[-12,-10]]),
                  rear_foot_contact=dict(shape='cylinder',radius_mm=12,half_width_mm=19),
                  inertia_model='uniform CAD volume scaled to component mass; explicit point-mass allowances',
                  motor_id_order=list(range(1,9)),encoder_zero='Requires individual assembly calibration; not prescribed by neutral pose',
                  encoder_direction=[1,1,-1,-1,1,1,-1,-1],source_motion='analytic IK, not video or mocap')
    (dest/'contract.json').write_text(json.dumps(contract,indent=2)+'\n')
    print(dest)

if __name__=='__main__': main()
