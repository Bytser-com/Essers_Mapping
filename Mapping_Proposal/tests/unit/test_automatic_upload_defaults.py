"""Automatic frontend uploads have independent, configurable settings."""

from scripts import config
from services import incoming_watcher


def test_default_upload_settings(monkeypatch):
    for name in ('AI_LIMIT_TARGETS', 'AI_SOURCE_SAMPLES', 'AI_HISTORY_PAIRS',
                 'AI_BATCH_SIZE', 'GEMINI_MAX_ATTEMPTS'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, '_env_loaded', True)
    assert config.ai_limit_targets() == 0
    assert config.ai_source_samples() == 5
    assert config.ai_history_pairs() == 3
    assert config.ai_batch_size() == 10
    assert config.gemini_max_attempts() == 20


def test_override_and_invalid_configuration(monkeypatch):
    monkeypatch.setattr(config, '_env_loaded', True)
    monkeypatch.setenv('AI_LIMIT_TARGETS', '10')
    monkeypatch.setenv('AI_SOURCE_SAMPLES', 'bad')
    monkeypatch.setenv('AI_HISTORY_PAIRS', '1')
    monkeypatch.setenv('AI_BATCH_SIZE', '0')
    monkeypatch.setenv('GEMINI_MAX_ATTEMPTS', '24')
    assert config.ai_limit_targets() == 10
    assert config.ai_source_samples() == 5
    assert config.ai_history_pairs() == 1
    assert config.ai_batch_size() == 1
    assert config.gemini_max_attempts() == 24


def test_default_watcher_uses_upload_settings(tmp_path, monkeypatch):
    from services.proposals import ProposalStore

    monkeypatch.setattr(incoming_watcher, 'incoming_dir', lambda: tmp_path / 'incoming')
    monkeypatch.setattr(incoming_watcher, 'proposal_storage', lambda: tmp_path / 'storage')
    monkeypatch.setattr(incoming_watcher, 'ai_limit_targets', lambda: 0)
    monkeypatch.setattr(incoming_watcher, 'ai_source_samples', lambda: 5)
    monkeypatch.setattr(incoming_watcher, 'ai_history_pairs', lambda: 3)
    monkeypatch.setattr(incoming_watcher, 'ai_batch_size', lambda: 10)
    watcher = incoming_watcher.default_watcher()
    assert isinstance(watcher.store, ProposalStore)
    assert watcher.settings.limit_targets == 0
    assert watcher.settings.source_samples == 5
    assert watcher.settings.history_pairs == 3
    assert watcher.settings.batch_size == 10
