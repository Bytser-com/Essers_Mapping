"""Verify that the local scanner wrapper cannot publish to the shared server."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'sonar-local.ps1'
POWERSHELL = shutil.which('pwsh')


@unittest.skipUnless(POWERSHELL, 'PowerShell required')
class LocalSonarTests(unittest.TestCase):
    def test_only_loopback_reaches_scanner_and_exit_status_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            stub = Path(directory) / 'scanner.ps1'
            capture = Path(directory) / 'arguments.txt'
            stub.write_text('[IO.File]::WriteAllLines($env:CAPTURE, [string[]]$args)\nexit 3\n', encoding='utf-8')
            cases = [('https://sonar-essers.shystack.com', 'dummy-token', False),
                     ('http://127.0.0.1:9001', '', False),
                     ('http://127.0.0.1:9001', 'dummy-token', True)]
            for server, token, allowed in cases:
                with self.subTest(server=server, token_present=bool(token)):
                    result = subprocess.run(
                        [POWERSHELL, '-NoProfile', '-File', str(SCRIPT), '-ScannerPath', str(stub), '-ServerUrl', server],
                        env={**os.environ, 'SONAR_TOKEN': token, 'CAPTURE': str(capture)},
                        capture_output=True, text=True,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(capture.exists(), allowed)
                    if allowed:
                        self.assertEqual(result.returncode, 3)
                        arguments = capture.read_text(encoding='utf-8-sig')
                        self.assertIn('-Dsonar.host.url=http://127.0.0.1:9001', arguments)
                        self.assertIn('-Dsonar.projectKey=Essers_Mapping_Local', arguments)
                        self.assertIn('-Dsonar.qualitygate.wait=true', arguments)
                        self.assertNotIn(token, arguments)


if __name__ == '__main__':
    unittest.main()
