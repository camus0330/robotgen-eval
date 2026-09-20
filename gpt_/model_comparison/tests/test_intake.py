"""Contract tests use synthetic text files, never represent robot validation."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('experiment', Path(__file__).resolve().parents[1] / 'tools/experiment.py')
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        (self.home / 'inputs').mkdir()
        (self.home / 'inputs/PROMPT.md').write_text('synthetic prompt')
        mod.write_new(self.home / 'records/input_manifest.json', {'files': mod.manifest(self.home / 'inputs')})
        self.root = self.home / 'submission'
        self.root.mkdir()
        (self.root / 'fixture.txt').write_text('SYNTHETIC FILE CONTRACT TEST ONLY')
        self.meta = {'submission_id': 'fixture', 'model_slot': 'model_A', 'phase': 'pilot', 'attempt': 1,
                     'status': 'COMPLETED', 'model_provider': 'test', 'model_exact_version': 'test',
                     'invocation_mode': 'test', 'session_id': 'test', 'actual_elapsed_s': 1,
                     'human_edit_minutes': 0, 'feedback_rounds': 0, 'logs': ['fixture.txt'],
                     'unknown_fields_reason': 'synthetic fixture',
                     'input_manifest_sha256': mod.verify_inputs(self.home),
                     'prompt_sha256': mod.digest(self.home / 'inputs/PROMPT.md')}
        self.design = {'units': {'cad': 'mm', 'simulation': 'm/kg/s/rad'},
                       'files': dict.fromkeys(mod.FILES, 'fixture.txt'),
                       'rebuild_command': ['python3', 'fixture.txt'],
                       'parts': [{'id': 'arbitrary_name', 'quantity': 1, 'step': 'fixture.txt', 'stl': 'fixture.txt'}],
                       'joints': [{'role': j, 'name': 'actual_' + j} for j in mod.JOINTS],
                       'contacts': {k: 'actual_' + k for k in mod.CONTACTS},
                       'motions': {m: {'reference': 'fixture.txt', 'config': 'fixture.txt'} for m in ['swing', 'wave']},
                       'interfaces': [{'id': j + kind, 'joint_role': j, 'part_id': 'arbitrary_name', 'kind': kind,
                                       'frame_in_part_mm': [[1,0,0,7],[0,1,0,8],[0,0,1,9],[0,0,0,1]]}
                                      for j in mod.JOINTS for kind in ['case_mount', 'horn_mount']]}

    def run_intake(self):
        for name, data in [('submission.json', self.meta), ('design_manifest.json', self.design)]:
            (self.root / name).write_text(json.dumps(data))
        return mod.validate(self.root, self.home)

    def test_arbitrary_names_and_one_part_accepted_without_engineering_claim(self):
        result = self.run_intake()
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['intake_status'], 'FILE_CONTRACT_ACCEPTED')
        self.assertIsNone(result['quality_score'])
        self.assertEqual(result['engineering_evaluation'], 'NOT_RUN')

    def test_missing_file_rejected(self):
        self.design['files']['mjcf'] = 'absent.xml'
        self.assertTrue(self.run_intake()['errors'])

    def test_path_traversal_rejected(self):
        self.design['files']['mjcf'] = '../inputs/PROMPT.md'
        self.assertTrue(self.run_intake()['errors'])

    def test_symlink_escape_rejected(self):
        (self.root / 'escape').symlink_to(self.home / 'inputs/PROMPT.md')
        self.design['files']['mjcf'] = 'escape'
        self.assertTrue(self.run_intake()['errors'])

    def test_duplicate_joint_and_missing_interface_rejected(self):
        self.design['joints'][1] = copy.deepcopy(self.design['joints'][0])
        self.design['interfaces'].pop()
        errors = self.run_intake()['errors']
        self.assertTrue(any('joint roles' in e for e in errors))
        self.assertTrue(any('interfaces' in e for e in errors))

    def test_reflection_transform_rejected(self):
        self.design['interfaces'][0]['frame_in_part_mm'][0][0] = -1
        self.assertTrue(self.run_intake()['errors'])

    def test_input_mutation_rejected(self):
        (self.home / 'inputs/PROMPT.md').write_text('changed')
        self.assertTrue(self.run_intake()['errors'])

    def test_added_input_rejected(self):
        (self.home / 'inputs/leaked_solution.py').write_text('not allowed')
        self.assertTrue(self.run_intake()['errors'])

    def test_incomplete_attempt_is_not_zero_score(self):
        self.meta['status'] = 'NOT_STARTED'
        result = self.run_intake()
        self.assertEqual(result['intake_status'], 'INVALID')
        self.assertIsNone(result['quality_score'])

    def test_generation_failure_can_be_recorded_without_design(self):
        self.meta['status'] = 'GENERATION_FAILED'
        self.design = None
        result = self.run_intake()
        self.assertEqual(result['intake_status'], 'FAILED_ATTEMPT_RECORDED')

    def test_malformed_design_returns_structured_error(self):
        self.design['parts'] = None
        self.assertTrue(self.run_intake()['errors'])

    def test_hash_mismatch_rejected(self):
        self.meta['input_manifest_sha256'] = '0'*64
        self.assertTrue(self.run_intake()['errors'])

    def test_write_refuses_overwrite(self):
        path = self.home / 'result.json'
        mod.write_new(path, {})
        with self.assertRaises(FileExistsError):
            mod.write_new(path, {'changed': True})

    def test_refresh_archives_previous_inputs_and_rebinds_unstarted_attempt(self):
        path = self.home / 'submissions/pilot/model_A/01/submission.json'
        mod.write_new(path, {'status': 'NOT_STARTED', 'logs': []})
        old_hash = mod.verify_inputs(self.home)
        def replacement(home, workspace):
            (home / 'inputs').mkdir()
            (home / 'inputs/PROMPT.md').write_text('new prompt')
            mod.write_new(home / 'records/input_manifest.json', {'files': mod.manifest(home / 'inputs')})
        with patch.object(mod, 'prepare_inputs', side_effect=replacement):
            mod.refresh_inputs('draft', self.home)
        self.assertTrue((self.home / 'records/input_versions/draft/inputs/PROMPT.md').exists())
        self.assertNotEqual(old_hash, mod.verify_inputs(self.home))
        self.assertEqual(mod.read(path)['input_manifest_sha256'], mod.verify_inputs(self.home))

    def test_refresh_refuses_after_attempt_starts(self):
        mod.write_new(self.home / 'submissions/pilot/model_A/01/submission.json', {'status': 'COMPLETED'})
        with self.assertRaises(ValueError):
            mod.refresh_inputs('draft', self.home)

    def test_refresh_failure_restores_original_snapshot(self):
        old_hash = mod.verify_inputs(self.home)
        with patch.object(mod, 'prepare_inputs', side_effect=FileNotFoundError('missing source')):
            with self.assertRaises(FileNotFoundError):
                mod.refresh_inputs('draft', self.home)
        self.assertEqual(old_hash, mod.verify_inputs(self.home))

    def test_freeze_refuses_unknown_model(self):
        mod.write_new(self.home / 'protocol.json', {'models': [{'slot': 'model_A', 'provider': None}]})
        with self.assertRaises(ValueError):
            mod.freeze(self.home, self.home / 'freeze.json')


if __name__ == '__main__':
    unittest.main()
