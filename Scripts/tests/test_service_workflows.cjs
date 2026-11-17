const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const source = fs.readFileSync(path.resolve(__dirname, '../../.github/workflows/service-cd.yml'), 'utf8').replaceAll('\r\n', '\n');
const script = source.split('          script: |\n')[1].split('\n  publish:')[0].split('\n').map(l => l.startsWith('            ') ? l.slice(12) : l).join('\n').trim();
const select = new AsyncFunction('github', 'context', 'core', 'process', script);
const sha = 'a'.repeat(40);
const baseRun = { id: 12, workflow_id: 7, event: 'push', conclusion: 'success', head_sha: sha, head_branch: 'Testing', head_repository: { full_name: 'Bytser-com/Essers_Mapping' } };
async function check(options = {}) {
  const run = { ...baseRun, ...options.run };
  const branch = options.branch || run.head_branch;
  const outputs = {};
  const context = { repo: { owner: 'Bytser-com', repo: 'Essers_Mapping' }, ref: `refs/heads/${branch}`, payload: options.manual ? {} : { workflow_run: { id: 12, head_branch: branch } } };
  const github = { rest: {
    git: { getRef: async () => ({ data: { object: { sha: options.currentSha || sha } } }) },
    actions: {
      getWorkflow: async () => ({ data: { id: 7 } }),
      getWorkflowRun: async () => ({ data: run }),
      listWorkflowRuns: async () => ({ data: { workflow_runs: options.noRun ? [] : [run] } }),
      listWorkflowRunArtifacts: () => {},
    },
  }, paginate: async () => options.artifacts || [{ name: 'frontend-dist', expired: false }] };
  const summary = { addRaw() { return this; }, async write() {} };
  const core = { setOutput: (key, value) => { outputs[key] = value; }, summary };
  await select(github, context, core, { env: { CI_WORKFLOW: 'frontend-ci.yml', ARTIFACT_NAME: 'frontend-dist', IMAGE_NAME: 'frontend' } });
  return outputs;
}
(async () => {
  let count = 0;
  for (const branch of ['Testing', 'main']) {
    for (const manual of [true, false]) {
      const result = await check({ run: { head_branch: branch }, manual });
      assert.equal(result.enabled, 'true');
      assert.equal(result.environment, branch === 'main' ? 'Production' : 'Testing');
      assert.equal(result.sha, sha);
      assert.equal(result.image, 'ghcr.io/bytser-com/essers_mapping/frontend');
      count++;
    }
  }
  assert.equal((await check({ currentSha: 'b'.repeat(40) })).enabled, 'false'); count++;
  assert.equal((await check({ artifacts: [] })).enabled, 'false'); count++;
  for (const options of [
    { branch: 'Development' }, { branch: 'Feature/example' },
    { run: { event: 'pull_request' } }, { run: { conclusion: 'failure' } },
    { run: { conclusion: 'cancelled' } }, { run: { workflow_id: 999 } },
    { run: { head_repository: { full_name: 'external/fork' } } },
    { branch: 'Testing', run: { head_branch: 'main' } },
    { artifacts: [{ name: 'frontend-dist', expired: true }] },
    { manual: true, noRun: true },
  ]) { await assert.rejects(check(options)); count++; }
  console.log(`Passed ${count} service CD selection scenarios using the actual workflow script.`);
})().catch(error => { console.error(error); process.exitCode = 1; });
