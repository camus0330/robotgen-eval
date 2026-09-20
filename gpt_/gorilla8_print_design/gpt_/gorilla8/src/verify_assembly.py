"""Inspect delivered meshes and exact CAD; render the actual articulated assembly."""
import argparse
import json
import csv
from pathlib import Path
import os
import xml.etree.ElementTree as ET
import numpy as np
import trimesh
import fcl
from design import OUT, REPORTS, INPUT_STEP, LIMBS, JOINT_NAMES, COLORS, transforms


def matrix(rotation, translation):
    t = np.eye(4)
    t[:3, :3], t[:3, 3] = rotation, translation
    return t


def is_stock_bearing_pair(a, b):
    return a.rsplit('_', 1)[0] == b.rsplit('_', 1)[0] and {a.rsplit('_', 1)[1], b.rsplit('_', 1)[1]} == {'case', 'rotors'}


def load_objects():
    records = json.loads((OUT / 'assembly/objects.json').read_text())
    for o in records:
        o['mesh_obj'] = trimesh.load(OUT / o['mesh'], force='mesh')
        mesh = o['mesh_obj']
        geometry = fcl.BVHModel()
        geometry.beginModel(len(mesh.vertices), len(mesh.faces))
        geometry.addSubModel(mesh.vertices, mesh.faces)
        geometry.endModel()
        o['fcl_obj'] = fcl.CollisionObject(geometry)
    return records


def locate_shape(shape, rotation, translation):
    import cadquery as cq
    from OCP.gp import gp_Trsf
    tr = gp_Trsf()
    tr.SetValues(*[float(x) for row in np.column_stack((rotation, translation)) for x in row])
    return shape.moved(cq.Location(tr))


def load_exact(records):
    import cadquery as cq
    parts = {}
    source = cq.importers.importStep(str(INPUT_STEP)).val().Solids()
    stator = cq.Compound.makeCompound([s for i, s in enumerate(source) if i not in [3, 10]])
    rotors = cq.Compound.makeCompound([source[3], source[10]])
    for o in records:
        name, part = o['name'], o['part']
        if part:
            if part not in parts:
                parts[part] = cq.importers.importStep(str(OUT / 'parts/step' / f'{part}.step')).val()
            shape = parts[part]
            if name.startswith('eye_'):
                shape = shape.translate((0, -10 if name == 'eye_0' else 10, 0))
            if 'pad' in name:
                limb = next(l for l in LIMBS if name.startswith(l['name']))
                shape = shape.translate((0, 0, -limb['lengths_mm'][1]))
        else:
            limb = next(l for l in LIMBS if name.startswith(l['name']))
            side = limb['side']
            rotation = np.array([[-side, 0, 0], [0, 0, side], [0, 1, 0]])
            translation = np.array([0, 8 * side, 0.])
            original = stator if name.endswith('case') else rotors
            if name.endswith('case'):
                translation += np.array(limb['origin_mm']) if '_motor_0_' in name else [0, 0, -limb['lengths_mm'][0]]
            shape = locate_shape(original, rotation, translation)
        o['shape'] = shape


def frames(motion_names):
    result = [('neutral', 0, {'time_s': 0.0, 'stage': 'neutral', 'contact_mask': [1, 1, 1, 1]})]
    for name in motion_names:
        path = OUT / 'motions' / name / 'poses.json'
        result.extend((name, i, p) for i, p in enumerate(json.loads(path.read_text())))
    return result


def simulation_frames(path):
    """Read simulate.py's actual qpos fields: root metres, quaternion wxyz, q radians."""
    contract = json.loads((OUT / 'simulation/contract.json').read_text())
    if contract['joint_order'] != JOINT_NAMES or contract['units'] != 'SI, radian':
        raise ValueError('Simulation contract does not match the CAD joint order and SI/radian convention')
    records = json.loads(path.read_text())
    if not records:
        raise ValueError('Simulation trace is empty')
    result = []
    previous_time = -float('inf')
    for i, record in enumerate(records):
        q = np.asarray(record['q'], dtype=float)
        root = np.asarray(record['root'], dtype=float)
        quat = np.asarray(record['root_quat_wxyz'], dtype=float)
        time = float(record['t'])
        if q.shape != (8,) or root.shape != (3,) or quat.shape != (4,):
            raise ValueError(f'Invalid actual qpos dimensions at simulation frame {i}')
        if not np.isfinite(np.r_[q,root,quat,time]).all() or abs(np.linalg.norm(quat)-1) > 1e-6:
            raise ValueError(f'Invalid actual qpos or non-unit quaternion at simulation frame {i}')
        if time <= previous_time:
            raise ValueError(f'Non-increasing simulation timestamp at frame {i}')
        previous_time = time
        pose = {'time_s':time, 'stage':'actual_simulation', 'joint_rad':q.tolist(),
                'root_mm':(root*1000).tolist(), 'root_quat_wxyz':quat.tolist(), 'contact_mask':None}
        result.append((path.parent.name, i, pose))
    return result


def pose_transforms(pose):
    if 'root_quat_wxyz' not in pose:
        return transforms(pose.get('joint_rad'), pose.get('root_mm'))
    from scipy.spatial.transform import Rotation
    w,x,y,z = pose['root_quat_wxyz']
    base_r = Rotation.from_quat([x,y,z,w]).as_matrix()
    local = transforms(pose['joint_rad'], np.zeros(3))
    root = np.asarray(pose['root_mm'])
    return {name:(base_r@r, base_r@t+root) for name,(r,t) in local.items()}


def scan(records, all_frames):
    candidates = {}
    grounds = {}
    ignored_stock = set()
    for frame_number, (run, index, pose) in enumerate(all_frames):
        ts = pose_transforms(pose)
        transformed_bounds = {}
        for o in records:
            r, t = ts[o['link']]
            o['fcl_obj'].setTransform(fcl.Transform(r, t))
            vertices = o['mesh_obj'].vertices @ r.T + t
            transformed_bounds[o['name']] = (vertices.min(0), vertices.max(0))
            g = grounds.setdefault(run, {'min_mesh_z_mm': float('inf'), 'minimum_at': None,
                                       'min_nonpad_mesh_z_mm':float('inf'), 'nonpad_minimum_at':None,
                                       'contacts': {}, 'frame_count': 0})
            minimum = float(vertices[:, 2].min())
            if minimum < g['min_mesh_z_mm']:
                g['min_mesh_z_mm'] = minimum
                g['minimum_at'] = {'frame': index, 'part': o['name'], 'stage': pose['stage']}
            if o['material'] != 'TPU' and minimum < g['min_nonpad_mesh_z_mm']:
                g['min_nonpad_mesh_z_mm'] = minimum
                g['nonpad_minimum_at'] = {'frame': index, 'part': o['name'], 'stage':pose['stage']}
            if o['material'] == 'TPU':
                limb_index = next(i for i, l in enumerate(LIMBS) if o['name'].startswith(l['name']))
                contact = pose['contact_mask'] is not None and bool(pose['contact_mask'][limb_index])
                pad = g['contacts'].setdefault(o['name'], {'min_z_mm': float('inf'), 'max_z_during_declared_contact_mm': None, 'worst_contact_frame': None})
                pad['min_z_mm'] = min(pad['min_z_mm'], minimum)
                if contact and (pad['max_z_during_declared_contact_mm'] is None or minimum > pad['max_z_during_declared_contact_mm']):
                    pad['max_z_during_declared_contact_mm'] = minimum
                    pad['worst_contact_frame'] = index
        grounds[run]['frame_count'] += 1
        # Explicit AABB broad phase keeps contact-return limits deterministic.
        for ia, a in enumerate(records):
            for b in records[ia + 1:]:
                same_link = a['link'] == b['link']
                if same_link and (frame_number != 0 or not (a['part'] or b['part'])):
                    continue
                pair = tuple(sorted([a['name'], b['name']]))
                if is_stock_bearing_pair(*pair):
                    ignored_stock.add(pair)
                    continue
                amin, amax = transformed_bounds[a['name']]
                bmin, bmax = transformed_bounds[b['name']]
                if np.any(amax < bmin - 1e-5) or np.any(bmax < amin - 1e-5):
                    continue
                request = fcl.CollisionRequest(num_max_contacts=1, enable_contact=False)
                if not fcl.collide(a['fcl_obj'], b['fcl_obj'], request, fcl.CollisionResult()):
                    continue
                group = candidates.setdefault(pair, [])
                # Same-link candidates are rigidly invariant. Cross-link transforms are retained for exact follow-up.
                group.append((run, index, pose))
        if index % 100 == 0:
            print(json.dumps({'scan': run, 'frame': index, 'candidate_pairs': len(candidates)}), flush=True)
    return candidates, grounds, ignored_stock


def exact_checks(records, candidates, exhaustive):
    load_exact(records)
    by = {o['name']: o for o in records}
    checked = []
    for pair, occurrences in candidates.items():
        a, b = (by[name] for name in pair)
        choices = occurrences if exhaustive else [occurrences[i] for i in sorted({0, len(occurrences)//2, len(occurrences)-1})]
        cache = {}
        results = []
        for run, index, pose in choices:
            ts = pose_transforms(pose)
            ra, ta = ts[a['link']]
            rb, tb = ts[b['link']]
            # Evaluate in A-local frame; translation of the robot cannot change overlap.
            relative_r, relative_t = ra.T @ rb, ra.T @ (tb - ta)
            key = tuple(np.round(np.r_[relative_r.ravel(), relative_t], 9))
            if key not in cache:
                relative_b = locate_shape(b['shape'], relative_r, relative_t)
                common = a['shape'].intersect(relative_b)
                cache[key] = max(0.0, common.Volume())
            volume = cache[key]
            results.append({'run': run, 'frame': index, 'stage': pose['stage'], 'intersection_mm3': volume})
        worst = max(results, key=lambda item: item['intersection_mm3'])
        item = {'pair': pair, 'same_link': a['link'] == b['link'], 'mesh_candidate_frames': len(occurrences),
                'exact_evaluations': len(cache), 'all_candidate_frames_checked': exhaustive or len(choices) == len(occurrences),
                'max_intersection_mm3': worst['intersection_mm3'], 'worst': worst,
                'positive_interference': worst['intersection_mm3'] > 1e-3,
                'exact_samples': results}
        checked.append(item)
        print(json.dumps({k:v for k,v in item.items() if k != 'exact_samples'}), flush=True)
    return checked


def render(records, all_frames):
    os.environ.setdefault('MUJOCO_GL', 'egl')
    import mujoco
    from scipy.spatial.transform import Rotation
    from PIL import Image
    directory = OUT / 'renders'
    directory.mkdir(parents=True, exist_ok=True)
    root = ET.Element('mujoco', model='gorilla8 actual manufacturing geometry')
    ET.SubElement(root, 'compiler', angle='radian', meshdir=str(OUT))
    visual = ET.SubElement(root, 'visual')
    ET.SubElement(visual, 'global', offwidth='1600', offheight='1400')
    ET.SubElement(visual, 'quality', shadowsize='4096', offsamples='4')
    ET.SubElement(visual, 'headlight', ambient='0.35 0.35 0.35', diffuse='0.65 0.65 0.65', specular='0.15 0.15 0.15')
    assets, world = ET.SubElement(root, 'asset'), ET.SubElement(root, 'worldbody')
    ET.SubElement(assets, 'texture', type='skybox', builtin='gradient', rgb1='.9 .93 .96', rgb2='.7 .76 .82', width='512', height='512')
    ET.SubElement(assets, 'texture', name='grid', type='2d', builtin='checker', rgb1='.87 .89 .91', rgb2='.79 .82 .85', width='128', height='128')
    ET.SubElement(assets, 'material', name='floor', texture='grid', texrepeat='10 10', reflectance='0')
    ET.SubElement(world, 'geom', type='plane', size='.5 .5 .01', material='floor', contype='0', conaffinity='0')
    ET.SubElement(world, 'light', pos='.25 -.3 .5', dir='-.25 .3 -.5', diffuse='.8 .8 .8', castshadow='true')
    for i, o in enumerate(records):
        ET.SubElement(assets, 'mesh', name=f'm{i}', file=o['mesh'], scale='.001 .001 .001')
        body = ET.SubElement(world, 'body', name=o['name'], mocap='true')
        color = COLORS[o['material']]
        ET.SubElement(body, 'geom', type='mesh', mesh=f'm{i}', rgba=' '.join(map(str, color)), contype='0', conaffinity='0')
    xml = ET.tostring(root, encoding='unicode')
    (directory / 'render_scene.xml').write_text(xml)
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    renderer = mujoco.Renderer(model, height=1400, width=1600)
    choices = [('neutral', all_frames[0][2])]
    wave = [f for f in all_frames if f[0] == 'flat_palm_wave']
    swing = [f for f in all_frames if f[0] == 'flat_palm_swing']
    if wave:
        choices.append(('wave', min(wave, key=lambda x: x[2]['joint_rad'][0])[2]))
    if swing:
        choices.append(('palm_swing', max(swing, key=lambda x: min(x[2]['end_center_mm'][2][2], x[2]['end_center_mm'][3][2]))[2]))
    for name, pose in choices:
        ts = pose_transforms(pose)
        for i, o in enumerate(records):
            r, t = ts[o['link']]
            quat = Rotation.from_matrix(r).as_quat()
            data.mocap_pos[i] = t / 1000
            data.mocap_quat[i] = np.r_[quat[3], quat[:3]]
        mujoco.mj_forward(model, data)
        for view, azimuth, elevation in [('three_quarter', 218, -15), ('front', 180, -5), ('side', 270, -5)]:
            if name != 'neutral' and view != 'three_quarter' and not (name == 'palm_swing' and view == 'side'):
                continue
            camera = mujoco.MjvCamera()
            camera.type = mujoco.mjtCamera.mjCAMERA_FREE
            camera.lookat = [pose.get('root_mm', [0, 0, 137])[0] / 1000, 0, .100]
            camera.distance = .50 if name == 'wave' else .40
            if name == 'wave':
                camera.lookat += [.025, .012, .020]
            camera.azimuth, camera.elevation = (142 if name == 'wave' else azimuth), elevation
            renderer.update_scene(data, camera)
            pixels = renderer.render()
            path = directory / f'{name}_{view}.png'
            Image.fromarray(pixels).save(path)
            print(json.dumps({'render': str(path)}), flush=True)
    renderer.close()



def render_layouts(records):
    """Show exploded link groups and one representative of each printable type."""
    os.environ.setdefault('MUJOCO_GL', 'egl')
    import mujoco
    from scipy.spatial.transform import Rotation
    from PIL import Image
    directory = OUT / 'renders'
    directory.mkdir(parents=True, exist_ok=True)

    def picture(name, items, azimuth, elevation, distance_factor):
        root = ET.Element('mujoco', model=name)
        ET.SubElement(root, 'compiler', angle='radian', meshdir=str(OUT))
        visual = ET.SubElement(root, 'visual')
        ET.SubElement(visual, 'global', offwidth='1800', offheight='1500')
        ET.SubElement(visual, 'quality', shadowsize='4096', offsamples='4')
        ET.SubElement(visual, 'headlight', ambient='.4 .4 .4' if name=='exploded' else '.28 .28 .28', diffuse='.6 .6 .6' if name=='exploded' else '.48 .48 .48')
        assets, world = ET.SubElement(root, 'asset'), ET.SubElement(root, 'worldbody')
        ET.SubElement(assets, 'texture', type='skybox', builtin='gradient', rgb1='.95 .97 .99', rgb2='.78 .83 .89', width='512', height='512')
        ET.SubElement(world, 'geom', type='plane', size='1 1 .01', rgba='.83 .87 .91 1', contype='0', conaffinity='0')
        ET.SubElement(world, 'light', pos='.3 -.4 .8', dir='-.3 .4 -.8', diffuse='.8 .8 .8' if name=='exploded' else '.5 .5 .5', castshadow='true')
        bounds = []
        for i, item in enumerate(items):
            r, t = item['rotation'], item['translation_mm']
            mesh = item['mesh_obj']
            vertices = mesh.vertices @ r.T + t
            bounds.extend([vertices.min(0), vertices.max(0)])
            ET.SubElement(assets, 'mesh', name=f'm{i}', file=item['mesh'], scale='.001 .001 .001')
            quat = Rotation.from_matrix(r).as_quat()
            body = ET.SubElement(world, 'body', name=item['name'], pos=' '.join(map(str, np.asarray(t)/1000)), quat=' '.join(map(str, np.r_[quat[3],quat[:3]])))
            ET.SubElement(body, 'geom', type='mesh', mesh=f'm{i}', rgba=' '.join(map(str,COLORS[item['material']])), contype='0', conaffinity='0')
        low, high = np.min(bounds, axis=0)/1000, np.max(bounds, axis=0)/1000
        xml = ET.tostring(root, encoding='unicode')
        (directory/f'{name}_scene.xml').write_text(xml)
        model = mujoco.MjModel.from_xml_string(xml)
        data = mujoco.MjData(model)
        mujoco.mj_forward(model,data)
        renderer = mujoco.Renderer(model,height=1500,width=1800)
        camera = mujoco.MjvCamera()
        camera.type = mujoco.mjtCamera.mjCAMERA_FREE
        camera.lookat = (low+high)/2
        camera.distance = float(max(high-low)*distance_factor)
        camera.azimuth, camera.elevation = azimuth,elevation
        renderer.update_scene(data,camera)
        Image.fromarray(renderer.render()).save(directory/f'{name}.png')
        renderer.close()
        print(json.dumps({'render':str(directory/f'{name}.png')}),flush=True)

    ts = transforms()
    exploded = []
    annotations = []
    for o in records:
        r,t = ts[o['link']]
        offset = np.array([0.,0.,65.])
        if o['link'] != 'base':
            limb = next(l for l in LIMBS if o['link'].startswith(l['name']))
            arm,lower = 'arm' in limb['name'],o['link'].endswith('lower')
            offset += [45 if arm and lower else 15 if arm else -50 if lower else -20,
                       limb['side']*(75 if lower else 45),-35 if lower else 0]
        elif o['name'] in ['P09_head_shell','eye_0','eye_1']:
            offset += [0,0,70]
        elif o['name'] == 'P08_chest_shell':
            offset += [60,0,15]
        exploded.append(dict(o,rotation=r,translation_mm=t+offset))
        annotations.append({'name':o['name'],'link':o['link'],'separation_offset_mm':offset.tolist(),'mesh':o['mesh']})
    picture('exploded',exploded,218,-18,2.25)
    (directory/'exploded_layout.json').write_text(json.dumps({'note':'Rigid link groups are translated for illustration; this is not an assemblable or motion pose. Head/eyes and chest are additionally separated.','objects':annotations},indent=2)+'\n')

    with (OUT/'parts/parts.csv').open() as handle:
        catalog = list(csv.DictReader(handle))
    if len(catalog) != 12:
        raise ValueError(f'Expected 12 printable types, got {len(catalog)}')
    laid_out,annotations = [],[]
    for i,part in enumerate(catalog):
        mesh_path = 'parts/stl/'+part['part']+'.stl'
        mesh = trimesh.load(OUT/mesh_path,force='mesh')
        row,column = divmod(i,4)
        center = (mesh.bounds[0]+mesh.bounds[1])/2
        t = np.array([(3-column)*100-center[0],[0,130,240][row]-center[1],-mesh.bounds[0,2]])
        material = 'TPU' if part['material']=='TPU' else 'eyes' if 'eye' in part['part'] else 'PETG'
        laid_out.append({'name':part['part'],'mesh':mesh_path,'mesh_obj':mesh,'rotation':np.eye(3),'translation_mm':t,'material':material})
        annotations.append({'part':part['part'],'quantity_required':int(part['quantity']),'displayed_quantity':1,'row':row+1,'column':column+1,'translation_mm':t.tolist(),'source_print_stl':mesh_path})
    picture('print_parts_layout',laid_out,270,-64,1.85)
    (directory/'print_parts_layout.json').write_text(json.dumps({'note':'One of each of the 12 print types; quantities are in the catalog. Layout is a review illustration, not a slicer bed or one-job print arrangement.','parts':annotations},indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render-only', action='store_true')
    parser.add_argument('--layouts-only', action='store_true', help='Render exploded assembly and the 12 actual print-STL types')
    parser.add_argument('--report', type=Path, help='Separate JSON report path; default reports/collision_checks.json')
    parser.add_argument('--skip-render', action='store_true')
    parser.add_argument('--exhaustive-exact', action='store_true', help='BREP-check every unique relative transform of every FCL candidate')
    parser.add_argument('--neutral-only', action='store_true')
    parser.add_argument('--motion', action='append', help='Motion directory name; defaults to the two requested delivered motions')
    parser.add_argument('--simulation-trace', type=Path, help='Absolute path to simulate.py actual trace; requires a separate --report and does not render')
    args = parser.parse_args()
    if args.simulation_trace:
        if not args.simulation_trace.is_absolute() or not args.report:
            parser.error('--simulation-trace requires an absolute trace path and explicit --report')
        if args.motion or args.neutral_only or args.render_only or args.layouts_only:
            parser.error('--simulation-trace cannot be combined with reference-motion or render-only selection')
    records = load_objects()
    if args.layouts_only:
        render_layouts(records)
        return 0
    motion_names = [] if args.simulation_trace else args.motion or ['flat_palm_swing', 'flat_palm_wave']
    all_frames = simulation_frames(args.simulation_trace) if args.simulation_trace else frames([] if args.neutral_only else motion_names)
    if args.neutral_only:
        all_frames = all_frames[:1]
    result = None
    if not args.render_only:
        candidates, ground, stock = scan(records, all_frames)
        checked = exact_checks(records, candidates, args.exhaustive_exact)
        ground_tolerance = 0.5 if args.simulation_trace else 0.05
        ground_passed = all(g['min_mesh_z_mm'] >= -ground_tolerance and
                            all(p['max_z_during_declared_contact_mm'] is None or p['max_z_during_declared_contact_mm'] <= 0.15
                                for p in g['contacts'].values()) for g in ground.values())
        self_collision_passed = not any(c['positive_interference'] for c in checked)
        result = {
            'method': 'Every recorded frame uses triangle-mesh FCL candidates, followed by OpenCascade BREP intersection volume. Ground uses transformed vertices of delivered mesh geometry.',
            'length_unit': 'mm', 'volume_tolerance_mm3': 1e-3,
            'ground_penetration_tolerance_mm': ground_tolerance,
            'declared_contact_gap_tolerance_mm': None if args.simulation_trace else 0.15,
            'input_kind':'actual_simulation_qpos' if args.simulation_trace else 'reference_poses',
            'simulation_trace':str(args.simulation_trace) if args.simulation_trace else None,
            'trace_contract':{'joint_order':JOINT_NAMES, 'root_input_unit':'m', 'joint_input_unit':'rad',
                              'root_quaternion_order':'wxyz', 'world_frame':'+X forward, +Y left, +Z up',
                              'fields_used':['t','root','root_quat_wxyz','q'],
                              'sample_intervals_s':sorted(set(round(all_frames[i][2]['time_s']-all_frames[i-1][2]['time_s'],9) for i in range(1,len(all_frames))))}
                             if args.simulation_trace else None,
            'geometry_contract': LIMBS, 'mesh_object_count': len(records),
            'cad_contains_added_fasteners': False,
            'frame_count': len(all_frames), 'exhaustive_exact': args.exhaustive_exact,
            'motion_directories': [] if args.neutral_only else motion_names,
            'excluded_pairs': [{'pair': p, 'reason': 'OEM stator/rotor bearing engagement retained unchanged from supplied actuator assembly'} for p in sorted(stock)],
            'pair_checks': checked, 'ground': ground,
            'positive_interference_pairs': [c['pair'] for c in checked if c['positive_interference']],
            'self_collision_passed':args.exhaustive_exact and self_collision_passed,
            'ground_within_tolerance':ground_passed,
            'passed':args.exhaustive_exact and self_collision_passed and ground_passed,
            'limitations': ['No continuous collision detection between recorded frames.', 'Added screws, nuts and cables are represented by assembly instructions/mass allowance, not solid geometry in this scan.', 'A sampled BREP follow-up is diagnostic only unless exhaustive_exact is true.'],
        }
        REPORTS.mkdir(parents=True, exist_ok=True)
        report_path = args.report or REPORTS / 'collision_checks.json'
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    if not args.skip_render and not args.simulation_trace:
        render(records, all_frames)
    if result is not None and (result['positive_interference_pairs'] or not result['ground_within_tolerance']):
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
