"""Test release provenance and publishing with dummy images; no registry is contacted."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'Scripts/service-release.py'
spec = importlib.util.spec_from_file_location('service_release', SCRIPT)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
TREE = 'a' * 40
SHA = 'b' * 40
BASE = 'ghcr.io/example/repo/frontend'
IMAGE = BASE + '@sha256:' + 'c' * 64
BASH = 'C:/Program Files/Git/bin/bash.exe' if os.name == 'nt' else shutil.which('bash')


def record():
    return {'schema': 1, 'environment': 'Testing', 'service': 'Frontend',
            'source_tree': TREE, 'source_sha': SHA, 'image': IMAGE}


class ReleaseTests(unittest.TestCase):
    def test_rejects_wrong_provenance_and_mutable_tags(self):
        for key, value in [('schema', 2), ('environment', 'Production'), ('service', 'Other'),
                           ('source_tree', 'd' * 40), ('source_sha', 'd' * 40),
                           ('image', BASE + ':latest'), ('image', IMAGE.replace('/frontend', '/other')),
                           ('image', IMAGE + '\nimage=untrusted')]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                release.validate({**record(), key: value}, 'Frontend', TREE, BASE, SHA)

    def test_rejects_invalid_record_type(self):
        with self.assertRaises(ValueError):
            release.validate([], 'Frontend', TREE, BASE, SHA)

    def test_record_roundtrip_preserves_the_digest_and_original_build_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            path = directory / 'receipt/release.json'
            output = directory / 'output'
            env = {**os.environ, 'SERVICE_PATH': 'Frontend', 'SOURCE_TREE': TREE,
                   'IMAGE_BASE': BASE, 'IMAGE_SOURCE_SHA': SHA, 'IMAGE': IMAGE,
                   'CI_RUN_ID': '12', 'GITHUB_OUTPUT': str(output)}
            for command in ('write', 'read'):
                result = subprocess.run([sys.executable, str(SCRIPT), command, str(path)],
                                        env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(path.read_text())['image'], IMAGE)
            self.assertEqual(output.read_text(), f'image={IMAGE}\nsource-sha={SHA}\n')
            env['IMAGE_SOURCE_SHA'] = 'd' * 40
            output.unlink()
            result = subprocess.run([sys.executable, str(SCRIPT), 'read', str(path)],
                                    env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists(), 'invalid provenance must never supply a deployment image')


@unittest.skipUnless(BASH and Path(BASH).is_file(), 'Bash required')
class PublishTests(unittest.TestCase):
    def publish(self, directory, revision=SHA):
        script = (ROOT / 'Scripts/publish-service-image.sh').read_text()
        stub = '''docker() {
  printf '%s\\n' "$*" >> "$CALLS"
  if [[ "$1 $2" == 'image inspect' ]]; then
    if [[ "$3" == service-ci:local ]]; then printf '%s' "$REVISION";
    else printf '%s' "$DIGEST"; fi
  fi
}
'''
        return subprocess.run([BASH, '--noprofile', '--norc', '-c', stub + script],
                              cwd=directory, capture_output=True, text=True, env={
                                  **os.environ, 'SERVICE_PATH': 'Frontend', 'SOURCE_SHA': SHA,
                                  'IMAGE_BASE': BASE, 'RUNNER_TEMP': directory.as_posix(),
                                  'GITHUB_OUTPUT': (directory / 'output').as_posix(),
                                  'CALLS': (directory / 'calls').as_posix(),
                                  'REVISION': revision, 'DIGEST': 'service-ci@sha256:' + 'd' * 64 + '\n' + IMAGE,
                              })

    def test_loads_tags_and_pushes_existing_image_without_building(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            result = self.publish(directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = (directory / 'calls').read_text().splitlines()
            self.assertTrue(calls[0].startswith('load --input '))
            self.assertFalse(any(call.startswith(('build ', 'buildx ')) for call in calls))
            self.assertEqual(sum(call.startswith('push ') for call in calls), 2)
            self.assertIn(f'push {BASE}:sha-{SHA}', calls)
            self.assertIn(f'push {BASE}:testing', calls)
            self.assertFalse(any(':latest' in call for call in calls))
            self.assertEqual((directory / 'output').read_text(), f'image={IMAGE}\nsource-sha={SHA}\n')

    def test_wrong_image_revision_stops_before_any_push(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            result = self.publish(directory, revision='d' * 40)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('push ', (directory / 'calls').read_text())
            self.assertFalse((directory / 'output').exists())


if __name__ == '__main__':
    unittest.main()
