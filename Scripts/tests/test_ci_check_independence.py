"""Exercise workflow conditions with failing prerequisites; no service is deployed."""

import ast
from pathlib import Path
import re
import unittest


WORKFLOWS = Path(__file__).resolve().parents[2] / '.github' / 'workflows'
TESTS = 'Unit, integration and functional tests with coverage'
BUILD = 'Build container for validation'
HEALTH = 'Validate container startup and health'


def check_steps(workflow):
    """Read names and scalar conditions from the checks job, without a YAML dependency."""
    text = (WORKFLOWS / f'{workflow}.yml').read_text(encoding='utf-8')
    job = re.split(r'\n  [\w-]+:\n', text.split('\n  checks:\n', 1)[1])[0]
    steps = []
    for block in job.split('      - name: ')[1:]:
        step = {'name': block.splitlines()[0].strip()}
        step.update(re.findall(r'^        (id|if|continue-on-error): (.+)$', block, re.MULTILINE))
        steps.append(step)
    return steps


def condition(expression, outcomes, *, successful, cancelled, enabled, dockerfile):
    """Evaluate the scalar guard subset used here, including implicit success()."""
    status = {'success': successful and not cancelled, 'failure': not successful and not cancelled,
              'cancelled': cancelled, 'always': True}
    if not re.search(r'\b(success|failure|cancelled|always)\(\)', expression):
        if not successful or cancelled:
            return False
    expression = expression.removeprefix('${{').removesuffix('}}').strip()
    expression = re.sub(r'\b(success|failure|cancelled|always)\(\)',
                        lambda match: repr(status[match[1]]), expression)
    expression = re.sub(r'steps\.([\w-]+)\.outcome',
                        lambda match: repr(outcomes.get(match[1], 'skipped')), expression)
    expression = expression.replace('steps.setup.outputs.enabled', repr(str(enabled).lower()))
    expression = expression.replace("hashFiles(format('{0}/Dockerfile', inputs.service-path))",
                                    repr('hash' if dockerfile else ''))
    expression = re.sub(r'!(?!=)', ' not ', expression).replace('&&', ' and ').replace('||', ' or ')
    tree = ast.parse(expression.strip(), mode='eval')
    allowed = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not,
               ast.Compare, ast.Eq, ast.NotEq, ast.Constant)
    if any(not isinstance(node, allowed) for node in ast.walk(tree)):
        raise ValueError(f'Unsupported guard: {expression}')
    return bool(eval(compile(tree, '<workflow condition>', 'eval'), {'__builtins__': {}}))


def simulate(workflow, failure=None, *, enabled=True, dockerfile=True, cancel_after=None):
    outcomes, results = {}, {}
    failed = cancelled = False
    for step in check_steps(workflow):
        should_run = condition(step.get('if', 'success()'), outcomes,
                               successful=not failed, cancelled=cancelled,
                               enabled=enabled, dockerfile=dockerfile)
        result = ('failure' if step['name'] == failure else 'success') if should_run else 'skipped'
        results[step['name']] = result
        if 'id' in step:
            outcomes[step['id']] = result
        if result == 'failure' and step.get('continue-on-error') != 'true':
            failed = True
        if step['name'] == cancel_after:
            cancelled = True
    return results, failed


class IndependentCiChecksTests(unittest.TestCase):
    def test_failures_do_not_skip_independent_checks_or_turn_ci_green(self):
        cases = [
            ('python-service-ci', 'Lint Python', [TESTS, 'Audit installed dependencies', BUILD, HEALTH]),
            ('python-service-ci', TESTS, ['Audit installed dependencies', BUILD, HEALTH]),
            ('python-service-ci', 'Audit installed dependencies', [BUILD, HEALTH]),
            ('python-service-ci', 'Setup service and dependencies', [BUILD, HEALTH]),
            ('frontend-ci', 'Lint', ['Check TypeScript types', TESTS, 'Build production frontend',
                                     'Browser end-to-end tests', BUILD]),
            ('frontend-ci', TESTS, ['Build production frontend', 'Browser end-to-end tests', BUILD]),
            ('frontend-ci', 'Browser end-to-end tests', [BUILD, HEALTH]),
            ('frontend-ci', HEALTH, ['Audit locked dependencies including development tools',
                                     'Upload production bundle']),
            ('frontend-ci', 'Install locked dependencies',
             ['Audit locked dependencies including development tools']),
            ('java-service-ci', TESTS + ' and packaging', ['Audit resolved dependencies']),
            ('java-service-ci', 'Audit resolved dependencies', [BUILD, HEALTH, 'Upload application JAR']),
            ('java-service-ci', HEALTH, ['Upload application JAR']),
            ('pipeline-validation', 'Validate workflow syntax and expressions',
             ['Test pipeline helpers and Sonar gate policy', 'Test trusted CI revision selection',
              'Check container smoke script syntax', 'Check Sonar GPG wrapper syntax']),
            ('pipeline-validation', 'Setup Node.js',
             ['Validate workflow syntax and expressions', 'Test pipeline helpers and Sonar gate policy']),
        ]
        for workflow, failure, expected in cases:
            with self.subTest(workflow=workflow, failure=failure):
                results, failed = simulate(workflow, failure)
                self.assertEqual(results[failure], 'failure')
                self.assertTrue(failed, 'CI must remain failed so CD cannot start')
                for name in expected:
                    self.assertEqual(results[name], 'success', name)

    def test_failed_prerequisites_skip_dependent_checks(self):
        cases = [
            ('python-service-ci', 'Setup service and dependencies', [TESTS, 'Lint Python',
                                                                    'Audit installed dependencies']),
            ('python-service-ci', BUILD, [HEALTH]),
            ('python-service-ci', 'Setup Docker Buildx', [BUILD, HEALTH]),
            ('frontend-ci', 'Build production frontend', ['Browser end-to-end tests', BUILD, HEALTH,
                                                         'Upload production bundle']),
            ('frontend-ci', BUILD, [HEALTH]),
            ('java-service-ci', TESTS + ' and packaging', [BUILD, HEALTH, 'Upload application JAR']),
            ('java-service-ci', 'Export resolved dependencies including test scope',
             ['Convert the Maven inventory for OSV', 'Audit resolved dependencies']),
            ('pipeline-validation', 'Verify the actionlint download',
             ['Extract actionlint', 'Validate workflow syntax and expressions']),
        ]
        for workflow, failure, expected in cases:
            with self.subTest(workflow=workflow, failure=failure):
                results, failed = simulate(workflow, failure)
                self.assertTrue(failed)
                for name in expected:
                    self.assertEqual(results[name], 'skipped', name)

    def test_cancellation_stops_new_checks_but_preserves_reports(self):
        for workflow in ['python-service-ci', 'java-service-ci', 'frontend-ci', 'pipeline-validation']:
            with self.subTest(workflow=workflow):
                results, _ = simulate(workflow, cancel_after='Checkout repository')
                for name, result in results.items():
                    if name != 'Checkout repository' and not name.startswith('Upload test'):
                        self.assertEqual(result, 'skipped', name)

    def test_placeholder_python_service_does_not_claim_tests_passed(self):
        results, failed = simulate('python-service-ci', enabled=False, dockerfile=False)
        self.assertFalse(failed)
        for name, result in results.items():
            if name not in ['Checkout repository', 'Setup service and dependencies']:
                self.assertEqual(result, 'skipped', name)


if __name__ == '__main__':
    unittest.main()
