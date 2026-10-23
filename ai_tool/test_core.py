"""Zero-dependency unit tests for XML parsing and structural validation."""
import unittest
from pathlib import Path
from xml_parser import parse_xml_directory
from mapping_validator import validate_mappings

ROOT = Path(__file__).resolve().parent


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.source = parse_xml_directory(ROOT / 'data/source')
        self.target = parse_xml_directory(ROOT / 'data/target')

    def test_paths_discovered(self):
        paths = {row['path'] for row in self.source}
        self.assertIn('/DELVRY03/IDOC/E1EDL20/VBELN', paths)

    def test_invalid_source_flagged(self):
        proposed = [{
            'source_path': '/not/real',
            'target_path': self.target[0]['path'],
            'rule_type': 'DIRECT', 'confidence': 95,
        }]
        accepted, rejected, issues = validate_mappings(proposed, self.source, self.target)
        self.assertEqual(len(rejected), 0)
        self.assertTrue(accepted[0]['requires_review'])
        self.assertEqual(len(issues), 1)

    def test_invalid_target_rejected(self):
        proposed = [{
            'source_path': self.source[0]['path'],
            'target_path': '/fake/target',
            'rule_type': 'DIRECT', 'confidence': 95,
        }]
        accepted, rejected, issues = validate_mappings(proposed, self.source, self.target)
        self.assertEqual(len(accepted), 0)
        self.assertEqual(len(rejected), 1)


if __name__ == '__main__':
    unittest.main()
