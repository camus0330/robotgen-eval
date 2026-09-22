"""Independent, read-only intake adapter; no invented engineering score."""
import argparse
import hashlib
import json
from pathlib import Path

from pilot_run import KIT, RECORDS, RESULTS, ROOT, write_json
from pilot_sandbox import execute_python

VERSION = "pilot-intake-20260923.1"
ENGINEERING = ("clean_rebuild", "step_kernel_readback", "solid_validity_volume_count",
               "all_printed_parts_envelope", "mesh_reference_closure", "urdf_mjcf_load",
               "joint_tree_actuator_contract", "swing_replay", "wave_replay", "robustness")


def intake(submission):
    source = "import sys,json; from pathlib import Path; sys.path.insert(0,'/kit/tools'); import experiment; print(json.dumps(experiment.validate(Path('/submission'),Path('/kit'))))"
    child = execute_python(source, kit=KIT, submission=submission)
    if child.returncode:
        return {"intake_status": "EVALUATOR_ERROR", "child_exit_code": child.returncode}
    result = json.loads(child.stdout)
    # experiment.validate is unchanged; never run submitted code here.
    result["child_exit_code"] = child.returncode
    return result


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
    parser.add_argument("--slot", choices=("model_A", "model_B", "model_C"), required=True)
    parser.add_argument("--submission", type=Path)
    args = parser.parse_args()
    result = evaluate(args.slot, args.submission)
    write_json(RESULTS / args.slot / "metrics.json", result)
    print(json.dumps({"slot": args.slot, "status": result["evidence"]["generation_status"],
                      "engineering_evaluation": "NOT_RUN", "failure_type": result["evidence"]["failure_type"]}))
    return 2 if args.submission is None or result["evidence"]["intake"]["intake_status"] != "FILE_CONTRACT_ACCEPTED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
