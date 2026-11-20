"""Unit tests for services/packages.py: naming and storing mapping packages."""
import io
import json
from datetime import UTC, datetime

import openpyxl
import pytest

from scripts import config
from scripts.models import MappingEntry, MappingPackage, PackageMeta
from services.packages import (
    build_package_path,
    convert_excel_to_package,
    describe_packages_server,
    format_semver,
    normalize_slug,
    normalize_version,
    remote_package_path,
    save_mapping_package,
)
from services.storage import LocalStorage

NOW = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)


@pytest.fixture
def packages_root(tmp_path):
    return tmp_path / 'packages'


@pytest.fixture
def packages_storage(packages_root):
    return LocalStorage(packages_root)


@pytest.fixture(autouse=True)
def packages_dir(monkeypatch):
    monkeypatch.setenv('SFTP_SHARED_PACKAGES_DIR', '/Packages')


@pytest.mark.parametrize(('value', 'expected'), [
    (3, 'v3'), ('3', 'v3'), ('v3', 'v3'), ('V4', 'v4'), ('version12', 'v12'), ('', 'v1'),
])
def test_normalize_version(value, expected):
    assert normalize_version(value) == expected


@pytest.mark.parametrize(('value', 'expected'), [
    ('1.0.0', '1.0.0'), ('v3', '3.0.0'), ('4', '4.0.0'), ('V12', '12.0.0'), ('', '1.0.0'),
])
def test_format_semver(value, expected):
    assert format_semver(value) == expected


@pytest.mark.parametrize(('value', 'expected'), [
    ('Nouryon', 'nouryon'), ('  Inbound  ', 'inbound'), ('Order Message 01', 'order_message_01'),
])
def test_normalize_slug(value, expected):
    assert normalize_slug(value) == expected


def test_build_package_path_is_normalized():
    assert build_package_path('nouryon', 'v3', 'inbound') == 'nouryon/v3/inbound/MPackage.json'
    assert build_package_path('Kelmont', 2, 'Inbound') == 'kelmont/v2/inbound/MPackage.json'


def test_remote_package_path_uses_the_packages_dir():
    assert remote_package_path('nouryon/v4/outbound/MPackage.json') == '/Packages/nouryon/v4/outbound/MPackage.json'


def test_save_mapping_package_attaches_metadata_and_writes_json(packages_root, packages_storage):
    package = MappingPackage(mappings=[MappingEntry(source_path='/A/B', target_path='/C/D')])

    path = save_mapping_package(packages_storage, package, 'Nouryon', '1', 'Inbound',
                                user_created='analist_b', package_version='1.0.0', now=NOW)

    assert path == '/Packages/nouryon/v1/inbound/MPackage.json'
    assert package.meta == PackageMeta(client_name='nouryon', package_version='1.0.0', package_type='inbound',
                                       date_created='2026-11-20T10:00:00Z', user_created='analist_b')
    stored = json.loads((packages_root / 'nouryon/v1/inbound/MPackage.json').read_text(encoding='utf-8'))
    assert stored['schema_version'] == '1.0'
    assert stored['meta']['client_name'] == 'nouryon'
    assert stored['mappings'] == [{'source_path': '/A/B', 'target_path': '/C/D'}]


def test_existing_metadata_is_kept(packages_storage):
    meta = PackageMeta(client_name='x', package_version='9.9.9', package_type='y', date_created='2020-01-01T00:00:00Z')
    package = MappingPackage(meta=meta)

    save_mapping_package(packages_storage, package, 'Nouryon', 'v2', 'inbound')

    assert package.meta == meta


def test_package_version_defaults_to_the_folder_version(packages_storage):
    package = MappingPackage()
    save_mapping_package(packages_storage, package, 'nouryon', 'v4', 'outbound', now=NOW)
    assert package.meta.package_version == '4.0.0'
    assert package.meta.user_created == 'analist_a'


def test_convert_excel_to_package(packages_root, packages_storage):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Mapping Proposal'
    ws.append(['Target segment path', 'Target field name', 'Source full path'])
    ws.append(['/ORDER/HEADER', 'ORDER_NUM', '/INVOICE/INV_NUM'])
    buf = io.BytesIO()
    wb.save(buf)

    package, path = convert_excel_to_package(packages_storage, buf.getvalue(), 'Nouryon', 'v4', 'outbound')

    assert len(package.mappings) == 1
    assert path == '/Packages/nouryon/v4/outbound/MPackage.json'
    assert (packages_root / 'nouryon/v4/outbound/MPackage.json').is_file()


def test_describe_packages_server(monkeypatch):
    monkeypatch.setattr(config, '_env_loaded', True)
    monkeypatch.setenv('SFTP_SHARED_HOST', 'sftp-shared')
    monkeypatch.setenv('SFTP_SHARED_PORT', '22')
    assert describe_packages_server() == 'sftp-shared:22'

    monkeypatch.setenv('SFTP_SHARED_HOST', '')
    assert describe_packages_server() == 'local-filesystem'
