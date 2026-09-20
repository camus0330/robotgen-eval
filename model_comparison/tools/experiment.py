#!/usr/bin/env python3
"""File intake and experiment provenance only. Never executes submitted code."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

KIT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = KIT_ROOT.parent
JOINTS = [f'{side}_{joint}_pitch' for side, joints in
          [('left', ['shoulder', 'elbow']), ('right', ['shoulder', 'elbow']),
           ('left', ['hip', 'knee']), ('right', ['hip', 'knee'])] for joint in joints]
CONTACTS = {'left_hand', 'right_hand', 'left_foot', 'right_foot'}
FILES = {'cad_source', 'assembly_step', 'bom', 'mjcf', 'urdf', 'controller',
         'readme', 'limitations', 'dependencies'}


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    def reject(value):
        raise ValueError('Non-finite JSON value: ' + value)
    return json.loads(Path(path).read_text(encoding='utf-8'), parse_constant=reject)


def write_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def file_path(root, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Missing file path')
    rel = Path(value)
    if rel.is_absolute() or '..' in rel.parts:
        raise ValueError('Path must be relative and cannot contain ..: ' + value)
    path = (root / rel).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Path escapes submission: ' + value)
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError('Missing or empty file: ' + value)
    return path


def manifest(folder):
    return [{'path': str(p.relative_to(folder)), 'sha256': digest(p)}
            for p in sorted(folder.rglob('*')) if p.is_file()]


def verify_inputs(home=KIT_ROOT):
    expected = read(home / 'records/input_manifest.json')['files']
    actual = manifest(home / 'inputs')
    if expected != actual:
        raise ValueError('Input files changed, added or removed; create a new experiment version')
    return digest(home / 'records/input_manifest.json')


def prepare_inputs(home=KIT_ROOT, workspace=WORKSPACE):
    dest = home / 'inputs'
    if dest.exists() or (home / 'records/input_manifest.json').exists():
        raise FileExistsError('Input snapshot exists; refusing overwrite')
    pairs = [(home / name, name) for name in
             ['TASK_SPEC.md', 'SUBMISSION_SPEC.md', 'PROMPT.md', 'protocol.json']]
    pairs += [(home / 'templates' / name, 'templates/' + name)
              for name in ['submission.json', 'design_manifest.json']]
    bench = workspace / 'configs/benchmark'
    pairs += [(bench / 'profile.json', 'motion_profile.json'),
              (bench / 'digital_profile.json', 'legacy_digital_profile.json'),
              (bench / 'digital_metrics.csv', 'legacy_metrics_reference.csv'),
              (bench / 'robustness_cases_public.jsonl', 'robustness_cases_public.jsonl'),
              (bench / 'environment.lock.txt', 'environment.lock.txt'),
              (workspace / 'data/xl330_m288_t.step', 'assets/xl330_m288_t.step'),
              (workspace / 'data/reference.png', 'assets/reference.png')]
    for source, _ in pairs:
        if not source.is_file():
            raise FileNotFoundError(source)
    for source, relative in pairs:
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    write_new(home / 'records/input_manifest.json', {
        'scope': 'public model inputs; excludes existing robot solution', 'files': manifest(dest)})


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def rigid_transform(matrix):
    if not isinstance(matrix, list) or len(matrix) != 4:
        return False
    if any(not isinstance(row, list) or len(row) != 4 or
           not all(number(x) for x in row) for row in matrix):
        return False
    if any(abs(a-b) > 1e-6 for a, b in zip(matrix[3], [0, 0, 0, 1])):
        return False
    r = matrix
    for i in range(3):
        for j in range(3):
            if abs(sum(r[k][i]*r[k][j] for k in range(3)) - int(i == j)) > 1e-6:
                return False
    det = (r[0][0]*(r[1][1]*r[2][2]-r[1][2]*r[2][1])
           - r[0][1]*(r[1][0]*r[2][2]-r[1][2]*r[2][0])
           + r[0][2]*(r[1][0]*r[2][1]-r[1][1]*r[2][0]))
    return abs(det-1) <= 1e-6


def validate(root, home=KIT_ROOT):
    root = Path(root).resolve()
    errors = []
    evidence = {}

    def check(ok, message):
        if not ok:
            errors.append(message)

    def checkfile(value):
        try:
            path = file_path(root, value)
            evidence[value] = digest(path)
        except (ValueError, OSError) as error:
            errors.append(str(error))

    status = None
    try:
        meta_path = file_path(root, 'submission.json')
        meta = read(meta_path)
        evidence['submission.json'] = digest(meta_path)
        status = meta.get('status')
        check(status in {'COMPLETED', 'GENERATION_FAILED', 'TIMEOUT'}, 'Attempt not completed: ' + str(status))
        for field in ['submission_id', 'model_provider', 'model_exact_version', 'invocation_mode', 'session_id']:
            check(isinstance(meta.get(field), str) and bool(meta[field].strip()), 'Missing metadata: ' + field)
        check(meta.get('model_slot') in {'model_A', 'model_B', 'model_C'}, 'Unknown model_slot')
        check(meta.get('phase') in {'pilot', 'formal'}, 'Invalid phase')
        check(type(meta.get('attempt')) is int and 1 <= meta['attempt'] <= (1 if meta.get('phase') == 'pilot' else 5), 'Invalid attempt number')
        for field in ['actual_elapsed_s', 'human_edit_minutes']:
            check(number(meta.get(field)) and meta[field] >= 0, 'Invalid metadata: ' + field)
        check(type(meta.get('feedback_rounds')) is int and meta['feedback_rounds'] >= 0, 'Invalid feedback_rounds')
        expected_hash = verify_inputs(home)
        check(meta.get('input_manifest_sha256') == expected_hash, 'Input manifest hash missing or mismatched')
        check(meta.get('prompt_sha256') == digest(home / 'inputs/PROMPT.md'), 'Prompt hash missing or mismatched')
        logs = meta.get('logs')
        check(isinstance(logs, list) and bool(logs), 'Raw logs required')
        for path in logs if isinstance(logs, list) else []:
            checkfile(path)
        edits = meta.get('human_edits', [])
        check(isinstance(edits, list), 'human_edits must be a list')
        for path in edits if isinstance(edits, list) else []:
            checkfile(path)
        if meta.get('human_edit_minutes', 0):
            check(bool(edits), 'Human edits require diff evidence')
        if any(meta.get(key) is None for key in ['actual_cost', 'usage_tokens', 'generation_seed']):
            check(isinstance(meta.get('unknown_fields_reason'), str) and bool(meta['unknown_fields_reason'].strip()), 'Explain unknown cost/token/seed fields')
        if status == 'COMPLETED':
            design_path = file_path(root, 'design_manifest.json')
            design = read(design_path)
            evidence['design_manifest.json'] = digest(design_path)
            check(design.get('units') == {'cad': 'mm', 'simulation': 'm/kg/s/rad'}, 'Wrong or missing units')
            for key in sorted(FILES):
                checkfile(design.get('files', {}).get(key))
            cmd = design.get('rebuild_command')
            check(isinstance(cmd, list) and bool(cmd) and all(isinstance(s, str) and s.strip() for s in cmd), 'rebuild_command must be a nonempty string array')
            parts = design.get('parts', [])
            ids = [p['id'] for p in parts]
            check(bool(ids) and len(ids) == len(set(ids)) and all(isinstance(x, str) and x.strip() for x in ids), 'Parts must have unique nonempty IDs')
            for part in parts:
                check(type(part.get('quantity')) is int and part['quantity'] > 0, 'Invalid part quantity')
                checkfile(part.get('step'))
                checkfile(part.get('stl'))
            joints = design.get('joints', [])
            check(len(joints) == 8 and {j['role'] for j in joints} == set(JOINTS), 'Exactly eight distinct joint roles required')
            names = [j['name'] for j in joints]
            check(len(set(names)) == 8 and all(isinstance(x, str) and x.strip() for x in names), 'Eight distinct actual joint names required')
            contacts = design.get('contacts', {})
            check(set(contacts) == CONTACTS, 'Four semantic contacts required')
            values = list(contacts.values())
            check(len(set(values)) == 4 and all(isinstance(x, str) and x.strip() for x in values), 'Four distinct contact geoms required')
            for motion in ['swing', 'wave']:
                for key in ['reference', 'config']:
                    checkfile(design.get('motions', {}).get(motion, {}).get(key))
            interfaces = design.get('interfaces', [])
            interface_ids = [i['id'] for i in interfaces]
            check(len(set(interface_ids)) == len(interface_ids) and all(isinstance(x, str) and x.strip() for x in interface_ids), 'Interface IDs must be unique and nonempty')
            required = {(j, kind) for j in JOINTS for kind in ['case_mount', 'horn_mount']}
            supplied = {(i['joint_role'], i['kind']) for i in interfaces}
            check(required <= supplied, 'Missing required case/horn interfaces for eight motors')
            for interface in interfaces:
                check(interface['part_id'] in ids, 'Interface references unknown part')
                check(interface['joint_role'] in JOINTS, 'Interface references unknown joint')
                check(rigid_transform(interface.get('frame_in_part_mm')), 'Invalid right-handed rigid interface transform')
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        errors.append('Malformed or missing submission: ' + str(error))
    result = 'INVALID' if errors else ('FILE_CONTRACT_ACCEPTED' if status == 'COMPLETED' else 'FAILED_ATTEMPT_RECORDED')
    return {'submission_path': str(root), 'intake_status': result, 'errors': errors,
            'engineering_evaluation': 'NOT_RUN', 'quality_score': None,
            'scope': 'file contract and declarations only; no geometry, dynamics or authenticity validation',
            'evidence_sha256': evidence}


def freeze(home, out):
    protocol = read(home / 'protocol.json')
    for model in protocol['models']:
        for field in ['provider', 'exact_version', 'invocation_mode', 'settings']:
            if not model.get(field):
                raise ValueError('Fill model configuration before freeze: ' + model['slot'] + '/' + field)
    if not protocol.get('environment_description'):
        raise ValueError('Fill environment_description before freeze')
    verify_inputs(home)
    if digest(home / 'protocol.json') != digest(home / 'inputs/protocol.json'):
        raise ValueError('Public protocol differs; create a new input snapshot in a new version directory')
    files = [home / name for name in ['protocol.json', 'TASK_SPEC.md', 'PROMPT.md', 'SUBMISSION_SPEC.md',
             'EXPERIMENT_PROTOCOL.md', 'tools/experiment.py', 'templates/submission.json', 'templates/design_manifest.json']]
    for name in ['TASK_SPEC.md', 'PROMPT.md', 'SUBMISSION_SPEC.md', 'templates/submission.json', 'templates/design_manifest.json']:
        if digest(home / name) != digest(home / 'inputs' / name):
            raise ValueError('Public input differs: ' + name)
    write_new(out, {'status': 'PROTOCOL_SNAPSHOT_ONLY', 'formal_engineering_ready': False,
                    'input_manifest_sha256': verify_inputs(home),
                    'files': [{'path': str(p.relative_to(home)), 'sha256': digest(p)} for p in files]})


def refresh_inputs(label, home=KIT_ROOT):
    if not label or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in label):
        raise ValueError('Archive label must contain only letters, digits, underscore or hyphen')
    submissions = list((home / 'submissions').glob('*/*/*/submission.json'))
    for path in submissions:
        meta = read(path)
        if meta.get('status') != 'NOT_STARTED' or meta.get('logs'):
            raise ValueError('Attempts have started; use a separate experiment version directory')
    archive = home / 'records/input_versions' / label
    if archive.exists():
        raise FileExistsError('Archive label already exists')
    verify_inputs(home)
    archive.mkdir(parents=True)
    shutil.move(str(home / 'inputs'), str(archive / 'inputs'))
    shutil.move(str(home / 'records/input_manifest.json'), str(archive / 'input_manifest.json'))
    try:
        prepare_inputs(home, home.parent)
    except Exception:
        if (home / 'inputs').exists():
            shutil.rmtree(home / 'inputs')
        (home / 'records/input_manifest.json').unlink(missing_ok=True)
        shutil.move(str(archive / 'inputs'), str(home / 'inputs'))
        shutil.move(str(archive / 'input_manifest.json'), str(home / 'records/input_manifest.json'))
        archive.rmdir()
        raise
    for path in submissions:
        meta = read(path)
        meta['input_manifest_sha256'] = digest(home / 'records/input_manifest.json')
        meta['prompt_sha256'] = digest(home / 'inputs/PROMPT.md')
        path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('prepare-inputs')
    sub.add_parser('verify-inputs')
    refresh = sub.add_parser('refresh-inputs'); refresh.add_argument('--archive-label', required=True)
    val = sub.add_parser('validate'); val.add_argument('root', type=Path); val.add_argument('--out', type=Path)
    inv = sub.add_parser('inventory'); inv.add_argument('--out', required=True, type=Path)
    fr = sub.add_parser('freeze'); fr.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'prepare-inputs':
            prepare_inputs(); print('Public input snapshot created')
        elif args.command == 'verify-inputs':
            print('Input snapshot verified: ' + verify_inputs())
        elif args.command == 'refresh-inputs':
            refresh_inputs(args.archive_label); print('Previous inputs archived; unstarted attempts bound to new inputs')
        elif args.command == 'validate':
            result = validate(args.root)
            if args.out:
                write_new(args.out, result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 2 if result['errors'] else 0
        elif args.command == 'freeze':
            freeze(KIT_ROOT, args.out); print('Protocol snapshot created; engineering readiness not asserted')
        elif args.command == 'inventory':
            rows = []
            for path in sorted((KIT_ROOT / 'submissions').glob('*/*/*/submission.json')):
                result = validate(path.parent)
                rows.append({'attempt': str(path.parent.relative_to(KIT_ROOT / 'submissions')),
                             'generation_status': read(path).get('status', 'UNKNOWN'),
                             'intake_status': result['intake_status'], 'engineering_evaluation': 'NOT_RUN',
                             'error_count': len(result['errors'])})
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open('x', encoding='utf-8-sig', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=['attempt', 'generation_status', 'intake_status', 'engineering_evaluation', 'error_count'])
                writer.writeheader(); writer.writerows(rows)
            print(f'{len(rows)} attempt records written; no engineering scores')
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
