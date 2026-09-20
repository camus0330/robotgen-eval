import hashlib
import tempfile
import unittest
from pathlib import Path
from scripts.benchmark.evaluate_digital import Digital, paired_successes, validate_manifest


class DigitalTests(unittest.TestCase):
    def test_missing_second_motion_not_success(self):
        cases=[{'case_id':'x'}]
        rows=[dict(case_id='x',motion='swing',task_pass=True,actuation_pass=True)]
        self.assertEqual(paired_successes(rows,cases,['swing','wave']),(False,0))

    def test_duplicate_cannot_replace_missing_trial(self):
        cases=[{'case_id':'x'}]
        row=dict(case_id='x',motion='swing',task_pass=True,actuation_pass=True)
        self.assertEqual(paired_successes([row,row],cases,['swing','wave']),(False,0))

    def test_actuation_failure_counts_even_if_task_succeeds(self):
        rows=[dict(case_id='x',motion=m,task_pass=True,actuation_pass=m=='swing') for m in ['swing','wave']]
        self.assertEqual(paired_successes(rows,[{'case_id':'x'}],['swing','wave']),(True,0))

    def test_hash_change_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'part.step';p.write_text('before')
            rows=[dict(path='part.step',sha256=hashlib.sha256(p.read_bytes()).hexdigest())]
            self.assertEqual(validate_manifest(root,rows),[])
            p.write_text('after');self.assertEqual(validate_manifest(root,rows),['part.step'])

    def test_empty_manifest_not_verified(self):
        self.assertTrue(validate_manifest(Path('.'),[]))

    def test_missing_evidence_is_explicit_failure_not_mechanical_measurement(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Digital(Path(tmp),Path(tmp));d.check(['DA05','DC03'],d.geometry)
            self.assertEqual(d.rows['DA05']['status'],'FAIL')
            self.assertEqual(d.rows['DA05']['failure_type'],'MISSING_EVIDENCE')


if __name__=='__main__':unittest.main()
