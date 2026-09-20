"""Parametric, millimetre CAD; export real print solids and articulated assembly."""
import json, math, csv
from pathlib import Path
import cadquery as cq
import numpy as np
import trimesh
from design import ROOT, OUT, REPORTS, INPUT_STEP, LIMBS, JOINT_NAMES, COLORS, transforms, PALM_X_MIN_MM, PALM_X_MAX_MM

def box(x0,x1,y0,y1,z0,z1):
    return cq.Solid.makeBox(x1-x0,y1-y0,z1-z0,cq.Vector(x0,y0,z0))

def cy(r,h,p,axis=(0,1,0)):
    return cq.Solid.makeCylinder(r,h,cq.Vector(*p),cq.Vector(*axis))

def union(*s):
    return s[0].fuse(*s[1:]).clean() if len(s)>1 else s[0]

def ellipsoid(r,p):
    m=cq.Matrix([[r[0],0,0,0],[0,r[1],0,0],[0,0,r[2],0],[0,0,0,1]])
    return cq.Solid.makeSphere(1,angleDegrees1=-90).transformGeometry(m).translate(p)

def hex_z(x,y,z,h,af=4.1):
    return cq.Workplane('XY',origin=(x,y,z)).polygon(6,af/math.cos(math.pi/6)).extrude(h).val()

def motor_saddle():
    # Datums: source Z + 8 -> robot local Y, source Y -> local Z.
    # Stock body faces +/-11.5; stock horn faces +/-14.5 mm.
    a=union(box(-13.4,13.4,-14.5,14.5,-28,-24.8),
            box(-13.4,13.4,11.5,14.5,-28,-15.0),
            box(-13.4,13.4,-14.5,-11.5,-28,-15.0),
            box(-13.4,-10.35,-11.5,11.5,-28,-15.0),
            box(10.35,13.4,-11.5,11.5,-28,-15.0))
    for x in [-8,8]:
        a=a.cut(cy(1.15,40,(x,-20,-22.5)))
        # 1 mm head recess leaves 2 mm PETG grip for the stock ST2x8.
        a=a.cut(cy(2.1,1.01,(x,13.5,-22.5)))
        a=a.cut(cy(2.1,1.01,(x,-14.51,-22.5)))
    return a.clean()

def rotor_fork():
    # 2.5 mm stand-off + 3 mm plate = 5.5 mm grip; ST2x8 engages 2.5 mm.
    # Stand-off passes outside stationary case screw heads; it is NOT a bearing.
    cheeks=[]
    for s in [-1,1]:
        ymin=17 if s>0 else -20
        cheek=union(cy(10.5,3,(0,ymin,0)), box(-7,7,ymin,ymin+3,-38,0))
        boss=cy(8,2.5,(0,14.5 if s>0 else -17,0))
        cheek=union(cheek,boss)
        cheek=cheek.cut(cy(3.6,10,(0,12 if s>0 else -22,0)))
        for x,z in [(6,0),(-6,0),(0,6),(0,-6)]:
            cheek=cheek.cut(cy(1.15,10,(x,12 if s>0 else -22,z)))
        # Open waist retains two continuous ribs and room for the wire service loop.
        cheek=cheek.cut(box(-2.5,2.5,ymin-1,ymin+4,-29,-16))
        cheeks.append(cheek)
    return union(*cheeks,box(-7,7,-20,20,-39,-35))

def upper(L,elbow_sign):
    # A side spine connects the fork to the next stator without entering its sweep.
    xside=25*elbow_sign
    pts=[(-7,-35),(7,-35),(xside+4.5,-L+11),(xside+4.5,-L-28),
         (xside-4.5,-L-28),(xside-4.5,-L+7),(-7,-39)]
    # Negative-side spine is the exact mirror of the positive-side one.
    if elbow_sign<0:
        pos=upper(L,1)
        return pos.mirror('YZ')
    spine=cq.Workplane('XZ',origin=(0,3,0)).polyline(pts).close().extrude(6).val()
    a=union(rotor_fork(),spine,motor_saddle().translate((0,0,-L)),
            box(10.35,29.5,-5,5,-L-28,-L-24.8))
    # Axial wire tie slots, deliberately outside the structural neck.
    a=a.cut(box(21,24,-6,6,-L-15,-L-12))
    return a.clean()

def palm_rigid(width,flat=False):
    p=cy(11,width,(0,-width/2,0)).intersect(box(-20,20,-width,width,-3,11))
    # Four finger lobes; same part, joined at the palm.
    for j in range(4):
        y=-width/2+(j+.5)*width/4
        p=union(p,ellipsoid((6,width/8-.4,5),(7,y,4)))
    cavity=box(-6,6,-width/2+2,width/2-2,-.5,7.5)
    for y in [-9,9]: cavity=cavity.cut(cy(3.4,12,(0,y,-2),(0,0,1)))
    # The central web remains under the hollow forearm tube.
    cavity=cavity.cut(box(-7,7,-3,3,-2,10))
    p=p.cut(cavity)
    if flat:
        # A broad fixed sole gives the two palms a finite fore-aft support polygon.
        # The two ribs carry heel bending into the original palm, without a wrist.
        p=union(p,box(PALM_X_MIN_MM,PALM_X_MAX_MM,-width/2,width/2,-10,-8),
                box(11,PALM_X_MAX_MM,-width/2,width/2,-8,-7),
                box(PALM_X_MIN_MM,11,-width/2,-width/2+4,-8,-2),
                box(PALM_X_MIN_MM,11,width/2-4,width/2,-8,-2),
                *[cy(3.4,6,(0,y,-8),(0,0,1)) for y in [-9,9]])
    for y in [-9,9]:
        p=p.cut(cy(1.15,30,(0,y,-15),(0,0,1)))
        p=p.cut(hex_z(0,y,6.8,6))
        if flat: p=p.cut(cy(2.6,6,(0,y,-15),(0,0,1)))
    return p.clean()

def lower(L,width,flat=False):
    outer=box(-7,7,-8,8,-L+7,-35)
    cavity=box(-4.5,4.5,-5.5,5.5,-L+10,-34)
    return union(rotor_fork(),outer.cut(cavity),palm_rigid(width,flat).translate((0,0,-L)))

def pad(width,flat=False):
    a=(box(PALM_X_MIN_MM,PALM_X_MAX_MM,-width/2,width/2,-12,-10) if flat else
       cy(12,width,(0,-width/2,0)).intersect(box(-20,20,-width,width,-13,-3)))
    for y in [-9,9]:
        a=a.cut(cy(1.15,20,(0,y,-15),(0,0,1)))
        a=a.cut(cy(2.6,6,(0,y,-15),(0,0,1)))
    return a.clean()

def torso():
    # Open cage: two frames and four rails, accessible from the back.
    a=union(box(-14,12,-31,31,-64,-60),box(-14,12,-31,31,3,8),
            box(-14,-10,-31,-26,-62,5),box(-14,-10,26,31,-62,5),
            box(8,12,-31,-26,-62,5),box(8,12,26,31,-62,5))
    # Lighten upper/lower deck; leave head mounting bridge and cable tie rails.
    a=a.cut(box(-8,6,-22,22,-66,-59))
    a=a.cut(box(-9,7,-9,9,2,9))
    for l in LIMBS:
        x,y,z=l['origin_mm']
        a=union(a,motor_saddle().translate((x,y,z)))
        if 'arm' in l['name']:
            # Full-height connection to the cup sidewall; no thin attachment lip.
            b=union(box(x-28.5,x-12.5,min(0,y),max(0,y),z-28,z-15),
                    box(-12,8.5,-29,29,z-28,z-15))
        else:
            # Attach the hip cup to the lower rear frame, outside the elbow sweep.
            b=box(-13,-5,min(0,y),max(0,y),-64,-57.8)
        a=union(a,b)
    # Inner fork cheek sweep at the +12-degree shoulder boundary.
    for y0,y1 in [(35,40),(-40,-35)]:
        a=a.cut(box(5.5,8.5,y0,y1,-28.1,-14.9))
    # Two low trays for external-power controller/power distribution; strap slots.
    a=union(a,box(-12,12,-29,29,-53,-50))
    for y in [-19,19]: a=a.cut(box(-8,8,y-1.3,y+1.3,-54,-49))
    # Four shell standoffs along X, with captive ordinary M2 nuts behind.
    for y in [-20,20]:
        for z in [-41,-12]:
            a=union(a,box(8,20,min(y-4,1.45*y),max(y+4,1.45*y),z-4,z+4))
            a=a.cut(cy(1.15,18,(5,y,z),(1,0,0)))
            # Hex pocket faces backwards; accessible with chest removed.
            h=cq.Workplane('YZ',origin=(8,y,z)).polygon(6,4.1/math.cos(math.pi/6)).extrude(2.2).val()
            a=a.cut(h)
    for y in [-15,15]: a=a.cut(cy(1.15,10,(0,y,0),(0,0,1)))
    return a.clean()

def chest():
    outer=ellipsoid((25,38,38),(3,0,-25))
    inner=ellipsoid((23.2,36.2,36.2),(3,0,-25))
    a=outer.cut(inner).intersect(box(20,40,-45,45,-63,12))
    for y in [-20,20]:
        for z in [-41,-12]:
            # Mount tab bridges from planar frame face to curved skin.
            a=union(a,box(20,24,y-4,y+4,z-4,z+4))
            a=a.cut(cy(1.15,15,(18,y,z),(1,0,0)))
            a=a.cut(cy(2.5,10,(23,y,z),(1,0,0)))
    return a.clean()

def head():
    a=ellipsoid((19,25,27),(6,0,33)).cut(ellipsoid((17,23,25),(6,0,33)))
    # Open the neck with positive area; a tangent inner ellipsoid at Z=8 is
    # liable to become a wrongly oriented closed cavity on STEP round-trip.
    a=a.intersect(box(-30,45,-40,40,10,65))
    a=union(a,ellipsoid((9,17,10),(23,0,25)))
    for y in [-10,10]:
        a=union(a,ellipsoid((6,8,7),(21,y,40)))
        a=a.cut(cy(5.1,25,(12,y,40),(1,0,0)))
    for s in [-1,1]:
        ear=cy(8,6,(6,23*s if s>0 else -29,34))
        ear=ear.cut(cy(5,4,(6,26 if s>0 else -30,34)))
        a=union(a,ear)
    for y in [-4,4]: a=a.cut(cy(1.7,8,(28,y,29),(1,0,0)))
    a=a.cut(ellipsoid((6.5,14.5,7.5),(23,0,25)))
    a=a.cut(box(30.2,35,-9,9,21,21.8))
    a=union(a,box(-5,5,-21,21,8,11))
    for y in [-15,15]:
        a=a.cut(cy(1.15,10,(0,y,6),(0,0,1)))
        a=a.cut(hex_z(0,y,9,5))
    return a.clean()

def eye():
    dome=ellipsoid((3.5,5.8,5.8),(26,0,40)).intersect(box(26,31,-7,7,33,47))
    return union(cy(5,6,(20,0,40),(1,0,0)),dome)

def tm(shape):
    v,f=shape.tessellate(.03,.08)
    m=trimesh.Trimesh(vertices=np.array([p.toTuple() for p in v]),faces=f,process=True)
    m.update_faces(m.nondegenerate_faces())
    m.update_faces(m.unique_faces())
    m.remove_unreferenced_vertices()
    # Inner cavity shells must retain negative signed volume.
    m.fix_normals(multibody=False)
    return m

def located(shape,R,t):
    # OCCT shape transform preserves analytic geometry and supports rotations only.
    from OCP.gp import gp_Trsf
    tr=gp_Trsf()
    tr.SetValues(*[float(v) for row in np.column_stack((R,t)) for v in row])
    return shape.moved(cq.Location(tr))

def build():
    for p in ['parts/step','parts/stl','assembly','meshes','renders','motions']: (OUT/p).mkdir(parents=True,exist_ok=True)
    REPORTS.mkdir(parents=True,exist_ok=True)
    shapes={'P01_torso_frame':torso(),'P02_upper_arm':upper(60,1),
            'P03_forearm_hand':lower(76,34,flat=True),'P04_thigh':upper(55,-1),
            'P05_shin_foot':lower(52,38),'P06_palm_pad':pad(34,flat=True),'P07_foot_pad':pad(38),
            'P08_chest_shell':chest(),'P09_head_shell':head(),'P10_eye_insert':eye()}
    # Coupons are functional scale-one interfaces, not a miniature robot.
    shapes['C01_horn_fit_coupon']=rotor_fork().intersect(box(-12,12,12,22,-12,12))
    shapes['C02_body_fit_coupon']=motor_saddle()
    qty={'P01_torso_frame':1,'P02_upper_arm':2,'P03_forearm_hand':2,'P04_thigh':2,
         'P05_shin_foot':2,'P06_palm_pad':2,'P07_foot_pad':2,'P08_chest_shell':1,
         'P09_head_shell':1,'P10_eye_insert':2,'C01_horn_fit_coupon':1,'C02_body_fit_coupon':1}
    catalog=[]
    for name,s in shapes.items():
        m=tm(s); b=s.BoundingBox()
        mat='TPU' if 'pad' in name else 'PETG'
        rec=dict(name=name,quantity=qty[name],material=mat,solid_count=len(s.Solids()),valid=s.isValid(),
                 watertight=bool(m.is_watertight),volume_mm3=s.Volume(),
                 bbox_mm=[b.xlen,b.ylen,b.zlen],mass_full_solid_g=s.Volume()*({'PETG':1.27,'TPU':1.21}[mat])/1000)
        # Assembly-local STEP is authoritative; print STL is translated onto build plate.
        cq.exporters.export(s,str(OUT/'parts/step'/f'{name}.step'))
        # Orient flat fork cheek on build plate. TPU pads print on their flat mating face.
        if name=='C01_horn_fit_coupon':
            printshape=s.rotate((0,0,0),(1,0,0),-90)
        elif name.startswith(('P02','P03','P04','P05','C02')):
            printshape=s.rotate((0,0,0),(1,0,0),90)
        elif 'pad' in name: printshape=s.rotate((0,0,0),(1,0,0),180)
        elif 'eye' in name: printshape=s.rotate((0,0,0),(0,1,0),90)
        else: printshape=s
        b2=printshape.BoundingBox()
        printshape=printshape.translate((-b2.xmin,-b2.ymin,-b2.zmin))
        pm=tm(printshape)
        pm.apply_translation(-pm.bounds[0])
        pm.export(str(OUT/'parts/stl'/f'{name}.stl'))
        rec['print_bbox_mm']=pm.extents.tolist()
        catalog.append(rec)
        print(name,rec,flush=True)
    # Split purchased motor into parent stator and child rotors from the supplied source.
    ss=cq.importers.importStep(str(INPUT_STEP)).val().Solids()
    stator=cq.Compound.makeCompound([s for i,s in enumerate(ss) if i not in [3,10]])
    rotors=cq.Compound.makeCompound([ss[3],ss[10]])
    objects=[]
    def add(name,shape,link,material,part=None,mass=None):
        objects.append(dict(name=name,shape=shape,link=link,material=material,part=part,mass=mass))
    for p in ['P01_torso_frame','P08_chest_shell','P09_head_shell']:
        add(p,shapes[p],'base','face' if 'head' in p else 'PETG',p)
    for j,y in enumerate([-10,10]): add(f'eye_{j}',shapes['P10_eye_insert'].translate((0,y,0)),'base','eyes','P10_eye_insert')
    for l in LIMBS:
        name=l['name']; arm='arm' in name; s=l['side']; L1,L2=l['lengths_mm']
        origin=np.array(l['origin_mm'])
        up,lo=name+'_upper',name+'_lower'
        for part,link,shift in [(('P02_upper_arm' if arm else 'P04_thigh'),up,[0,0,0]),
                                (('P03_forearm_hand' if arm else 'P05_shin_foot'),lo,[0,0,0]),
                                (('P06_palm_pad' if arm else 'P07_foot_pad'),lo,[0,0,-L2])]:
            add(name+'_'+part,shapes[part].translate(shift),link,'TPU' if 'pad' in part else 'PETG',part)
        R=np.array([[-s,0,0],[0,0,s],[0,1,0]],dtype=float)
        motor_shift=np.array([0,8*s,0])
        for j,parent,child,pos in [(0,'base',up,origin),(1,up,lo,np.array([0,0,-L1]))]:
            add(f'{name}_motor_{j}_case',located(stator,R,motor_shift+pos),parent,'motor',mass=.0168)
            add(f'{name}_motor_{j}_rotors',located(rotors,R,motor_shift),child,'horn',mass=.0022)
    # Hardware and wiring allowances are explicit masses, NOT hidden CAD volume.
    allowances=[dict(link='base',mass_kg=.035,com_mm=[0,0,-46],description='external-power controller + distribution + torso wiring'),
                dict(link='base',mass_kg=.008,com_mm=[0,0,-20],description='torso screws/nuts/straps')]
    for l in LIMBS:
        for suffix,L in [('upper',l['lengths_mm'][0]),('lower',l['lengths_mm'][1])]:
            allowances.append(dict(link=l['name']+'_'+suffix,mass_kg=.005,com_mm=[0,0,-L/2],description='screws, nuts and flexible cable allowance'))
    masslinks={}
    ts=transforms(); scene=trimesh.Scene(); assembly=cq.Assembly(name='gorilla8')
    index=[]
    for o in objects:
        shape=o['shape']; name=o['name']; link=o['link']; mat=o['material']
        density=1.21 if mat=='TPU' else 1.27
        mass=o['mass'] if o['mass'] is not None else shape.Volume()*density/1e6
        com=np.array(shape.Center().toTuple())
        d=masslinks.setdefault(link,dict(mass_kg=0.,weighted=np.zeros(3),items=[]))
        d['mass_kg']+=mass; d['weighted']+=mass*com
        d['items'].append(dict(name=name,mass_kg=mass,com_mm=com.tolist(),material=mat))
        m=tm(shape); m.visual.vertex_colors=np.array(COLORS[mat])*255
        m.export(str(OUT/'meshes'/f'{name}.stl'))
        r,t=ts[link]; T=np.eye(4);T[:3,:3]=r;T[:3,3]=t
        scene.add_geometry(m,node_name=name,geom_name=name,transform=T)
        assembly.add(located(shape,r,t),name=name,color=cq.Color(*COLORS[mat]))
        index.append(dict(name=name,link=link,material=mat,part=o['part'],mesh=f'meshes/{name}.stl',mass_kg=mass,com_mm=com.tolist()))
    for a in allowances:
        d=masslinks[a['link']];d['mass_kg']+=a['mass_kg'];d['weighted']+=a['mass_kg']*np.array(a['com_mm']);d['items'].append(a)
    for d in masslinks.values(): d['com_mm']=(d.pop('weighted')/d['mass_kg']).tolist()
    scene.apply_scale(.001)
    scene.export(str(OUT/'assembly/gorilla8_neutral.glb'))
    assembly.save(str(OUT/'assembly/gorilla8_neutral.step'))
    (OUT/'assembly/objects.json').write_text(json.dumps(index,indent=2))
    (REPORTS/'masslinks.json').write_text(json.dumps(masslinks,indent=2))
    (REPORTS/'print_parts.json').write_text(json.dumps(catalog,indent=2))
    (OUT/'parts/parts.csv').write_text('part,quantity,material,print_bbox_mm,full_solid_mass_g\n'+'\n'.join(
        f"{r['name']},{r['quantity']},{r['material']},\"{','.join(f'{x:.1f}' for x in r['print_bbox_mm'])}\",{r['mass_full_solid_g']:.2f}" for r in catalog)+'\n')
    total=sum(d['mass_kg'] for d in masslinks.values())
    print('TOTAL MASS KG including hardware/electronics allowance',total,flush=True)
    # Coupons may consist of two detached cheeks by design; robot parts may not.
    failures=[r['name'] for r in catalog if not r['valid'] or not r['watertight'] or (r['name'].startswith('P') and r['solid_count']!=1)]
    (REPORTS/'cad_checks.json').write_text(json.dumps(dict(total_mass_kg=total,failures=failures,parts=catalog),indent=2))
    if failures: raise RuntimeError('Invalid or disconnected print parts: '+str(failures))

if __name__=='__main__': build()
