"""Unit tests for scripts/config.py: settings from the environment and the shared .env."""
from __future__ import annotations

import os

import pytest

from scripts import config


@pytest.fixture(autouse=True)
def no_real_env_file(monkeypatch):
    """Never read the developer's real .env during the tests."""
    monkeypatch.setattr(config, '_env_loaded', True)


def test_without_sftp_host_there_is_no_sftp_config(monkeypatch):
    monkeypatch.setenv('SFTP_SHARED_HOST', '  ')
    assert config.sftp_shared_config() is None
    assert config.sftp_shared_packages_config() is None


def test_sftp_config_from_the_environment(monkeypatch):
    monkeypatch.setenv('SFTP_SHARED_HOST', 'sftp-shared')
    monkeypatch.setenv('SFTP_SHARED_PORT', '2222')
    monkeypatch.setenv('SFTP_SHARED_USER', ' shareduser ')
    monkeypatch.setenv('SFTP_SHARED_PASSWORD', 'secret')
    monkeypatch.setenv('SFTP_SHARED_PROPOSALS_DIR', 'Proposals')
    monkeypatch.setenv('SFTP_SHARED_PACKAGES_DIR', '/Packages')

    assert config.sftp_shared_config() == {
        'host': 'sftp-shared', 'port': 2222, 'user': 'shareduser', 'password': 'secret',
        'base_dir': '/Proposals', 'proposals_dir': '',
    }
    assert config.sftp_shared_packages_config()['base_dir'] == '/Packages'


def test_default_folders_and_invalid_port(monkeypatch):
    monkeypatch.setenv('SFTP_SHARED_HOST', 'sftp-shared')
    monkeypatch.setenv('SFTP_SHARED_PORT', 'abc')
    monkeypatch.delenv('SFTP_SHARED_PROPOSALS_DIR', raising=False)
    monkeypatch.delenv('SFTP_SHARED_PACKAGES_DIR', raising=False)

    assert config.sftp_shared_config()['port'] == 22
    assert config.sftp_shared_config()['base_dir'] == '/Proposals'
    assert config.sftp_shared_packages_config()['base_dir'] == '/Packages'


def test_local_folders_live_under_the_shared_dir():
    assert config.proposals_dir() == config.shared_storage_dir() / 'proposals'
    assert config.packages_dir() == config.shared_storage_dir() / 'packages'


def test_cors_origins_are_split_and_trimmed(monkeypatch):
    monkeypatch.setenv('CORS_ORIGINS', 'http://localhost:5173, http://localhost:3000 ,,')
    assert config.cors_origins() == ['http://localhost:5173', 'http://localhost:3000']

    monkeypatch.setenv('CORS_ORIGINS', '')
    assert config.cors_origins() == []


def test_shared_env_file_in_the_repo_root_is_read_once(monkeypatch, tmp_path):
    (tmp_path / '.env').write_text('CONVERTER_TEST_VALUE=from-env-file\n', encoding='utf-8')
    monkeypatch.setattr(config, 'REPO_ROOT', tmp_path)
    monkeypatch.setattr(config, '_env_loaded', False)
    monkeypatch.delenv('CONVERTER_TEST_VALUE', raising=False)

    config._load_env()
    assert config._env_loaded is True
    assert os.environ['CONVERTER_TEST_VALUE'] == 'from-env-file'
    monkeypatch.delenv('CONVERTER_TEST_VALUE')


def test_existing_variables_win_over_the_env_file(monkeypatch, tmp_path):
    (tmp_path / '.env').write_text('CONVERTER_TEST_VALUE=from-env-file\n', encoding='utf-8')
    monkeypatch.setattr(config, 'REPO_ROOT', tmp_path)
    monkeypatch.setattr(config, '_env_loaded', False)
    monkeypatch.setenv('CONVERTER_TEST_VALUE', 'from-terminal')

    config._load_env()
    assert os.environ['CONVERTER_TEST_VALUE'] == 'from-terminal'
