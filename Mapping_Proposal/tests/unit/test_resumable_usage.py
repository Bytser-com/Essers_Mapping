"""Offline regression tests for durable token tracking, risk severity and legacy CSV."""
from pathlib import Path
import csv
import json
import tempfile
import unittest

from scripts.experiment_tracker import ExperimentTracker
from scripts.mapping_validator import validate_mappings


class UsageTrackingTests(unittest.TestCase):
    def test_resumption_preserves_usage_and_does_not_double_count_restored_batch(self):
        with tempfile.TemporaryDirectory() as root_name:
            root = Path(root_name)
            run = root / 'output' / 'runs' / 'test-job'
            def tracker():
                return ExperimentTracker(settings={'model': 'test'}, root=root,
                                         run_dir=run, job_signature='abcdef')
            first = tracker()
            first.begin_batch(1)
            first.event({'type': 'attempt'})
            first.event({'type': 'usage', 'input_tokens': 120, 'output_tokens': 10, 'total_tokens': 130})
            checkpoint_metrics = first.batch_metrics(1)
            self.assertEqual(checkpoint_metrics['input_tokens'], 120)
            first.begin_batch(2)
            first.event({'type': 'attempt'})
            first.event({'type': 'api_error', 'code': 503})
            first.finish(status='failed', stage='gemini', error=RuntimeError('simulated'))
            second = tracker()
            second.begin_batch(1)
            second.restored_batch(1, checkpoint_metrics)
            second.begin_batch(2)
            second.event({'type': 'attempt'})
            second.event({'type': 'usage', 'input_tokens': 140, 'output_tokens': 15, 'total_tokens': 155})
            result = second.finish(status='completed')
            self.assertEqual(result['input_tokens'], 260)
            self.assertEqual(result['output_tokens'], 25)
            self.assertEqual(result['total_tokens'], 285)
            self.assertEqual(result['execution_input_tokens'], 140)
            self.assertEqual(result['batches_restored'], 1)
            self.assertEqual(result['job_api_attempts'], 3)
            third = tracker()
            third.begin_batch(1)
            third.restored_batch(1, checkpoint_metrics)
            third.begin_batch(2)
            third.restored_batch(2, second.batch_metrics(2))
            self.assertEqual(third.finish(status='completed')['input_tokens'], 260)
            ledger = json.loads((run / 'usage_ledger.json').read_text())
            self.assertEqual(ledger['totals']['input_tokens'], 260)

    def test_legacy_checkpoint_is_marked_incomplete(self):
        with tempfile.TemporaryDirectory() as root_name:
            root = Path(root_name)
            tr = ExperimentTracker(settings={}, root=root,
                                   run_dir=root / 'output' / 'runs' / 'legacy', job_signature='old')
            tr.restored_batch(1, None)
            record = tr.finish(status='completed')
            self.assertFalse(record['token_accounting_complete'])

    def test_legacy_csv_header_is_migrated_without_misalignment(self):
        with tempfile.TemporaryDirectory() as root_name:
            root = Path(root_name)
            csv_file = root / 'output' / 'experiments.csv'
            csv_file.parent.mkdir(parents=True)
            csv_file.write_text('run_id,status,input_tokens\nold1,completed,123\n')
            tr = ExperimentTracker(settings={}, root=root,
                                   run_dir=root / 'output' / 'runs' / 'csv-test', job_signature='sig')
            tr.finish(status='completed')
            with csv_file.open(encoding='utf-8-sig', newline='') as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]['run_id'], 'old1')
            self.assertEqual(rows[0]['input_tokens'], '123')
            self.assertEqual(len(rows), 2)
            self.assertIn('execution_input_tokens', rows[1])

    def test_risk_severity_normalization_and_unknown_category_review(self):
        source = [{'path': '/Source/A'}]
        target = [{'path': '/Target/B'}]
        def proposal(risk):
            return {'source_path':'/Source/A','target_path':'/Target/B',
                    'rule_type':'DIRECT','risk_category':risk,'confidence':80,
                    'requires_review':False, 'review_priority':'LOW'}
        for risk, expected, review in [('Low','LOW',False), ('NONE','LOW',False),
                                      ('DATA_INTEGRITY','HIGH',True)]:
            accepted, _, issues = validate_mappings([proposal(risk)], source, target)
            self.assertEqual(accepted[0]['risk_category'], expected)
            self.assertEqual(bool(accepted[0]['requires_review']), review)
            self.assertEqual(bool(issues), review)


if __name__ == '__main__':
    unittest.main()
