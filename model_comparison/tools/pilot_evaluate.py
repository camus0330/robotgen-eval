"""Independent, read-only intake adapter; no invented engineering score."""
import argparse
import hashlib
import json
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from pilot_run import KIT, RECORDS, RESULTS, ROOT, write_json
from pilot_sandbox import execute_python
from pilot_snapshot import safe_snapshot, relative_name, SnapshotRejected
from pilot_cad import VERSION, source_rebuild, step_readback, stl_measure, RebuildContractError

ENGINEERING = ("clean_rebuild", "step_kernel_readback", "solid_validity_volume_count",
               "all_printed_parts_envelope", "mesh_reference_closure", "urdf_mjcf_parse", "joint_counts",
               "joint_tree_actuator_contract", "dynamics_load", "swing_replay", "wave_replay", "robustness")
INTEGRATION_RUN = "offline_integration_eval_20260922_v3"


def intake(submission, *, kit=None, results_root=None):
    kit = Path(kit) if kit is not None else KIT
    results_root = Path(results_root) if results_root is not None else RESULTS
    source = "import sys,json; from pathlib import Path; sys.path.insert(0,'/kit/tools'); import experiment; print(json.dumps(experiment.validate(Path('/submission'),Path('/kit'))))"
    parent = Path(tempfile.mkdtemp(prefix="intake-v2-", dir=results_root))
    safe_snapshot(submission, parent / "received")
    child = execute_python(source, kit=kit, submission=parent / "received")
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


_stl_measure = stl_measure


def _xml_measure(path, root_name):
    root = ET.parse(path).getroot()
    joints = root.findall(".//joint")
    return {"root": root.tag, "root_expected": root_name,
            "joint_count": len(joints), "joint_names": [j.get("name") for j in joints],
            "parse_pass": root.tag == root_name}


def _structure_metrics(submission, *, kit=None):
    kit = Path(kit) if kit is not None else KIT
    # Caller supplies the immutable safe snapshot of NEW rebuilt outputs.
    safe_snapshot(submission)
    manifest = json.loads((submission / "design_manifest.json").read_text(encoding="utf-8"))
    paths = sorted({relative_name(manifest["files"]["assembly_step"])} |
                   {relative_name(p["step"]) for p in manifest["parts"]})
    step = step_readback(submission, paths, kit=kit)
    available = step.get("environment") == "PASS" and step["os_exit_code"] == 0
    step_pass = available and bool(step.get("parts")) and all(p["status"] == "PASS" for p in step["parts"])
    rows = [("step_kernel_readback", step, "mm3", "PASS" if step_pass else "FAIL" if available else "NA",
             None if step_pass else "STEP_READBACK_FAILED" if available else "CAD_ENVIRONMENT_UNAVAILABLE")]
    parts = [{"id": p.get("id"), "stl": relative_name(p["stl"]),
              "measurement": stl_measure(submission / relative_name(p["stl"]))} for p in manifest["parts"]]
    complete = bool(parts) and all(p["measurement"] is not None for p in parts)
    sizes = [p["measurement"]["bbox_mm"]["size"] if p["measurement"] else None for p in parts]
    envelope = complete and all(all(0 < x <= y for x,y in zip(size,(220,220,250))) for size in sizes)
    rows.append(("stl_triangle_proxy", {"parts":parts}, "mm3", "PASS" if complete else "FAIL", None if complete else "MISSING_OR_INVALID_STL"))
    rows.append(("solid_validity_volume_count", None, None, "NA", "MESH_SOLID_VALIDITY_NOT_IMPLEMENTED"))
    rows.append(("all_printed_parts_envelope", {"part_count":len(parts), "sizes_mm":sizes,"limits_mm":[220,220,250]}, "mm", "PASS" if envelope else "FAIL", None if envelope else "MISSING_INVALID_OR_OVERSIZE_PART"))
    xml = {}
    for key, root in (("urdf","robot"),("mjcf","mujoco")):
        try:
            name = relative_name(manifest["files"][key])
            xml[key] = _xml_measure(submission / name, root)
        except (KeyError, ValueError, OSError, ET.ParseError):
            xml[key] = {"parse_pass":False, "joint_count":None}
    parsed = all(x["parse_pass"] for x in xml.values())
    rows.append(("urdf_mjcf_parse", xml, "bool", "PASS" if parsed else "NA", None if parsed else "XML_MISSING_OR_INVALID"))
    rows.append(("joint_counts", {k:v["joint_count"] for k,v in xml.items()}, "count", "OBSERVED" if parsed else "NA", None if parsed else "XML_MISSING_OR_INVALID"))
    try:
        refs = [relative_name(n.get("filename")) for n in ET.parse(submission / relative_name(manifest["files"]["urdf"])).findall(".//mesh") if n.get("filename")]
        missing = [r for r in refs if not (submission / r).is_file()]
        rows.append(("mesh_reference_closure", {"references":refs,"missing":missing}, "count", "FAIL" if missing else "PASS", "MISSING_MESH" if missing else None))
    except (KeyError, ValueError, OSError, ET.ParseError):
        rows.append(("mesh_reference_closure", None, None, "NA", "XML_MISSING_OR_INVALID"))
    for metric in ("joint_tree_actuator_contract", "dynamics_load", "swing_replay", "wave_replay", "robustness"):
        rows.append((metric, None, None, "NA", "NOT_IMPLEMENTED"))
    return rows


def evaluate_integration(submission, run_id=INTEGRATION_RUN, mode="OFFLINE_INTEGRATION", *,
                         kit=None, results_root=None, record_id=None, batch_id=None, execution_context=None):
    kit = Path(kit) if kit is not None else KIT
    results_root = Path(results_root) if results_root is not None else RESULTS
    relative_name(run_id)
    record_dir = results_root / relative_name(record_id or run_id)
    record_dir.mkdir(parents=True, exist_ok=False)
    evidence_file = record_dir / "evaluation.json"
    evidence = {"run_id":run_id,"mode":mode,"rule_version":VERSION,"submission":str(submission),
                "batch_id":batch_id,"input_kit":str(kit),
                "execution_context":execution_context,
                "rebuild_attempted":False,"rebuild_os_exit_code":None,"engineering_evaluation":"NOT_RUN",
                "evaluator_hash":hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    metrics = []
    try:
        evidence["received_snapshot"] = safe_snapshot(submission, record_dir / "received")
        evidence["intake"] = intake(record_dir / "received", kit=kit, results_root=results_root)
        if evidence["intake"].get("intake_status") != "FILE_CONTRACT_ACCEPTED":
            raise RebuildContractError("FILE_CONTRACT")
        rebuilt, rebuild = source_rebuild(record_dir / "received", record_dir, kit=kit)
        evidence.update(rebuild=rebuild, rebuild_attempted=True, rebuild_os_exit_code=rebuild["os_exit_code"],
                        measured_directory=str(rebuilt))
        rows = _structure_metrics(rebuilt, kit=kit)
        cad_ok = all(next(r for r in rows if r[0] == key)[3] == "PASS"
                     for key in ("step_kernel_readback", "stl_triangle_proxy"))
        passed = rebuild["outputs_created"] and cad_ok
        metrics.append(_metric("clean_rebuild", rebuild, None, "PASS" if passed else "FAIL",
                               None if passed else "MISSING_INVALID_OR_NOT_REBUILT", "evaluation.json", "pending"))
        metrics.extend(_metric(*row, "evaluation.json", "pending") for row in rows)
        evidence["engineering_evaluation"] = "PARTIAL_CAD_MEASURED" if passed else "REBUILD_FAILED"
    except (RebuildContractError, SnapshotRejected) as error:
        evidence["failure_type"] = "UNSAFE_SNAPSHOT" if isinstance(error, SnapshotRejected) else "SOURCE_OUTPUT_CONTRACT_UNCLEAR_OR_FILE_CONTRACT"
        evidence["safe_exception_class"] = type(error).__name__
        metrics = [_metric(m, None, None, "NOT_RUN", evidence["failure_type"], "evaluation.json", "pending") for m in dict.fromkeys(ENGINEERING)]
    except (OSError, subprocess.TimeoutExpired) as error:
        evidence.update(failure_type="SNAPSHOT_IO_OR_SANDBOX_FAILURE", safe_exception_class=type(error).__name__)
        metrics = [_metric(m, None, None, "NOT_RUN", evidence["failure_type"], "evaluation.json", "pending") for m in dict.fromkeys(ENGINEERING)]
    write_json(evidence_file, evidence)
    for row in metrics:
        row["evidence_path"] = evidence_file.relative_to(ROOT).as_posix()
        row["evidence_hash"] = hashlib.sha256(evidence_file.read_bytes()).hexdigest()
    write_json(record_dir / "metrics.json", {"run_id":run_id,"mode":mode,"metrics":metrics,"evidence":evidence})
    print(json.dumps({"run_id":run_id,"engineering_evaluation":evidence["engineering_evaluation"]}))
    return 0 if evidence["engineering_evaluation"] == "PARTIAL_CAD_MEASURED" else 2


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


def batch_evaluation_context(plan_path, slot):
    import pilot_batch as batch
    plan = batch.read(plan_path)
    batch.verify(plan)
    if slot not in plan["models"]:
        raise ValueError("evaluation slot absent from plan")
    return plan, {"plan_sha256": batch.sha(plan_path), "slot": slot,
                  "model_config_sha256": batch.config_hash(plan["models"][slot]),
                  "deadline": plan["deadline"], "budget": plan["budget"],
                  "addendum_sha256": plan["addendum_sha256"],
                  "policy": "Independent evaluation of frozen output; never authorizes another model request"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot", choices=("model_A", "model_B", "model_C"))
    parser.add_argument("--submission", type=Path)
    parser.add_argument("--integration", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument("--mode", default="OFFLINE_INTEGRATION")
    parser.add_argument("--kit", type=Path)
    parser.add_argument("--results-root", type=Path)
    parser.add_argument("--record-id")
    parser.add_argument("--batch-id")
    parser.add_argument("--execution-plan", type=Path)
    args = parser.parse_args()
    if args.integration:
        if args.submission is None:
            parser.error("--integration requires --submission")
        context = None
        if args.execution_plan is not None:
            import pilot_batch as batch
            plan, context = batch_evaluation_context(args.execution_plan, args.slot)
            name = plan["run_names"][args.slot]
            expected = {"kit":batch.local(plan["paths"]["kit"]),
                        "results_root":batch.local(plan["paths"]["results_root"]),
                        "submission":batch.local(plan["paths"]["output_root"]) / name / "final"}
            if any(getattr(args,k) is None or getattr(args,k).absolute() != v for k,v in expected.items()):
                parser.error("evaluation paths differ from batch plan")
            if (args.batch_id, args.run_id, args.record_id, args.mode) != (
                    plan["batch_id"], plan["batch_id"]+"/"+name+"/evaluation", name+"/evaluation", plan["mode"]):
                parser.error("evaluation identity differs from batch plan")
        raise SystemExit(evaluate_integration(args.submission, run_id=args.run_id or INTEGRATION_RUN, mode=args.mode,
                                             kit=args.kit, results_root=args.results_root,
                                             record_id=args.record_id, batch_id=args.batch_id, execution_context=context))
    if args.slot is None:
        parser.error("--slot is required unless --integration is used")
    result = evaluate(args.slot, args.submission)
    write_json(RESULTS / args.slot / "metrics.json", result)
    print(json.dumps({"slot": args.slot, "status": result["evidence"]["generation_status"],
                      "engineering_evaluation": "NOT_RUN", "failure_type": result["evidence"]["failure_type"]}))
    return 2 if args.submission is None or result["evidence"]["intake"]["intake_status"] != "FILE_CONTRACT_ACCEPTED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
