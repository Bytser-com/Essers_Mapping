"""Coverage can warn, but scanner/API errors and other failed conditions must block."""

from contextlib import contextmanager, redirect_stdout
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit


SCRIPT = Path(__file__).resolve().parents[1] / 'check-sonar-quality-gate.py'
SPEC = importlib.util.spec_from_file_location('sonar_quality_gate', SCRIPT)
sonar = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sonar)

CONFIG = {'SONAR_HOST_URL': 'https://sonarcloud.io', 'SONAR_PROJECT_KEY': 'project', 'SONAR_TOKEN': 'fake-token'}
COVERAGE = {'metricKey': 'new_coverage', 'status': 'ERROR', 'actualValue': '69.0', 'errorThreshold': '80'}


def gate(*conditions, status='ERROR'):
    return {'analysisId': 'analysis-123', 'projectStatus': {'status': status, 'conditions': list(conditions)}}


def task(status='SUCCESS', **changes):
    return {'task': {'id': 'task-123', 'componentKey': 'project', 'status': status,
                     'analysisId': 'analysis-123', **changes}}


@contextmanager
def workspace(metadata=True):
    previous = Path.cwd()
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, CONFIG, clear=True):
        os.chdir(directory)
        try:
            if metadata:
                Path('.scannerwork').mkdir()
                Path('.scannerwork/report-task.txt').write_text(
                    'serverUrl=https://sonarcloud.io\nprojectKey=project\nceTaskId=task-123\n'
                    'ceTaskUrl=https://untrusted.invalid/api/ce/task?id=task-123\n', encoding='utf-8',
                )
            yield
        finally:
            os.chdir(previous)


class SonarGateTests(unittest.TestCase):
    def evaluate(self, payload):
        output = io.StringIO()
        with redirect_stdout(output):
            result = sonar.check_gate(payload)
        return result, output.getvalue()

    def test_passing_gate_succeeds_without_warnings(self):
        result, output = self.evaluate(gate({**COVERAGE, 'status': 'OK'}, status='OK'))
        self.assertEqual(result, 0)
        self.assertNotIn('::warning::', output)

    def test_only_new_code_coverage_is_advisory(self):
        result, output = self.evaluate(gate(COVERAGE))
        self.assertEqual(result, 0)
        self.assertIn('::warning::', output)
        self.assertIn('69.0%', output)
        self.assertIn('80%', output)
        self.assertIn('SonarQube gate remains failed', output)

    def test_other_conditions_still_block_even_alongside_low_coverage(self):
        for metric in ('new_security_rating', 'new_reliability_rating', 'new_maintainability_rating',
                       'new_duplicated_lines_density', 'new_security_hotspots_reviewed', 'coverage', 'future_metric'):
            with self.subTest(metric=metric):
                result, output = self.evaluate(gate(COVERAGE, {'metricKey': metric, 'status': 'ERROR'}))
                self.assertEqual(result, 1)
                self.assertIn('::error::', output)
                self.assertIn(metric, output)

    def test_unknown_or_inconsistent_results_cannot_pass(self):
        for payload in (gate(status='NONE'), gate(), gate(COVERAGE, status='OK'),
                        gate({'metricKey': 'new_coverage', 'status': 'unexpected'}),
                        gate({'status': 'ERROR'}), gate(None), {'projectStatus': {'status': 'OK', 'conditions': None}}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                sonar.check_gate(payload)

    def test_remote_text_cannot_inject_extra_workflow_commands(self):
        output = io.StringIO()
        with redirect_stdout(output):
            sonar.annotation('error', 'Remote text\n::warning::injected')
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        self.assertIn('%0A', output.getvalue())

    def test_polling_checks_the_exact_analysis_after_processing(self):
        with patch.object(sonar, 'get_json', side_effect=[task('PENDING'), task('IN_PROGRESS'), task(), gate(COVERAGE)]) as fetch, \
                patch.object(sonar.time, 'sleep'):
            actual = sonar.wait_for_gate('https://sonarcloud.io', 'token', 'task-123', 'project')
        self.assertEqual(actual, gate(COVERAGE))
        self.assertEqual(fetch.call_args.args[2:4],
                         ('/api/qualitygates/project_status', {'analysisId': 'analysis-123'}))
        self.assertTrue(all(0 < call.args[4] <= 20 for call in fetch.call_args_list))

    def test_failed_cancelled_or_mismatched_tasks_cannot_pass(self):
        for response in (task('FAILED'), task('CANCELED'), task('UNKNOWN'), task(id='different'),
                         task(componentKey='different'), task(analysisId=None)):
            with self.subTest(response=response), patch.object(sonar, 'get_json', return_value=response), \
                    self.assertRaises(ValueError):
                sonar.wait_for_gate('https://sonarcloud.io', 'token', 'task-123', 'project')

    def test_pending_analysis_times_out(self):
        with patch.object(sonar.time, 'monotonic', side_effect=[0, 0, 301, 301]), \
                patch.object(sonar.time, 'sleep'), patch.object(sonar, 'get_json', return_value=task('PENDING')), \
                self.assertRaises(TimeoutError):
            sonar.wait_for_gate('https://sonarcloud.io', 'token', 'task-123', 'project')

    def test_report_selects_the_matching_analysis_instead_of_the_latest(self):
        date = '2026-11-27T14:02:38+0000'
        history = {'analyses': [
            {'key': 'newer-analysis', 'date': '2026-11-27T15:00:00+0000'},
            {'key': 'analysis-123', 'date': date},
        ]}
        with patch.object(sonar, 'get_json', return_value=history) as fetch:
            url = sonar.analysis_report_url('https://sonar-essers.shystack.com', 'fake-token',
                                            'project & other', 'analysis-123')
        self.assertEqual(urlsplit(url).path, '/project/activity')
        self.assertEqual(parse_qs(urlsplit(url).query), {'id': ['project & other'], 'selected_date': [date]})
        self.assertEqual(fetch.call_args.args[2:4],
                         ('/api/project_analyses/search', {'project': 'project & other', 'ps': 100}))
        self.assertNotIn('fake-token', url)

    def test_unavailable_or_invalid_history_links_to_exact_gate_json(self):
        cases = [{'analyses': []}, {'analyses': [{'key': 'other', 'date': '2026-11-27'}]},
                 {'analyses': [{'key': 'analysis-123', 'date': 'invalid'}]},
                 {'analyses': None}, {}, URLError('offline'),
                 HTTPError('https://sonarcloud.io', 403, 'Forbidden', {}, None)]
        for response in cases:
            with self.subTest(response=response):
                options = {'side_effect': response} if isinstance(response, Exception) else {'return_value': response}
                with patch.object(sonar, 'get_json', **options):
                    url = sonar.analysis_report_url('https://sonarcloud.io', 'fake-token', 'project', 'analysis-123')
                self.assertEqual(url, 'https://sonarcloud.io/api/qualitygates/project_status?analysisId=analysis-123')

    def test_errors_and_warnings_link_to_the_report_and_write_summary_before_failure(self):
        for condition, expected in ((COVERAGE, 0), ({'metricKey': 'new_violations', 'status': 'ERROR'}, 1)):
            with self.subTest(metric=condition['metricKey']), workspace(), \
                    patch.object(sonar, 'wait_for_gate', return_value=gate(condition)), \
                    patch.object(sonar, 'get_json', return_value={'analyses': [
                        {'key': 'analysis-123', 'date': '2026-11-27T14:02:38+0000'}
                    ]}):
                summary = Path('summary.md')
                summary.write_text('Existing summary\n', encoding='utf-8')
                os.environ['GITHUB_STEP_SUMMARY'] = str(summary)
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(sonar.main(), expected)
                result = output.getvalue()
                annotation = next(line for line in result.splitlines() if line.startswith('::'))
                self.assertIn('https://sonarcloud.io/project/activity?', annotation)
                self.assertIn('selected_date=', annotation)
                self.assertNotIn('fake-token', result + summary.read_text())
                saved = summary.read_text()
                self.assertTrue(saved.startswith('Existing summary\n'))
                self.assertIn('[This analysis](https://sonarcloud.io/project/activity?', saved)
                self.assertIn('/api/qualitygates/project_status?analysisId=analysis-123', saved)
                self.assertIn('latest analysis', saved)

    def test_history_lookup_failure_does_not_change_the_gate_policy(self):
        with workspace(), patch.object(sonar, 'wait_for_gate', return_value=gate(COVERAGE)), \
                patch.object(sonar, 'get_json', side_effect=URLError('history unavailable')), \
                redirect_stdout(io.StringIO()) as output:
            self.assertEqual(sonar.main(), 0)
            self.assertIn('project_status?analysisId=analysis-123', output.getvalue())

    def test_authenticated_request_has_a_timeout_and_encodes_parameters(self):
        response = io.BytesIO(b'{"task": {}}')
        opener = Mock()
        opener.open.return_value = response
        with patch.object(sonar, 'build_opener', return_value=opener):
            sonar.get_json('https://sonarcloud.io', 'token', '/api/ce/task', {'id': 'a&other=b'}, 12)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), 'GET')
        self.assertEqual(request.get_header('Authorization'), 'Bearer token')
        self.assertTrue(request.get_header('User-agent').startswith('Essers-Mapping-Sonar-Quality-Gate/'))
        self.assertEqual(request.full_url, 'https://sonarcloud.io/api/ce/task?id=a%26other%3Db')
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 12)

    def test_token_is_not_forwarded_on_redirects(self):
        self.assertIsNone(sonar.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.invalid'))

    def test_completed_gate_is_saved_without_trusting_metadata_urls(self):
        with workspace(), patch.object(sonar, 'wait_for_gate', return_value=gate(COVERAGE)) as wait, \
                patch.object(sonar, 'analysis_report_url', return_value='https://sonarcloud.io/project/activity?id=project'), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(sonar.main(), 0)
            wait.assert_called_once_with('https://sonarcloud.io', 'fake-token', 'task-123', 'project')
            self.assertEqual(json.loads(Path('test-results/sonarqube-quality-gate.json').read_text()), gate(COVERAGE))

    def test_self_hosted_scan_uses_the_configured_server(self):
        server = 'https://sonar-essers.shystack.com'
        with workspace(), patch.dict(os.environ, {'SONAR_HOST_URL': server}), \
                patch.object(sonar, 'wait_for_gate', return_value=gate(status='OK')) as wait, \
                patch.object(sonar, 'analysis_report_url', return_value=server + '/project/activity?id=project'), \
                redirect_stdout(io.StringIO()):
            metadata = Path('.scannerwork/report-task.txt')
            metadata.write_text(metadata.read_text().replace('https://sonarcloud.io', server), encoding='utf-8')
            self.assertEqual(sonar.main(), 0)
            wait.assert_called_once_with(server, 'fake-token', 'task-123', 'project')

    def test_missing_or_mismatched_metadata_cannot_pass(self):
        with workspace(metadata=False), patch.object(sonar, 'wait_for_gate') as wait, redirect_stdout(io.StringIO()):
            self.assertEqual(sonar.main(), 1)
            wait.assert_not_called()
        with workspace(), patch.object(sonar, 'wait_for_gate') as wait, redirect_stdout(io.StringIO()):
            os.environ['SONAR_PROJECT_KEY'] = 'another-project'
            self.assertEqual(sonar.main(), 1)
            wait.assert_not_called()

    def test_missing_configuration_or_insecure_server_cannot_pass(self):
        for changes in ({'SONAR_TOKEN': ''}, {'SONAR_PROJECT_KEY': ''}, {'SONAR_HOST_URL': 'http://sonarcloud.io'}):
            with self.subTest(changes=changes), workspace(), patch.dict(os.environ, changes), \
                    patch.object(sonar, 'wait_for_gate') as wait, redirect_stdout(io.StringIO()):
                self.assertEqual(sonar.main(), 1)
                wait.assert_not_called()

    def test_missing_server_does_not_fall_back_to_sonarcloud(self):
        output = io.StringIO()
        with workspace(), patch.object(sonar, 'wait_for_gate') as wait, redirect_stdout(output):
            del os.environ['SONAR_HOST_URL']
            self.assertEqual(sonar.main(), 1)
            self.assertIn('SONAR_HOST_URL', output.getvalue())
            wait.assert_not_called()

    def test_api_authentication_network_timeout_and_invalid_json_errors_block(self):
        errors = (HTTPError('https://sonarcloud.io', 401, 'Unauthorized', {}, None),
                  URLError('connection unavailable'), TimeoutError('processing timed out'),
                  json.JSONDecodeError('invalid response', '', 0))
        for error in errors:
            output = io.StringIO()
            with self.subTest(error=type(error).__name__), workspace(), \
                    patch.object(sonar, 'wait_for_gate', side_effect=error), redirect_stdout(output):
                self.assertEqual(sonar.main(), 1)
                self.assertIn('::error::', output.getvalue())
                self.assertNotIn(CONFIG['SONAR_TOKEN'], output.getvalue())

    def test_malformed_coverage_cannot_be_treated_as_a_warning(self):
        payload = copy.deepcopy(gate(COVERAGE))
        del payload['projectStatus']['conditions'][0]['actualValue']
        with workspace(), patch.object(sonar, 'wait_for_gate', return_value=payload), \
                patch.object(sonar, 'analysis_report_url', return_value='https://sonarcloud.io/report'), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(sonar.main(), 1)
        for value in (None, 'NaN', 'inf', '-1', '101', 'not a percentage'):
            with self.subTest(value=value), workspace(), \
                    patch.object(sonar, 'wait_for_gate', return_value=gate({**COVERAGE, 'actualValue': value})), \
                    patch.object(sonar, 'analysis_report_url', return_value='https://sonarcloud.io/report'), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(sonar.main(), 1)

    def test_cloudflare_block_is_identified_without_exposing_response_details(self):
        payload = {'cloudflare_error': True, 'error_code': 1010,
                   'detail': 'Untrusted response containing ' + CONFIG['SONAR_TOKEN']}
        error = HTTPError('https://sonar-essers.shystack.com/api/ce/task', 403, 'Forbidden',
                          {}, io.BytesIO(json.dumps(payload).encode()))
        output = io.StringIO()
        with workspace(), patch.object(sonar, 'wait_for_gate', side_effect=error), redirect_stdout(output):
            self.assertEqual(sonar.main(), 1)
        self.assertIn('Cloudflare rejected the API client (error 1010)', output.getvalue())
        self.assertNotIn('Check token permissions', output.getvalue())
        self.assertNotIn(CONFIG['SONAR_TOKEN'], output.getvalue())

    def test_non_json_forbidden_response_remains_a_blocking_http_error(self):
        error = HTTPError('https://sonar-essers.shystack.com/api/ce/task', 403, 'Forbidden',
                          {}, io.BytesIO(b'<html>Forbidden</html>'))
        output = io.StringIO()
        with workspace(), patch.object(sonar, 'wait_for_gate', side_effect=error), redirect_stdout(output):
            self.assertEqual(sonar.main(), 1)
        self.assertIn('HTTP 403', output.getvalue())
        self.assertNotIn('<html>', output.getvalue())

    def test_workflow_keeps_scan_failures_blocking_and_checks_gate_separately(self):
        workflow = (SCRIPT.parent.parent / '.github/workflows/sonarqube.yml').read_text(encoding='utf-8')
        scan = workflow.split('- name: Run SonarQube scan\n', 1)[1].split('# A failed quality gate', 1)[0]
        self.assertIn('-Dsonar.qualitygate.wait=false', scan)
        self.assertIn('run: python Scripts/check-sonar-quality-gate.py', scan)
        self.assertNotIn('continue-on-error:', scan)


if __name__ == '__main__':
    unittest.main()
