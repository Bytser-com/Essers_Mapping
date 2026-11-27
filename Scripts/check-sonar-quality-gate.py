#!/usr/bin/env python3
"""Check this scan's gate: new-code coverage warns; other failures block CI."""

import json
import os
from datetime import datetime
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


USER_AGENT = 'Essers-Mapping-Sonar-Quality-Gate/1.0'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        # Never forward the Sonar token to a redirect destination.
        return None


def annotation(level, message):
    escaped = str(message).replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
    print(f'::{level}::{escaped}')


def get_json(server, token, endpoint, parameters, timeout):
    request = Request(
        f'{server}{endpoint}?{urlencode(parameters)}',
        headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json',
                 'User-Agent': USER_AGENT},
    )
    with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError('Sonar returned an invalid JSON response.')
    return payload


def wait_for_gate(server, token, task_id, project_key, timeout=300):
    """Wait for the uploaded task, then fetch its exact analysis, never the latest one."""
    deadline = time.monotonic() + timeout

    def fetch(endpoint, parameters):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Sonar quality-gate processing timed out.')
        return get_json(server, token, endpoint, parameters, min(20, remaining))

    while True:
        task = fetch('/api/ce/task', {'id': task_id})['task']
        if task['id'] != task_id or task['componentKey'] != project_key:
            raise ValueError('Sonar returned a task for a different scan or project.')
        if task['status'] == 'SUCCESS':
            analysis_id = task.get('analysisId')
            if not isinstance(analysis_id, str) or not analysis_id:
                raise ValueError('Completed Sonar task has no analysis ID.')
            payload = fetch('/api/qualitygates/project_status', {'analysisId': analysis_id})
            return {**payload, 'analysisId': analysis_id}
        if task['status'] not in ('PENDING', 'IN_PROGRESS'):
            raise ValueError(f"Sonar processing did not succeed: {task['status']}.")
        time.sleep(max(0, min(5, deadline - time.monotonic())))


def analysis_report_url(server, token, project, analysis_id):
    """Select this analysis in Activity; its exact gate JSON is a safe fallback."""
    exact_gate = f'{server}/api/qualitygates/project_status?{urlencode({"analysisId": analysis_id})}'
    try:
        history = get_json(server, token, '/api/project_analyses/search', {'project': project, 'ps': 100}, 15)
        for analysis in history['analyses']:
            if analysis['key'] == analysis_id:
                # Activity selects an analysis by its timestamp, not by an analysisId parameter.
                date = analysis['date']
                datetime.fromisoformat(date)
                return f'{server}/project/activity?{urlencode({"id": project, "selected_date": date})}'
    except (OSError, URLError, ValueError, KeyError, TypeError) as error:
        if isinstance(error, HTTPError):
            error.close()
        # Report navigation must not change the quality-gate result.
    return exact_gate


def publish_report_links(server, project, analysis_id, report_url):
    dashboard = f'{server}/dashboard?{urlencode({"id": project})}'
    exact_gate = f'{server}/api/qualitygates/project_status?{urlencode({"analysisId": analysis_id})}'
    print(f'SonarQube report for this analysis: {report_url}')
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with Path(summary).open('a', encoding='utf-8') as output:
            output.write('\n### SonarQube report\n\n'
                         f'- [This analysis]({report_url})\n'
                         f'- [Exact quality-gate result (JSON)]({exact_gate})\n'
                         f'- [Project dashboard and issues (latest analysis)]({dashboard})\n')


def check_gate(payload, report_url=None):
    gate = payload['projectStatus']
    conditions = gate['conditions']
    if not isinstance(conditions, list) or any(
        not isinstance(item, dict) or item.get('status') not in ('OK', 'ERROR', 'NO_VALUE')
        or not isinstance(item.get('metricKey'), str) for item in conditions
    ):
        raise ValueError('Sonar returned invalid quality-gate conditions.')
    failed = [item for item in conditions if item['status'] == 'ERROR']
    if gate['status'] == 'OK' and not failed:
        print('SonarQube quality gate passed.')
        return 0
    if gate['status'] != 'ERROR' or not failed:
        raise ValueError('Sonar returned an unknown or inconsistent quality-gate result.')

    blocking = False
    for condition in failed:
        metric = condition['metricKey']
        if metric == 'new_coverage':
            if any(not 0 <= float(condition[key]) <= 100 for key in ('actualValue', 'errorThreshold')):
                raise ValueError('Sonar returned invalid coverage percentages.')
            annotation('warning',
                       f"Sonar new-code coverage: {condition['actualValue']}%; "
                       f"required: {condition['errorThreshold']}%. Coverage is advisory in GitHub Actions; "
                       'the SonarQube gate remains failed.'
                       + (f' See this analysis: {report_url}' if report_url else ''))
        else:
            blocking = True
            report = f'See this analysis: {report_url}' if report_url else 'See the SonarQube report.'
            annotation('error', f'Sonar quality gate failed: {metric}. {report}')
    return 1 if blocking else 0


def main():
    try:
        server = os.environ.get('SONAR_HOST_URL', '').strip().rstrip('/')
        parsed = urlsplit(server)
        if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.query or parsed.fragment:
            raise ValueError('SONAR_HOST_URL must be an HTTPS URL without credentials.')
        token = os.environ.get('SONAR_TOKEN', '').strip()
        project = os.environ.get('SONAR_PROJECT_KEY', '').strip()
        if not token or not project:
            raise ValueError('SONAR_TOKEN and SONAR_PROJECT_KEY are required.')

        metadata = dict(
            line.split('=', 1) for line in Path('.scannerwork/report-task.txt').read_text(encoding='utf-8').splitlines()
            if '=' in line
        )
        if metadata.get('projectKey') != project or metadata.get('serverUrl', '').rstrip('/') != server:
            raise ValueError('Scanner metadata does not match the configured Sonar project/server.')
        task_id = metadata.get('ceTaskId')
        if not task_id:
            raise ValueError('Scanner metadata is missing ceTaskId.')
        payload = wait_for_gate(server, token, task_id, project)
        analysis_id = payload['analysisId']
        report_url = analysis_report_url(server, token, project, analysis_id)
        publish_report_links(server, project, analysis_id, report_url)
        report = Path('test-results/sonarqube-quality-gate.json')
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(payload, indent=2), encoding='utf-8')
        return check_gate(payload, report_url)
    except HTTPError as error:
        try:
            payload = json.loads(error.read(8192)) if error.fp is not None else {}
        except (OSError, ValueError):
            payload = {}
        finally:
            error.close()
        if isinstance(payload, dict) and payload.get('cloudflare_error') is True:
            code = payload.get('error_code')
            detail = f' (error {code})' if isinstance(code, int) else ''
            annotation('error', f'Sonar quality-gate request failed: HTTP {error.code}. '
                       f'Cloudflare rejected the API client{detail}. Check the client User-Agent and Cloudflare rules.')
        else:
            annotation('error', f'Sonar quality-gate request failed: HTTP {error.code}. '
                       'Check token permissions and upstream proxy rules.')
    except (OSError, URLError, ValueError, KeyError, TypeError) as error:
        annotation('error', f'Cannot verify Sonar quality gate: {error}')
    return 1


if __name__ == '__main__':
    sys.exit(main())
