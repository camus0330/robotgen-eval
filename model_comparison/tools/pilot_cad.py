"""Source-only pilot CAD rebuild and kernel readback, rule version 2."""
import hashlib
import json
import math
from pathlib import Path
import shlex
import struct

from pilot_snapshot import safe_snapshot, relative_name
from pilot_sandbox import execute_command, execute_python

VERSION = "pilot-cad-20260923.2"


class RebuildContractError(ValueError):
    pass


def validate_rebuild_contract(manifest, inventory):
    groups = {}
    for key in ("rebuild_inputs", "rebuild_outputs", "rebuild_excluded"):
        value = manifest.get(key, [] if key == "rebuild_excluded" else None)
        if not isinstance(value, list) or not all(isinstance(p, str) for p in value):
            raise RebuildContractError("SOURCE_OUTPUT_CONTRACT_UNCLEAR: " + key)
        groups[key] = {relative_name(p) for p in value}
        if len(groups[key]) != len(value):
            raise RebuildContractError("duplicate contract paths")
    inputs, outputs, excluded = (groups[k] for k in groups)
    if not inputs or not outputs or inputs & outputs or inputs & excluded or outputs & excluded:
        raise RebuildContractError("overlapping or empty input/output contract")
    declared_names = [p for group in groups.values() for p in group]
    if len({p.casefold() for p in declared_names}) != len(declared_names):
        raise RebuildContractError("case-aliased contract paths")
    if "design_manifest.json" in inputs | outputs | excluded or "submission.json" in outputs:
        raise RebuildContractError("metadata may not be generated")
    files = {row["path"] for row in inventory["files"]}
    if not inputs <= files or files - inputs - outputs - excluded - {"design_manifest.json", "submission.json"}:
        raise RebuildContractError("SOURCE_OUTPUT_CONTRACT_UNCLEAR: unclassified or missing files")
    try:
        declared = {relative_name(manifest["files"]["assembly_step"])}
    except (KeyError, TypeError) as error:
        raise RebuildContractError("assembly STEP path missing") from error
    if not manifest.get("parts"):
        raise RebuildContractError("no declared printed parts")
    for part in manifest["parts"]:
        declared.update((relative_name(part["step"]), relative_name(part["stl"])))
    if not declared <= outputs:
        raise RebuildContractError("every assessed CAD output must be generated")
    if any(Path(p).suffix.lower() in (".step", ".stp", ".stl") for p in inputs):
        raise RebuildContractError("prebuilt CAD cannot be a source input")
    command = manifest.get("rebuild_command")
    if not isinstance(command, list) or len(command) != 2 or command[0] not in ("python", "python3", "/cad/bin/python"):
        raise RebuildContractError("supported contract: Python source entrypoint plus input files")
    if relative_name(command[1]) not in inputs or not command[1].endswith(".py"):
        raise RebuildContractError("entrypoint must be a declared Python source input")
    # Invoke the exact declared source using the reviewed sandbox interpreter.
    return inputs, outputs, ["/cad/bin/python", "-B", command[1]]


def source_rebuild(received, destination, *, kit):
    received, destination = Path(received), Path(destination)
    inventory = safe_snapshot(received)
    manifest = json.loads((received / "design_manifest.json").read_text(encoding="utf-8"))
    inputs, outputs, command = validate_rebuild_contract(manifest, inventory)
    workspace = destination / "work"
    before = safe_snapshot(received, workspace, include=inputs | {"design_manifest.json"})
    assert not outputs & {row["path"] for row in before["files"]}
    child = execute_command(shlex.join(command), kit=kit, writable_output=workspace, seconds=60, cad=True)
    execution = {"command":command, "os_exit_code":child.returncode,
                 "stdout_sha256":hashlib.sha256(child.stdout.encode()).hexdigest(),
                 "stderr_sha256":hashlib.sha256(child.stderr.encode()).hexdigest()}
    (destination / "rebuild_execution.json").write_text(json.dumps(execution, indent=2)+"\n", encoding="utf-8")
    # Namespace process has exited (including timeout=124); inspect before reads.
    rebuilt = destination / "rebuilt"
    after = safe_snapshot(workspace, rebuilt)
    actual = {row["path"]: row for row in after["files"]}
    missing = sorted(p for p in outputs if p not in actual or actual[p]["size"] == 0)
    source_changed = [r["path"] for r in before["files"] if actual.get(r["path"]) != r]
    return rebuilt, {"rule_version": VERSION, "command": command, "os_exit_code": child.returncode,
                     "stdout_sha256": hashlib.sha256(child.stdout.encode()).hexdigest(),
                     "stderr_sha256": hashlib.sha256(child.stderr.encode()).hexdigest(),
                     "source_snapshot": before, "rebuilt_snapshot": after,
                     "expected_outputs": sorted(outputs), "missing_outputs": missing,
                     "source_changed": source_changed,
                     "outputs_created": child.returncode == 0 and not missing and not source_changed}


def step_readback(submission, paths, *, kit):
    # Operator code only; never import the design's Python during measurement.
    source = '''import json, math, importlib.metadata as meta
from pathlib import Path
try:
 import cadquery as cq
except Exception as e:
 print(json.dumps({'environment':'UNAVAILABLE','error_class':type(e).__name__})); raise SystemExit(3)
results=[]
for name in PATHS:
 try:
  obj=cq.importers.importStep(str(Path('/submission')/name))
  solids=obj.solids().vals()
  volume=sum(s.Volume() for s in solids)
  box=obj.val().BoundingBox()
  valid=bool(solids) and all(s.isValid() for s in solids) and math.isfinite(volume) and volume>0
  results.append({'path':name,'status':'PASS' if valid else 'FAIL','solid_count':len(solids),'valid':valid,'volume_mm3':volume,'bbox_mm':[box.xlen,box.ylen,box.zlen]})
 except Exception as e:
  results.append({'path':name,'status':'FAIL','failure_type':'STEP_READBACK_FAILED','error_class':type(e).__name__})
print(json.dumps({'environment':'PASS','interpreter':'/cad/bin/python','versions':{n:meta.version(n) for n in ('cadquery','cadquery-ocp')},'parts':results}))
'''.replace("PATHS", repr([relative_name(p) for p in paths]))
    child = execute_python(source, kit=kit, submission=submission, cad=True, seconds=60)
    try:
        evidence = json.loads(child.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        evidence = {"environment": "UNAVAILABLE", "failure_type": "SANDBOX_OR_IMPORT_FAILED"}
    evidence.update(os_exit_code=child.returncode, stdout_sha256=hashlib.sha256(child.stdout.encode()).hexdigest(),
                    stderr_sha256=hashlib.sha256(child.stderr.encode()).hexdigest())
    return evidence


def stl_measure(path):
    """ASCII/binary triangle bbox and signed-volume proxy, no solid-validity claim."""
    try:
        data = Path(path).read_bytes()
        vertices = []
        if len(data) >= 84 and len(data) == 84 + struct.unpack_from('<I', data, 80)[0] * 50:
            for offset in range(84, len(data), 50):
                values = struct.unpack_from('<12fH', data, offset)
                vertices.extend((values[3:6], values[6:9], values[9:12]))
        else:
            for line in data.decode('ascii').splitlines():
                f = line.split()
                if f and f[0].lower() == 'vertex':
                    if len(f) != 4:
                        return None
                    vertices.append(tuple(float(v) for v in f[1:]))
        if not vertices or len(vertices) % 3 or not all(math.isfinite(x) for v in vertices for x in v):
            return None
        low = [min(v[i] for v in vertices) for i in range(3)]
        high = [max(v[i] for v in vertices) for i in range(3)]
        volume = 0.0
        for i in range(0, len(vertices), 3):
            a, b, c = vertices[i:i+3]
            volume += (a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0])) / 6
        return {"triangle_count": len(vertices)//3, "bbox_mm": {"min": low, "max": high, "size": [b-a for a,b in zip(low,high)]},
                "absolute_volume_proxy_mm3": abs(volume), "solid_validity_checked": False}
    except (OSError, UnicodeError, ValueError, struct.error):
        return None
