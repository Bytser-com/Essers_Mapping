"""Tests for the review coordination and shared environment configuration."""

from scripts import config, pipeline


def test_pipeline_passes_extracted_records_to_gemini(monkeypatch):
    extracted = [{'excel_row': 3, 'Target field name': 'CITY'}]
    calls = []

    def fake_extract(contents):
        assert contents == b'excel-file'
        calls.append('extract')
        return extracted

    def fake_review(records):
        assert records is extracted
        calls.append('review')
        return {'decision': 'ACCEPTED', 'summary': 'OK', 'findings': [], 'checked_mappings': 1}

    monkeypatch.setattr(pipeline, 'read_mapping_proposal', fake_extract)
    monkeypatch.setattr(pipeline, 'review_with_gemini', fake_review)

    assert pipeline.run_review(b'excel-file')['decision'] == 'ACCEPTED'
    assert calls == ['extract', 'review']


def test_review_settings_use_environment_values(monkeypatch):
    monkeypatch.setattr(config, 'load_dotenv', lambda *args, **kwargs: False)
    monkeypatch.setenv('GEMINI_API_KEY', 'dummy-test-key')
    monkeypatch.setenv('GEMINI_MODEL', 'shared-model')
    monkeypatch.delenv('GEMINI_REVIEW_MODEL', raising=False)
    settings = config.load_review_settings()
    assert settings.api_key == 'dummy-test-key'
    assert settings.model == 'shared-model'
    assert settings.timeout_ms == 60000


def test_review_model_overrides_shared_model(monkeypatch):
    monkeypatch.setattr(config, 'load_dotenv', lambda *args, **kwargs: False)
    monkeypatch.setenv('GEMINI_API_KEY', 'dummy-test-key')
    monkeypatch.setenv('GEMINI_MODEL', 'shared-model')
    monkeypatch.setenv('GEMINI_REVIEW_MODEL', 'review-model')
    assert config.load_review_settings().model == 'review-model'
