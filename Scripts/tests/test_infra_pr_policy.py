"""Exercise the real YAML guards for accidental PRs and normal releases."""
import ast
from pathlib import Path
import re
import unittest

from test_ci_check_independence import check_steps


WORKFLOWS = Path(__file__).resolve().parents[2] / '.github/workflows'
INFRA = (WORKFLOWS / 'infra-pipeline.yml').read_text(encoding='utf-8')


def evaluate(expression, *, event='pull_request', head='Feature/example', base='main',
             branch='main', number=138):
    """Evaluate the small expression subset used in these guards, without GitHub."""
    values = {'event_name': event, 'head_ref': head, 'base_ref': base,
              'ref_name': branch, 'event.pull_request.number': number}
    expression = expression.strip().removeprefix('${{').removesuffix('}}').strip()
    expression = re.sub(r'github\.([\w.]+)', lambda m: repr(values[m[1]]), expression)
    expression = expression.replace('&&', ' and ').replace('||', ' or ')
    tree = ast.parse(expression, mode='eval')
    allowed = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.Compare, ast.Eq,
               ast.NotEq, ast.Constant, ast.Call, ast.Name, ast.Load)
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise ValueError('Unsupported workflow expression')
        if isinstance(node, ast.Name) and node.id != 'format':
            raise ValueError('Unsupported workflow function')
    return eval(compile(tree, '<workflow guard>', 'eval'),
                {'__builtins__': {}, 'format': lambda template, *args: template.format(*args)})


def terraform_allowed(**context):
    job = INFRA.split('\n  terraform:\n', 1)[1].split('\n  ansible:\n', 1)[0]
    guard = re.search(r'^    if: >-\n((?:      .+\n)+)', job, re.MULTILINE)
    if not guard:
        raise AssertionError('Terraform requires a guard before calling the reusable workflow')
    return evaluate(' '.join(line.strip() for line in guard[1].splitlines()), **context)


def branch_policy_fails(**context):
    return any(evaluate(step['if'], **context) for step in check_steps('pr-branch-policy'))


def concurrency(field, **context):
    block = INFRA.split('\nconcurrency:\n', 1)[1].split('\npermissions:', 1)[0]
    expression = re.search(r'^  ' + field + r': (.+)$', block, re.MULTILINE)[1]
    if expression == '>-':
        expression = ' '.join(line.strip() for line in re.search(
            r'^  ' + field + r': >-\n((?:    .+\n)+)', block, re.MULTILINE)[1].splitlines())
    return evaluate(expression, **context)


class InfrastructurePrPolicyTests(unittest.TestCase):
    def test_accidental_feature_prs_never_request_terraform(self):
        for head in ['Feature/249-NavigatePromises', 'Feature/250-NavigateApprovalError']:
            for base in ['main', 'Testing']:
                with self.subTest(head=head, base=base):
                    self.assertFalse(terraform_allowed(head=head, base=base))
                    self.assertTrue(branch_policy_fails(head=head, base=base))

    def test_releases_follow_development_testing_main(self):
        for head, base in [('Development', 'Testing'), ('Testing', 'main')]:
            with self.subTest(head=head, base=base):
                self.assertTrue(terraform_allowed(head=head, base=base))
                self.assertFalse(branch_policy_fails(head=head, base=base))

    def test_development_cannot_skip_testing(self):
        self.assertFalse(terraform_allowed(head='Development', base='main'))
        self.assertTrue(branch_policy_fails(head='Development', base='main'))

    def test_correcting_feature_pr_to_development_clears_the_policy_error(self):
        self.assertTrue(branch_policy_fails(base='main'))
        self.assertFalse(branch_policy_fails(base='Development'))
        policy = (WORKFLOWS / 'pr-branch-policy.yml').read_text(encoding='utf-8')
        self.assertIn('edited', policy.split('\npermissions:', 1)[0])

    def test_push_and_manual_infrastructure_runs_remain_available(self):
        for event in ['push', 'workflow_dispatch']:
            for branch in ['Testing', 'main']:
                with self.subTest(event=event, branch=branch):
                    self.assertTrue(terraform_allowed(event=event, head='', base='', branch=branch))

    def test_pr_validation_never_holds_a_deployment_lock(self):
        for base in ['Testing', 'main']:
            with self.subTest(base=base):
                self.assertEqual(concurrency('group', base=base, number=138), 'infra-pr-138')
                self.assertEqual(concurrency('group', base=base, number=139), 'infra-pr-139')
                self.assertTrue(concurrency('cancel-in-progress', base=base))

    def test_live_deployments_still_serialize_without_cancelling_each_other(self):
        for event in ['push', 'workflow_dispatch']:
            for branch, environment in [('Testing', 'testing'), ('main', 'production')]:
                with self.subTest(event=event, branch=branch):
                    self.assertEqual(concurrency('group', event=event, branch=branch), 'cluster-write-' + environment)
                    self.assertFalse(concurrency('cancel-in-progress', event=event, branch=branch))


if __name__ == '__main__':
    unittest.main()
