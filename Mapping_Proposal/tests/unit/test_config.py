"""Verify local and deployed Gemini configuration without contacting Gemini."""

from scripts import config


def test_personal_dotenv_supplies_local_key(tmp_path, monkeypatch):
    (tmp_path / '.env').write_text('GEMINI_API_KEY=local-test-key\n', encoding='utf-8')
    monkeypatch.setattr(config, 'ROOT', tmp_path)
    monkeypatch.setattr(config, '_env_loaded', False)
    # setenv registers restoration, even when dotenv adds the value afterwards.
    monkeypatch.setenv('GEMINI_API_KEY', '')
    monkeypatch.delenv('GEMINI_API_KEY')

    assert config.load_settings().gemini_api_key == 'local-test-key'


def test_deployed_key_takes_precedence_over_personal_dotenv(tmp_path, monkeypatch):
    (tmp_path / '.env').write_text('GEMINI_API_KEY=local-test-key\n', encoding='utf-8')
    monkeypatch.setattr(config, 'ROOT', tmp_path)
    monkeypatch.setattr(config, '_env_loaded', False)
    monkeypatch.setenv('GEMINI_API_KEY', 'deployment-test-key')

    assert config.load_settings().gemini_api_key == 'deployment-test-key'
