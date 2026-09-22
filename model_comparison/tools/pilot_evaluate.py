"""Independent, read-only intake adapter; no invented engineering score."""
import argparse
import hashlib
import json
import importlib.util
import re
import shlex
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from pilot_run import KIT, RECORDS, RESULTS, ROOT, write_json
from pilot_sandbox import execute_command, execute_python

VERSION = "pilot-intake-20260923.1"
ENGINEERING = ("clean_rebuild", "step_kernel_readback", "solid_validity_volume_count",
               "all_printed_parts_envelope", "mesh_reference_closure", "urdf_mjcf_load",
               "joint_tree_actuator_contract", "dynamics_load", "swing_replay", "wave_replay", "robustness")
INTEGRATION_RUN = "offline_integration_eval_20260922_v2"


def intake(submission):
    source = "import sys,json; from pathlib import Path; sys.path.insert(0,'/kit/tools'); import experiment; print(json.dumps(experiment.validate(Path('/submission'),Path('/kit'))))"
    child = execute_python(source, kit=KIT, submission=submission)
    if child.returncode:
        return {"intake_status": "EVALUATOR_ERROR", "child_exit_code": child.returncode}
    result = json.loads(child.stdout)
    # experiment.validate is unchanged; never run submitted code here.
    result["child_exit_code"] = child.returncode
    return result


def _metric(metric_id, value, unit, status, failure, evidence_path, evidence_hash):
    return {"metric_id": metric_id, "definition_version": VERSION,
            "raw_value": value, "unit": unit, "status": status,
            "failure_type": failure, "evidence_path": evidence_path,
            "evidence_hash": evidence_hash,
            "evaluator_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def _stl_measure(path):
    vertices = []
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.strip().split()
        if len(fields) == 4 and fields[0].lower() == "vertex":
            vertices.append(tuple(float(x) for x in fields[1:]))
    if not vertices:
        return None
    mins = [min(p[i] for p in vertices) for i in range(3)]
    maxs = [max(p[i] for p in vertices) for i in range(3)]
    volume = 0.0
    for i in range(0, len(vertices) - 2, 3):
        a, b, c = vertices[i:i+3]
        volume += (a[0]*(b[1]*c[2]-b[2]*c[1]) - a[1]*(b[0]*c[2]-b[2]*c[0]) + a[2]*(b[0]*c[1]-b[1]*c[0])) / 6
    return {"vertex_count": len(vertices), "triangle_count": len(vertices)//3,
            "bbox_mm": {"min": mins, "max": maxs, "size": [maxs[i]-mins[i] for i in range(3)]},
            "signed_volume_mm3": volume, "absolute_volume_mm3": abs(volume)}


def _xml_measure(path, root_name):
    root = ET.parse(path).getroot()
    joints = root.findall(".//joint")
    return {"root": root.tag, "root_expected": root_name,
            "joint_count": len(joints), "joint_names": [j.get("name") for j in joints],
            "parse_pass": root.tag == root_name}


def _run_rebuild(submission):
    workspace = Path(tempfile.mkdtemp(prefix="robotgen-eval-rebuild-"))
    shutil.copytree(submission, workspace, dirs_exist_ok=True)
    manifest = json.loads((workspace / "design_manifest.json").read_text(encoding="utf-8"))
    command = manifest.get("rebuild_command")
    if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
        raise ValueError("manifest rebuild_command is missing or malformed")
    if command == ["pilot_rebuild"]:
        command = ["python3", "rebuild.py"]
    child = execute_command(" ".join(shlex.quote(item) for item in command),
                            kit=KIT, writable_output=workspace, seconds=30)
    return workspace, child


def _structure_metrics(submission):
    rows = []
    kernel_name = next((name for name in ("cadquery", "OCP") if importlib.util.find_spec(name)), None)
    step_result = None
    if kernel_name == "cadquery":
        probe = execute_python("import cadquery as cq; s=cq.importers.importStep('/submission/assembly.step'); solids=s.solids().vals(); print({'solids':len(solids),'valid':all(x.isValid() for x in solids),'volume':sum(x.Volume() for x in solids)})", kit=KIT, submission=submission, seconds=30)
        step_result = {"kernel":"cadquery", "exit_code":probe.returncode, "stdout_sha256":hashlib.sha256(probe.stdout.encode()).hexdigest(), "readback_pass":probe.returncode == 0}
    elif kernel_name == "OCP":
        step_result = {"kernel":"OCP", "readback_pass":False, "failure":"adapter not implemented"}
    rows.append(("step_kernel_readback", step_result, "bool", "PASS" if step_result and step_result.get("readback_pass") else "NA", None if step_result and step_result.get("readback_pass") else "ADAPTER_UNSUPPORTED"))
    manifest = json.loads((submission / "design_manifest.json").read_text(encoding="utf-8"))
    parts = []
    for part in manifest.get("parts", []):
        measured = _stl_measure(submission / part["stl"])
        parts.append({"id":part.get("id"), "stl":part.get("stl"), "measurement":measured})
    valid_parts = [p for p in parts if p["measurement"] and p["measurement"]["absolute_volume_mm3"] > 0]
    solid_status = "PASS" if parts and len(valid_parts) == len(parts) else "FAIL"
    rows.append(("solid_validity_volume_count", {"parts":parts,"valid_part_count":len(valid_parts)}, "mm3", solid_status, None if solid_status == "PASS" else "THRESHOLD"))
    sizes = [p["measurement"]["bbox_mm"]["size"] for p in valid_parts]
    envelope_status = "PASS" if sizes and all(all(x <= y for x, y in zip(size, (220, 220, 250))) for size in sizes) else "FAIL"
    rows.append(("all_printed_parts_envelope", {"part_count":len(parts), "sizes_mm":sizes, "limits_mm":[220,220,250]}, "mm", envelope_status, None if envelope_status == "PASS" else "THRESHOLD"))
    refs = [node.get("filename") for node in ET.parse(submission / "robot.urdf").findall(".//mesh") if node.get("filename")]
    closure = {"references": refs, "missing": [r for r in refs if not (submission / r).is_file()]}
    rows.append(("mesh_reference_closure", closure, "count", "PASS" if not closure["missing"] else "FAIL", None if not closure["missing"] else "MISSING_EVIDENCE"))
    urdf = _xml_measure(submission / "robot.urdf", "robot")
    mjcf = _xml_measure(submission / "robot.mjcf", "mujoco")
    parsed = urdf["parse_pass"] and mjcf["parse_pass"]
    rows.append(("urdf_mjcf_parse", {"urdf":urdf,"mjcf":mjcf}, "bool", "PASS" if parsed else "FAIL", None if parsed else "EVALUATOR_ERROR"))
    rows.append(("dynamics_load", None, "bool", "NA", "ADAPTER_UNSUPPORTED"))
    expected_roles = {"left_shoulder_pitch","left_elbow_pitch","right_shoulder_pitch","right_elbow_pitch","left_hip_pitch","left_knee_pitch","right_hip_pitch","right_knee_pitch"}
    declared_roles = {j.get("role") for j in manifest.get("joints", [])}
    contract = {"declared_role_count":len(declared_roles),"expected_role_count":len(expected_roles),"urdf_joint_count":urdf["joint_count"],"mjcf_joint_count":mjcf["joint_count"]}
    contract_pass = declared_roles == expected_roles and urdf["joint_count"] == 8 and mjcf["joint_count"] >= 8
    rows.append(("joint_tree_actuator_contract", contract, "count", "PASS" if contract_pass else "FAIL", None if contract_pass else "THRESHOLD"))
    for metric in ("swing_replay", "wave_replay", "robustness"):
        rows.append((metric, None, None, "NA", "ADAPTER_UNSUPPORTED"))
    return rows


def evaluate_integration(submission):
    submission = Path(submission).resolve()
    record_dir = RESULTS / INTEGRATION_RUN
    record_dir.mkdir(parents=True, exist_ok=True)
    intake_result = intake(submission)
    evidence_file = record_dir / "evaluation.json"
    evaluator_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    evidence = {"run_id": INTEGRATION_RUN, "mode": "OFFLINE_INTEGRATION", "submission": str(submission),
                "intake": intake_result, "rebuild_attempted": False, "rebuild_os_exit_code": None,
                "engineering_evaluation": "NOT_RUN", "evaluator_hash": evaluator_hash}
    metrics = []
    if intake_result.get("intake_status") == "FILE_CONTRACT_ACCEPTED":
        workspace, child = _run_rebuild(submission)
        evidence.update({"rebuild_attempted": True, "rebuild_os_exit_code": child.returncode,
                         "rebuild_stdout_sha256": hashlib.sha256(child.stdout.encode()).hexdigest(),
                         "rebuild_stderr_sha256": hashlib.sha256(child.stderr.encode()).hexdigest()})
        passed = child.returncode == 0 and (workspace / "rebuild.marker").is_file()
        metrics.append(_metric("clean_rebuild", child.returncode, "exit_code", "PASS" if passed else "FAIL", None if passed else "EVALUATOR_ERROR", "evaluation.json", "pending"))
        metrics.extend(_metric(*row, "evaluation.json", "pending") for row in _structure_metrics(submission))
        evidence["engineering_evaluation"] = "PARTIAL_STRUCTURE_ONLY"
        evidence["rebuild_workspace"] = str(workspace)
    else:
        for metric in ("clean_rebuild", *ENGINEERING):
            metrics.append(_metric(metric, None, None, "NOT_RUN", "FILE_CONTRACT", "evaluation.json", "pending"))
    evidence_file.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence_hash = hashlib.sha256(evidence_file.read_bytes()).hexdigest()
    for row in metrics:
        row["evidence_path"] = evidence_file.relative_to(ROOT).as_posix()
        row["evidence_hash"] = evidence_hash
    result = {"run_id": INTEGRATION_RUN, "mode": "OFFLINE_INTEGRATION", "metrics": metrics, "evidence": evidence}
    write_json(record_dir / "metrics.json", result)
    print(json.dumps({"run_id": INTEGRATION_RUN, "intake_status": intake_result.get("intake_status"), "rebuild_exit_code": evidence["rebuild_os_exit_code"], "engineering_evaluation": evidence["engineering_evaluation"]}))
    return 0 if evidence["engineering_evaluation"] == "PARTIAL_STRUCTURE_ONLY" else 2


def evaluate(slot, submission=None):
    evaluator_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    record = RESULTS / slot / "evaluation.json"
    gate_path = RESULTS / slot / "run_gate.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8")) if gate_path.exists() else None
    detail = intake(submission) if submission is not None else None
    evidence = {"slot": slot, "evaluator_version": VERSION, "evaluator_hash": evaluator_hash,
                "generation_status": gate["status"] if gate else "NOT_OBSERVED",
                "failure_type": gate["failure_type"] if gate else "MISSING_EVIDENCE",
                "submission_present": submission is not None, "intake": detail,
                "rebuild_attempted": False, "rebuild_os_exit_code": None,
                "engineering_evaluation": "NOT_RUN", "quality_score": None}
    write_json(record, evidence)
    evidence_hash = hashlib.sha256(record.read_bytes()).hexdigest()
    metrics = []
    for metric in ("design_produced", "file_contract", *ENGINEERING, "elapsed_s", "client_queries", "tokens", "cost", "human_design_edits"):
        status, failure, value = "NOT_STARTED", evidence["failure_type"], None
        if submission is not None:
            status, failure = "NA", "ADAPTER_UNSUPPORTED"
            if metric == "file_contract":
                value = detail["intake_status"]
                status = "PASS" if value == "FILE_CONTRACT_ACCEPTED" else "FAIL"
                failure = None if status == "PASS" else ("EVALUATOR_ERROR" if value == "EVALUATOR_ERROR" else "MISSING_EVIDENCE")
        metrics.append({"metric_id": metric, "definition": "Existing frozen task/file contract; no score or threshold change",
                        "version": VERSION, "raw_value": value, "unit": "USD" if metric == "cost" else "s" if metric == "elapsed_s" else None,
                        "status": status, "failure_type": failure,
                        "evidence_path": record.relative_to(ROOT).as_posix(), "evidence_hash": evidence_hash,
                        "evaluator_hash": evaluator_hash})
    return {"slot": slot, "metrics": metrics, "evidence": evidence}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot", choices=("model_A", "model_B", "model_C"))
    parser.add_argument("--submission", type=Path)
    parser.add_argument("--integration", action="store_true")
    args = parser.parse_args()
    if args.integration:
        if args.submission is None:
            parser.error("--integration requires --submission")
        raise SystemExit(evaluate_integration(args.submission))
    if args.slot is None:
        parser.error("--slot is required unless --integration is used")
    result = evaluate(args.slot, args.submission)
    write_json(RESULTS / args.slot / "metrics.json", result)
    print(json.dumps({"slot": args.slot, "status": result["evidence"]["generation_status"],
                      "engineering_evaluation": "NOT_RUN", "failure_type": result["evidence"]["failure_type"]}))
    return 2 if args.submission is None or result["evidence"]["intake"]["intake_status"] != "FILE_CONTRACT_ACCEPTED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
