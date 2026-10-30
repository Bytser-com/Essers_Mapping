"""Offline regression tests. No API calls or Gemini access required.

Run: python -m unittest scripts.test_core -v
"""
import tempfile
import unittest
from pathlib import Path

from .mapping_validator import validate_mappings
from .readprompt import build_mapping_contents
from .xml_parser import (
    discover_historical_pairs, leaf_values, parse_xml_directory,
    parse_xml_files, read_raw_xml, select_historical_examples,
    select_raw_examples,
)
from main import _benchmark_evaluation, _proposals_needing_retry, _target_batches, _split_benchmark_pairs

ROOT = Path(__file__).resolve().parent.parent


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = parse_xml_directory(ROOT / 'data' / 'source')
        cls.pairs = discover_historical_pairs(ROOT / 'data' / 'historical')
        cls.target = parse_xml_files([p['converted_file'] for p in cls.pairs])

    def test_complete_historical_pair_discovery(self):
        self.assertEqual(len(self.pairs), 400)
        self.assertEqual({p['company'] for p in self.pairs}, {'christeyns', 'chugoku', 'hempel'})
        self.assertEqual(len(self.source), 378)
        self.assertEqual(len(self.target), 96)

    def test_source_and_target_path_validation(self):
        invalid = {'source_path': '/not/a/real/path', 'target_path': self.target[0]['path'],
                   'rule_type': 'DIRECT', 'confidence': 95}
        accepted, rejected, issues = validate_mappings([invalid], self.source, self.target)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(rejected), 0)
        self.assertTrue(accepted[0]['requires_review'])
        self.assertEqual(len(issues), 1)
        accepted, rejected, _ = validate_mappings([{**invalid, 'target_path': '/fake'}], self.source, self.target)
        self.assertFalse(accepted)
        self.assertEqual(len(rejected), 1)

    def test_raw_xml_is_raw_not_json(self):
        original = self.pairs[0]['original_file']
        xml = read_raw_xml(original)
        self.assertIn('<', xml)
        self.assertIn('>', xml)
        self.assertNotIn('"original_json":', xml)

    def test_samples_do_not_cut_xml(self):
        paths = sorted((ROOT / 'data' / 'source').rglob('*.xml'))
        samples = select_raw_examples(paths, sample_count=2, max_chars=180000)
        self.assertGreaterEqual(len(samples), 1)
        self.assertLessEqual(sum(len(d['xml']) for d in samples), 180000)
        for doc in samples:
            self.assertEqual(doc['xml'], read_raw_xml(doc['path']))

    def test_target_batches_cover_all_fields(self):
        batches = _target_batches(self.target[:32], 10)
        self.assertEqual([f['path'] for batch in batches for f in batch],
                         [f['path'] for f in self.target[:32]])
        self.assertTrue(all(len(batch) <= 10 for batch in batches))

    def test_no_historical_evidence_control(self):
        self.assertEqual(select_historical_examples(self.pairs, 0), [])

    def test_heldout_company_never_enters_prompt(self):
        training = [p for p in self.pairs if p['company'] != 'hempel']
        heldout = [p for p in self.pairs if p['company'] == 'hempel']
        source_inventory = parse_xml_files([p['original_file'] for p in heldout])
        target_inventory = parse_xml_files([p['converted_file'] for p in training])
        source_doc = select_raw_examples([p['original_file'] for p in heldout], 1, 60000)
        history_doc = select_historical_examples(training, 1)
        content = build_mapping_contents(source_inventory, target_inventory[:3], target_inventory,
                                         source_doc, history_doc, [])
        self.assertIn('HISTORICAL MATCHED CONVERSION EXAMPLES', content)
        self.assertNotIn('Outbound_Hempel_001_Converted.xml', content)
        self.assertNotIn('--- MATCHING HISTORICAL CONVERTED: hempel', content)
        self.assertTrue(all(pair['company'] != 'hempel' for pair in history_doc))

    def test_retry_missing_target_or_invalid_path(self):
        target_batch = self.target[:2]
        source_paths = {f['path'] for f in self.source}
        proposal = {'target_path': target_batch[0]['path'], 'source_path': '/fake', 'rule_type': 'DIRECT'}
        self.assertEqual(len(_proposals_needing_retry([proposal], target_batch, source_paths)), 2)

    def test_same_company_seed_split_is_strict_and_reproducible(self):
        hempel = [p for p in self.pairs if p['company'] == 'hempel']
        seed, test, docs = _split_benchmark_pairs(hempel, 5)
        self.assertEqual((len(seed), len(test), len(docs)), (5, 145, 5))
        seed_ids = {p['pair_id'] for p in seed}
        self.assertFalse(seed_ids & {p['pair_id'] for p in test})
        self.assertEqual(
            seed_ids,
            {p['pair_id'] for p in _split_benchmark_pairs(hempel, 5)[0]},
        )
        self.assertTrue(all(d['company'] == 'hempel' for d in docs))

    def test_test_conversions_absent_from_seed_prompt(self):
        hempel = [p for p in self.pairs if p['company'] == 'hempel']
        non_hempel = [p for p in self.pairs if p['company'] != 'hempel']
        seed, test, docs = _split_benchmark_pairs(hempel, 5)
        source_inventory = parse_xml_files([p['original_file'] for p in test])
        target_inventory = parse_xml_files([p['converted_file'] for p in non_hempel])
        raw_samples = select_raw_examples([p['original_file'] for p in test], 2, 180000)
        control = build_mapping_contents(source_inventory, target_inventory[:10],
                                         target_inventory, raw_samples, [], [])
        treatment = build_mapping_contents(source_inventory, target_inventory[:10],
                                           target_inventory, raw_samples, docs, [])
        self.assertEqual(len(test), 145)
        self.assertTrue(all(d['converted_filename'] in treatment for d in docs))
        self.assertTrue(all(d['converted_filename'] not in control for d in docs))
        self.assertTrue(all(p['converted_file'].name not in treatment for p in test))
        self.assertTrue(all(p['converted_file'].name not in control for p in test))

    def test_heldout_direct_value_agreement_is_observation_only(self):
        hempel = [p for p in self.pairs if p['company'] == 'hempel'][:3]
        proposal = {
            'source_path': '/OutboundExpected/Head/ShipmentID',
            'target_path': '/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1SHP_OBDLV_SAVE_REPLICA/E1BPOBDLVHDR/DELIV_NUMB',
            'rule_type': 'DIRECT', 'requires_review': False,
            'transformation': '', 'condition': '', 'lookup': '',
        }
        with tempfile.TemporaryDirectory() as temp:
            report = _benchmark_evaluation([proposal], hempel, Path(temp))
        self.assertEqual(report['total_pair_field_checks'], 3)
        self.assertEqual(report['exact_value_agreements'], 3)
        self.assertIn('require expert review', report['important_limitations'])


if __name__ == '__main__':
    unittest.main()
