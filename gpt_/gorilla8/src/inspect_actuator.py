#!/usr/bin/env python3
"""Extract supplied XL330 STEP mounting geometry in its native millimetre frame."""
import argparse
import json
import math
from pathlib import Path

import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane


def vec(v):
    return [round(v.X(), 6), round(v.Y(), 6), round(v.Z(), 6)]


def bbox(shape):
    b = shape.BoundingBox()
    return {
        "min": [round(b.xmin, 6), round(b.ymin, 6), round(b.zmin, 6)],
        "max": [round(b.xmax, 6), round(b.ymax, 6), round(b.zmax, 6)],
    }


def component_geometry(solid, name, index):
    cylinders = {}
    planes = []
    for face_index, face in enumerate(solid.Faces()):
        surface = BRepAdaptor_Surface(face.wrapped)
        if surface.GetType() == GeomAbs_Cylinder:
            cylinder = surface.Cylinder()
            direction = vec(cylinder.Axis().Direction())
            if next(v for v in direction if abs(v) > 1e-6) < 0:
                direction = [-v for v in direction]
            point = vec(cylinder.Location())
            distance = sum(a * b for a, b in zip(point, direction))
            origin = [round(a - distance * b, 6) for a, b in zip(point, direction)]
            radius = round(cylinder.Radius(), 6)
            key = (radius, *origin, *direction)
            bounds = bbox(face)
            axial_bounds = [
                sum(direction[k] * bounds["min" if (direction[k] >= 0) == (end == 0) else "max"][k]
                    for k in range(3))
                for end in (0, 1)
            ]
            item = cylinders.setdefault(key, {
                "radius_mm": radius, "axis_origin_mm": origin,
                "axis_direction": direction, "axial_min_mm": axial_bounds[0],
                "axial_max_mm": axial_bounds[1], "face_indices": [],
            })
            item["face_indices"].append(face_index)
            item["axial_min_mm"] = round(min(item["axial_min_mm"], axial_bounds[0]), 6)
            item["axial_max_mm"] = round(max(item["axial_max_mm"], axial_bounds[1]), 6)
        elif surface.GetType() == GeomAbs_Plane:
            plane = surface.Plane()
            normal = vec(plane.Axis().Direction())
            if abs(normal[2]) > 0.999999:
                planes.append({
                    "face_index": face_index, "z_mm": round(plane.Location().Z(), 6),
                    "area_mm2": round(face.Area(), 6), "bbox_mm": bbox(face),
                })
    return {"solid_index": index, "name": name, "valid": solid.isValid(),
            "bbox_mm": bbox(solid), "cylinders": list(cylinders.values()),
            "z_normal_planes": planes}


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step", type=Path, default=root / "xl330_m288_t/xl330_m288_t.step")
    parser.add_argument("--metadata", type=Path, default=root / "xl330_m288_t/__cadgen__/models/xl330_m288_t.step/assembly.json")
    parser.add_argument("--output", type=Path, default=root / "gorilla8/reports/actuator_geometry.json")
    args = parser.parse_args()
    shape = cq.importers.importStep(str(args.step)).val()
    solids = shape.Solids()
    metadata = json.loads(args.metadata.read_text())
    occurrences = [item for item in metadata["occurrences"] if item["name"] != "SHELL"]
    if len(solids) != 15 or len(occurrences) != len(solids):
        raise ValueError("Supplied STEP/metadata structure changed; re-identify components before using the dimensions.")
    components = [component_geometry(s, o["name"], i) for i, (s, o) in enumerate(zip(solids, occurrences))]
    horn_holes = [c for c in components[3]["cylinders"]
                  if math.isclose(c["radius_mm"], 0.8) and c["axis_origin_mm"] != [0, 0, 0]]
    if len(horn_holes) != 4 or not math.isclose(components[3]["bbox_mm"]["max"][2], 6.5, abs_tol=1e-5):
        raise ValueError("Unexpected horn geometry; do not reuse the mounting pattern.")
    report = {
        "source": str(args.step.relative_to(root)), "units": "mm",
        "method": "OpenCascade BREP cylinder axes/radii and bounded face extents; no mesh inference",
        "native_frame": "Output shaft axis +Z, origin on shaft at middle/front case seam z=0; case length along -Y.",
        "robot_frame_rotation": [[-1, 0, 0], [0, 0, 1], [0, 1, 0]],
        "bbox_mm": bbox(shape), "solid_count": len(solids),
        "interfaces": {
            "body": {
                "case_bbox_mm": {"min": [-10, -24.5, -19.5], "max": [10, 9.5, 3.5]},
                "mount_hole_xy_mm": [[-8, 7.5], [8, 7.5], [-8, -22.5], [8, -22.5]],
                "front_face_z_mm": 3.5, "rear_face_z_mm": -19.5,
                "cover_clearance_diameter_mm": 2.0, "middle_pilot_diameter_mm": 1.6,
                "front_clearance_depth_mm": 3.5, "rear_clearance_depth_mm": 4.5,
                "middle_pilot_z_range_mm": [-15, 0],
                "case_assembly_screws_do_not_remove_xy_mm": [[-8.4, 4.5], [8.4, 4.5], [-8.4, -19.4], [4.9, -22.9]],
            },
            "output_horn": {
                "mount_face_z_mm": 6.5, "diameter_mm": 16,
                "mount_hole_xy_mm": [c["axis_origin_mm"][:2] for c in horn_holes],
                "hole_diameter_mm": 1.6, "pitch_circle_diameter_mm": 12,
                "modeled_hole_depth_mm": 2.9, "drawing_max_screw_penetration_mm": 3.0,
                "central_counterbore_diameter_mm": 5.6,
                "central_counterbore_z_range_mm": [4.9, 6.3],
                "central_face_chamfer_opening_diameter_mm": 6.0,
                "center_screw": "OEM BTS2_M2_6X8; preserve installed screw; not an M2 bracket attachment",
            },
            "idler_horn": {
                "mount_face_z_mm": -22.5, "diameter_mm": 16,
                "mount_hole_xy_mm": [[0, -6], [-6, 0], [0, 6], [6, 0]],
                "hole_diameter_mm": 1.6, "pitch_circle_diameter_mm": 12,
                "modeled_hole_depth_mm": 2.9, "drawing_max_screw_penetration_mm": 3.0,
                "inner_cap_clearance_bore_diameter_mm": 7.2,
                "inner_cap_clearance_bore_z_range_mm": [-22.3, -20.0],
                "central_face_chamfer_opening_diameter_mm": 7.6,
                "shaft_hole_diameter_mm": 5.0,
                "shaft_hole_z_range_mm": [-19.8, -18.35],
                "case_register_outer_diameter_mm": 6.5,
                "case_register_z_range_mm": [-19.3, -18.35],
            },
            "idler_cap": {
                "flange_outer_diameter_mm": 6.8,
                "flange_z_range_mm": [-22.3, -20.1],
                "stem_outer_diameter_mm": 4.8,
                "stem_z_range_mm": [-19.9, -17.7],
                "screw_clearance_diameter_mm": 2.8,
                "screw_clearance_z_range_mm": [-20.5, -17.7],
                "screw_counterbore_diameter_mm": 5.6,
                "screw_counterbore_z_range_mm": [-22.3, -20.7],
                "radial_clearance_to_idler_mm": 0.2,
                "note": "Retains OEM rotating idler horn. Keep cap and its OEM screw unchanged; attach printed fork to idler horn face.",
                "source_discrepancy": "STEP metadata calls the central screw BTS2_M2_6X8, while the official saved assembly illustration labels idler M2.6x6. Preserve the actual OEM kit screw; do not purchase replacements from the STEP component name.",
            },
            "suggested_printed_interface": {
                "front_fork_z_range_mm": [6.5, 9.5],
                "rear_fork_z_range_mm": [-25.5, -22.5],
                "fork_nominal_wall_mm": 3.0,
                "mount_hole_clearance_mm": 2.2,
                "front_center_access_mm": 6.4,
                "rear_center_access_mm": 8.0,
                "horn_screws": "ST2 x 5 plastic tapping, 3.0 mm printed wall, nominal penetration 2.0 mm; verify actual head-to-tip length.",
                "horn_screw_alternative": "Official illustration uses ST2 x 6 with 3.0 mm frame. A 3.2 mm frame with ST2 x 6 gives nominal 2.8 mm penetration, below the 3.0 mm maximum.",
                "body_screws": "ST2 x 10 plastic tapping, 3.0 mm printed wall; nominal front pilot engagement 3.5 mm or rear engagement 2.5 mm.",
                "warning": "Do not substitute ordinary M2 machine screws in OEM 1.6 mm untapped plastic holes. Printed fork wall lies outside both OEM horns; do not insert it between idler cap and horn.",
            },
        },
        "limitations": [
            "Nominal STEP dimensions are not measurements of the user's physical servo or printer.",
            "Threads, material strength, screw torque and dynamic load rating are not established by STEP geometry.",
            "Geometry-only recommended wall/clearance values require the assembly's separate interference and load verification.",
        ],
        "components": components,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"report": str(args.output), "solids": len(solids), "horn_mount_holes": len(horn_holes),
                      "all_solids_valid": all(s.isValid() for s in solids)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
