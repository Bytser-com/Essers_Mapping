"""Shared pytest fixtures for the Mapping Converter tests.

Tests never use the real SFTP server: they use a temporary folder (LocalStorage).
"""
import pytest

from services.storage import LocalStorage


@pytest.fixture
def proposals_root(tmp_path):
    root = tmp_path / 'proposals'
    root.mkdir()
    return root


@pytest.fixture
def proposals_storage(proposals_root):
    return LocalStorage(proposals_root)
