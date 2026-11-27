// Select trusted CI output for Testing, or a successfully deployed Testing image for main.
module.exports = async function selectRelease({ github, context, core, env }) {
  const { owner, repo } = context.repo;
  const repository = `${owner}/${repo}`;
  const branch = context.ref.replace('refs/heads/', '');
  if (!['Testing', 'main'].includes(branch) || !['push', 'workflow_dispatch'].includes(context.eventName)) {
    throw new Error('CD only supports pushes or manual runs on Testing and main.');
  }
  if (!/^[A-Za-z0-9_-]+$/.test(env.SERVICE_PATH)) throw new Error('Invalid service directory.');
  const { data: ref } = await github.rest.git.getRef({ owner, repo, ref: `heads/${branch}` });
  const { data: workflow } = await github.rest.actions.getWorkflow({ owner, repo, workflow_id: env.CI_WORKFLOW });
  const { data: callerRun } = await github.rest.actions.getWorkflowRun({ owner, repo, run_id: context.runId });
  let run = callerRun;
  if (context.eventName === 'workflow_dispatch' && callerRun.workflow_id !== workflow.id) {
    const { data } = await github.rest.actions.listWorkflowRuns({
      owner, repo, workflow_id: workflow.id, branch, head_sha: ref.object.sha,
      status: 'success', per_page: 10,
    });
    run = data.workflow_runs[0];
  }
  // The inline CD job runs after its CI checks/gate; its enclosing workflow is still running.
  const inline = run?.id === context.runId && run?.status === 'in_progress';
  if (!run || run.workflow_id !== workflow.id || !['push', 'workflow_dispatch'].includes(run.event) ||
      (!inline && run.conclusion !== 'success') || run.head_branch !== branch ||
      run.head_repository?.full_name !== repository) {
    throw new Error('Refusing CD: a trusted successful CI run is required.');
  }
  if (run.head_sha !== ref.object.sha || (context.sha && context.sha !== ref.object.sha)) {
    core.setOutput('enabled', 'false');
    await core.summary.addRaw('CD skipped: a newer commit superseded this run.').write();
    return;
  }
  const { data: tree } = await github.rest.git.getTree({ owner, repo, tree_sha: run.head_sha });
  const serviceTree = tree.tree.find(item => item.path === env.SERVICE_PATH && item.type === 'tree')?.sha;
  if (!serviceTree) throw new Error('Service source directory is missing.');
  const releaseName = `tested-${env.IMAGE_NAME}-${serviceTree}`;
  if (branch === 'Testing') {
    const artifacts = await github.paginate(github.rest.actions.listWorkflowRunArtifacts, { owner, repo, run_id: run.id, per_page: 100 });
    const image = artifacts.find(item => item.name === `${env.SERVICE_PATH}-image`);
    if (!image || image.expired) throw new Error('The tested container artifact is missing or expired. Rerun Testing CI.');
    core.setOutput('image-artifact-id', String(image.id));
  } else {
    const { data: manualWorkflow } = await github.rest.actions.getWorkflow({
      owner, repo, workflow_id: env.CI_WORKFLOW.replace('-ci.yml', '-cd.yml'),
    });
    const artifacts = await github.paginate(github.rest.actions.listArtifactsForRepo, { owner, repo, name: releaseName, per_page: 100 });
    let receipt;
    for (const artifact of artifacts.filter(a => a.name === releaseName && !a.expired).sort((a, b) => b.id - a.id)) {
      if (artifact.workflow_run?.head_branch !== 'Testing') continue;
      const { data: testedRun } = await github.rest.actions.getWorkflowRun({ owner, repo, run_id: artifact.workflow_run.id });
      const trustedWorkflow = (testedRun.workflow_id === workflow.id && ['push', 'workflow_dispatch'].includes(testedRun.event)) ||
        (testedRun.workflow_id === manualWorkflow.id && testedRun.event === 'workflow_dispatch');
      if (!trustedWorkflow || testedRun.conclusion !== 'success' || testedRun.head_branch !== 'Testing' ||
          testedRun.head_repository?.full_name !== repository) continue;
      const { data: testedTree } = await github.rest.git.getTree({ owner, repo, tree_sha: testedRun.head_sha });
      if (!testedTree.tree.some(item => item.path === env.SERVICE_PATH && item.type === 'tree' && item.sha === serviceTree)) continue;
      receipt = { artifact, run: testedRun };
      break;
    }
    if (!receipt) throw new Error('No successful Testing deployment matches this service source. Deploy and test it on Testing first; production never rebuilds.');
    core.setOutput('receipt-id', String(receipt.artifact.id));
    core.setOutput('receipt-run-id', String(receipt.run.id));
    core.setOutput('receipt-sha', receipt.run.head_sha);
  }
  for (const [key, value] of Object.entries({
    enabled: 'true', sha: run.head_sha, branch, 'run-id': String(run.id),
    image: `ghcr.io/${repository.toLowerCase()}/${env.IMAGE_NAME}`,
    environment: branch === 'main' ? 'Production' : 'Testing',
    namespace: branch === 'main' ? 'essers-mapping-production' : 'essers-mapping-testing',
    'source-tree': serviceTree, 'release-name': releaseName,
  })) core.setOutput(key, value);
};
