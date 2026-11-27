// GitHub is mocked; exercise selection without publishing or deploying anything.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const selectRelease = require('../select-service-release.cjs');
const sha = 'a'.repeat(40);
const testedSha = 'b'.repeat(40);
const tree = 'c'.repeat(40);
const releaseName = `tested-frontend-${tree}`;
const repository = { full_name: 'Bytser-com/Essers_Mapping' };

async function check(options = {}) {
  const branch = options.branch || 'Testing';
  const run = {
    id: 12, workflow_id: 7, event: options.event || 'push', status: 'in_progress',
    conclusion: null, head_sha: sha, head_branch: branch, head_repository: repository,
    ...options.run,
  };
  const testedRun = {
    id: 10, workflow_id: 7, event: 'push', conclusion: 'success', status: 'completed',
    head_sha: testedSha, head_branch: 'Testing', head_repository: repository,
    ...options.testedRun,
  };
  const outputs = {};
  const context = {
    repo: { owner: 'Bytser-com', repo: 'Essers_Mapping' }, runId: 12,
    ref: `refs/heads/${branch}`, sha: options.contextSha || sha,
    eventName: options.event || 'push',
  };
  const images = options.images || [{ id: 20, name: 'Frontend-image', expired: false }];
  const receipts = options.receipts || [{
    id: 30, name: releaseName, expired: false, workflow_run: { id: 10, head_branch: 'Testing' },
  }];
  const github = { rest: {
    git: {
      getRef: async () => ({ data: { object: { sha: options.currentSha || sha } } }),
      getTree: async ({ tree_sha }) => ({ data: { tree: [{
        path: options.missingService ? 'Other' : 'Frontend', type: 'tree',
        sha: tree_sha === testedSha ? (options.testedTree || tree) : tree,
      }] } }),
    },
    actions: {
      getWorkflow: async ({ workflow_id }) => ({ data: { id: workflow_id.endsWith('-cd.yml') ? 8 : 7 } }),
      getWorkflowRun: async ({ run_id }) => ({ data: run_id === 12 ? run : testedRun }),
      listWorkflowRuns: async () => ({ data: { workflow_runs: options.ciRuns || [] } }),
      listWorkflowRunArtifacts: 'images', listArtifactsForRepo: 'receipts',
    },
  }, paginate: async endpoint => endpoint === 'images' ? images : receipts };
  const summary = { addRaw() { return this; }, async write() {} };
  await selectRelease({ github, context, core: {
    setOutput: (key, value) => { outputs[key] = value; }, summary,
  }, env: { CI_WORKFLOW: 'frontend-ci.yml', SERVICE_PATH: 'Frontend', IMAGE_NAME: 'frontend' } });
  return outputs;
}

test('Testing publishes the exact container artifact after inline CI', async () => {
  for (const event of ['push', 'workflow_dispatch']) {
    const result = await check({ event });
    assert.equal(result.enabled, 'true');
    assert.equal(result['image-artifact-id'], '20');
    assert.equal(result.environment, 'Testing');
    assert.equal(result.namespace, 'essers-mapping-testing');
    assert.equal(result.image, 'ghcr.io/bytser-com/essers_mapping/frontend');
  }
});

test('main reuses a successful Testing release despite different merge commit SHAs', async () => {
  const result = await check({ branch: 'main' });
  assert.equal(result.sha, sha);
  assert.equal(result['receipt-sha'], testedSha);
  assert.equal(result['receipt-run-id'], '10');
  assert.equal(result['receipt-id'], '30');
  assert.equal(result['source-tree'], tree);
  assert.equal(result.environment, 'Production');
  assert.equal(result.namespace, 'essers-mapping-production');
  assert.equal(result['image-artifact-id'], undefined);
});

test('manual recovery selects successful CI for the current revision', async () => {
  const result = await check({ event: 'workflow_dispatch', run: { workflow_id: 8 }, ciRuns: [{
    id: 9, workflow_id: 7, event: 'workflow_dispatch', conclusion: 'success',
    head_sha: sha, head_branch: 'Testing', head_repository: repository,
  }] });
  assert.equal(result['run-id'], '9');
});

test('a successful manual Testing deployment is also a trusted release', async () => {
  const result = await check({ branch: 'main', testedRun: { workflow_id: 8, event: 'workflow_dispatch' } });
  assert.equal(result.enabled, 'true');
});

test('stale triggering runs skip deployment', async () => {
  assert.equal((await check({ currentSha: 'd'.repeat(40) })).enabled, 'false');
  assert.equal((await check({ contextSha: 'd'.repeat(40) })).enabled, 'false');
});

for (const [name, options] of Object.entries({
  'non-release branch': { branch: 'Development' },
  'PR event': { event: 'pull_request' },
  'wrong CI workflow': { run: { workflow_id: 99 } },
  'fork CI': { run: { head_repository: { full_name: 'external/fork' } } },
  'mismatched branch': { run: { head_branch: 'main' } },
  'failed CI': { run: { status: 'completed', conclusion: 'failure' } },
  'cancelled CI': { run: { status: 'completed', conclusion: 'cancelled' } },
  'missing source directory': { missingService: true },
  'missing image': { images: [] },
  'expired image': { images: [{ id: 20, name: 'Frontend-image', expired: true }] },
  'wrong image artifact': { images: [{ id: 20, name: 'Other-image' }] },
  'manual run without CI': { event: 'workflow_dispatch', run: { workflow_id: 8 } },
  'missing release': { branch: 'main', receipts: [] },
  'expired release': { branch: 'main', receipts: [{ id: 30, name: releaseName, expired: true }] },
  'other service release': { branch: 'main', receipts: [{ id: 30, name: 'tested-other' }] },
  'different service source': { branch: 'main', testedTree: 'd'.repeat(40) },
  'failed Testing deployment': { branch: 'main', testedRun: { conclusion: 'failure' } },
  'PR Testing receipt': { branch: 'main', testedRun: { event: 'pull_request' } },
  'fork Testing receipt': { branch: 'main', testedRun: { head_repository: { full_name: 'external/fork' } } },
  'unknown release workflow': { branch: 'main', testedRun: { workflow_id: 99 } },
  'CD push rather than manual receipt': { branch: 'main', testedRun: { workflow_id: 8, event: 'push' } },
  'release not deployed to Testing': { branch: 'main', testedRun: { head_branch: 'main' } },
})) test(`refuses ${name}`, async () => { await assert.rejects(check(options)); });

test('ignores an untrusted newer artifact and finds a valid Testing receipt', async () => {
  const result = await check({ branch: 'main', receipts: [
    { id: 31, name: releaseName, workflow_run: { id: 11, head_branch: 'feature' } },
    { id: 30, name: releaseName, workflow_run: { id: 10, head_branch: 'Testing' } },
  ] });
  assert.equal(result['receipt-id'], '30');
});
