"""Shared pytest fixtures for the Mapping Converter tests.

Tests never use the real SFTP server: they use a temporary folder (LocalStorage),
and never call Gemini: the AI review is replaced by a fake in every test that needs it.
"""
import io

import pytest
from openpyxl import Workbook

from services.storage import LocalStorage


@pytest.fixture
def proposals_root(tmp_path):
    root = tmp_path / 'proposals'
    root.mkdir()
    return root


@pytest.fixture
def proposals_storage(proposals_root):
    return LocalStorage(proposals_root)


@pytest.fixture
def packages_root(tmp_path):
    root = tmp_path / 'packages'
    root.mkdir()
    return root


@pytest.fixture
def packages_storage(packages_root):
    return LocalStorage(packages_root)


@pytest.fixture
def mapping_excel():
    """A real "Mapping Proposal" workbook (bytes): readable by the AI review and the package converter."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Mapping Proposal'
    sheet.append(['', 'TARGET', '', 'SOURCE', ''])
    sheet.append(['Mapping ID', 'Target segment path', 'Target field name', 'Source full path', 'Proposed rule type'])
    sheet.append(['MP-001', '/TARGET/HDR', 'DOC_ID', '/SOURCE/HEADER/ID', 'DIRECT'])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
