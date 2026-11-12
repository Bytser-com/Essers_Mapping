"""Retry behavior for frontend uploads, without real Gemini or SFTP."""

import json
import logging
from pathlib import Path

from scripts.errors import GeminiError, QuotaExceededError
from scripts.models import MappingResult
from services.incoming_watcher import IncomingWatcher, configure_ai_logging
from services.proposal_runner import is_retryable_gemini_error
from services.proposals import AiStatus, ProposalStatus, ProposalStore


def _upload(incoming: Path):
    folder = incoming / 'upload-1'
    folder.mkdir(parents=True)
    (folder / 'order.xml').write_text('<Order><ID>ABCD1234</ID></Order>', encoding='utf-8')
    (folder / 'upload.json').write_text(json.dumps({'customer': 'Ostavel'}), encoding='utf-8')


def _runner(tmp_path, errors):
    calls = []

    def run(settings):
        calls.append(settings.source_dir)
        if errors:
            raise errors.pop(0)
        workbook = tmp_path / 'finished.xlsx'
        workbook.write_bytes(b'generated-workbook-test')
        return MappingResult(run_id='test', run_dir=tmp_path, workbook_path=workbook,
                             mapping_rows=1, placeholders=0, rejected_proposals=0, structural_issues=0)

    return run, calls


def test_retryable_errors_are_classified_conservatively():
    assert is_retryable_gemini_error(QuotaExceededError('Gemini rate limit reached (minute quota)', code=429))
    assert is_retryable_gemini_error(QuotaExceededError('Gemini is overloaded (503)', code=503))
    assert is_retryable_gemini_error(GeminiError('timed out', code='timeout'))
    assert not is_retryable_gemini_error(QuotaExceededError('daily quota exceeded', code=429))
    assert not is_retryable_gemini_error(RuntimeError('Server overloaded'))


def test_temporary_failure_keeps_same_upload_and_can_resume_after_restart(tmp_path, monkeypatch):
    incoming = tmp_path / 'incoming'
    store = ProposalStore(tmp_path / 'storage')
    _upload(incoming)
    monkeypatch.setenv('AI_RETRY_MAX_ATTEMPTS', '3')
    monkeypatch.setenv('AI_RETRY_DELAY_SECONDS', '600')
    runner, calls = _runner(tmp_path, [QuotaExceededError('Gemini rate limit reached (minute quota)', code=429)])
    first = IncomingWatcher(incoming, store, run=runner)
    assert first.run_once() == 1
    [proposal] = store.list_proposals()
    assert proposal.ai_status is AiStatus.RUNNING
    folder = incoming / 'upload-1.processing'
    assert (folder / 'order.xml').is_file()
    assert (folder / 'retry_state.json').is_file()
    assert list((tmp_path / 'storage').rglob('*.xlsx')) == []
    # Not ready yet; polling should not attempt immediately.
    assert first.run_once() == 0
    assert len(calls) == 1
    # Restart the API and simulate passage of the scheduled retry time.
    retry = json.loads((folder / 'retry_state.json').read_text(encoding='utf-8'))
    retry['next_retry_at'] = 0
    (folder / 'retry_state.json').write_text(json.dumps(retry), encoding='utf-8')
    second = IncomingWatcher(incoming, store, run=runner)
    assert second.recover_interrupted() == 1
    assert second.run_once() == 1
    assert len(calls) == 2
    [proposal] = store.list_proposals()
    assert proposal.version == 1
    assert proposal.status is ProposalStatus.READY_FOR_REVIEW
    assert list((tmp_path / 'storage').rglob('*.xlsx'))
    assert not folder.exists()


def test_retry_exhaustion_moves_upload_to_failed(tmp_path, monkeypatch):
    incoming = tmp_path / 'incoming'
    store = ProposalStore(tmp_path / 'storage')
    _upload(incoming)
    monkeypatch.setenv('AI_RETRY_MAX_ATTEMPTS', '2')
    monkeypatch.setenv('AI_RETRY_DELAY_SECONDS', '0')
    runner, calls = _runner(tmp_path, [
        QuotaExceededError('Gemini is overloaded (503)', code=503),
        QuotaExceededError('Gemini is overloaded (503)', code=503),
    ])
    watcher = IncomingWatcher(incoming, store, run=runner)
    assert watcher.run_once() == 1
    assert watcher.run_once() == 1
    [proposal] = store.list_proposals()
    assert proposal.ai_status is AiStatus.FAILED
    assert len(calls) == 2
    assert (incoming / 'failed' / 'upload-1' / 'order.xml').is_file()


def test_permanent_error_fails_immediately(tmp_path):
    incoming = tmp_path / 'incoming'
    store = ProposalStore(tmp_path / 'storage')
    _upload(incoming)
    runner, calls = _runner(tmp_path, [QuotaExceededError('daily quota exceeded', code=429)])
    watcher = IncomingWatcher(incoming, store, run=runner)
    assert watcher.run_once() == 1
    assert len(calls) == 1
    assert (incoming / 'failed' / 'upload-1' / 'error.txt').is_file()


def test_api_logging_enables_batch_info(caplog):
    configure_ai_logging()
    with caplog.at_level(logging.INFO, logger='scripts'):
        logging.getLogger('scripts.pipeline').info('Mapping batch 1/10: 10 target fields')
    assert 'Mapping batch 1/10' in caplog.text


def test_real_pipeline_restores_first_batch_after_transient_second_batch_failure(tmp_path, monkeypatch):
    """Only Gemini is faked: the real pipeline handles checkpoints + Excel."""
    from scripts import pipeline
    from scripts.models import MappingSettings

    fixtures = Path(__file__).resolve().parents[1] / 'fixtures'
    incoming = tmp_path / 'incoming'
    store = ProposalStore(tmp_path / 'storage')
    customer_xml = fixtures / 'source' / 'order_ostavel.xml'
    folder = incoming / 'upload-1'
    folder.mkdir(parents=True)
    (folder / 'order.xml').write_bytes(customer_xml.read_bytes())
    (folder / 'upload.json').write_text('{"customer":"Ostavel"}', encoding='utf-8')
    monkeypatch.setattr(pipeline, 'HISTORICAL_DIR', fixtures / 'historical')
    monkeypatch.setattr(pipeline, 'ROOT', tmp_path)
    monkeypatch.setattr(pipeline, 'RUNS_DIR', tmp_path / 'output' / 'runs')
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.setenv('AI_RETRY_DELAY_SECONDS', '0')
    monkeypatch.setenv('AI_RETRY_MAX_ATTEMPTS', '3')
    seen = []
    second_batch_failed = False

    def fake_gemini(source_fields, target_fields, **kwargs):
        nonlocal second_batch_failed
        target = target_fields[0]['path']
        seen.append(target)
        callback = kwargs['on_event']
        callback({'type': 'attempt'})
        if len(seen) == 2 and not second_batch_failed:
            second_batch_failed = True
            callback({'type': 'api_error', 'code': 503})
            raise QuotaExceededError('Gemini is overloaded (503)', code=503)
        callback({'type': 'usage', 'input_tokens': 100, 'output_tokens': 10, 'total_tokens': 110})
        source = next(field['path'] for field in source_fields if field['path'].endswith('/OrderNumber'))
        return [{
            'source_path': source, 'target_path': target, 'rule_type': 'DIRECT',
            'confidence': 80, 'requires_review': True, 'review_priority': 'MEDIUM',
            'reason': 'Fixture-based test proposal', 'evidence': '', 'fixed_value': '',
            'transformation': '', 'condition': '', 'lookup': '', 'loop': '',
            'review_question': 'Verify.', 'risk_category': 'MEDIUM',
        }]

    monkeypatch.setattr(pipeline, 'run_gemini', fake_gemini)
    settings = MappingSettings(history_pairs=1, source_samples=1, limit_targets=3, batch_size=1)
    watcher = IncomingWatcher(incoming, store, settings=settings, run=pipeline.run_mapping)
    assert watcher.run_once() == 1
    assert len(seen) == 2
    assert list((tmp_path / 'output' / 'runs').rglob('batch_0001.json'))
    assert not list((tmp_path / 'storage').rglob('*.xlsx'))
    [proposal] = store.list_proposals()
    assert proposal.ai_status is AiStatus.RUNNING

    # Retry the exact same upload, without sending batch 1 again.
    assert IncomingWatcher(incoming, store, settings=settings, run=pipeline.run_mapping).run_once() == 1
    assert len(seen) == 4  # batch 1 once, batch 2 twice, batch 3 once
    assert seen.count(seen[0]) == 1
    [proposal] = store.list_proposals()
    assert proposal.version == 1
    assert proposal.status is ProposalStatus.READY_FOR_REVIEW
    assert len(list((tmp_path / 'storage').rglob('*.xlsx'))) == 1
