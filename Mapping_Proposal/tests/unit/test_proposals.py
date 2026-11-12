"""The proposal.json files that Mapping_Proposal writes per upload: services/proposals.py.

User story: "Als analist wil ik een overzicht van alle klanten en hun mapping packages,
zodat ik snel naar het juiste package kan gaan."

The overview on Home itself is served by Version_Control (GET /api/version-control/proposals),
see SftpProposalStorageServiceTest there. These tests check that the data Mapping_Proposal writes
can be read back with the same rules. The test names keep the Jira test case (TC-57-xx) they relate to.

The storage is a temporary folder with the same layout as on the SFTP server
(<root>/<customer folder>/v<N>/proposal.json). The same code runs on SFTP, see
tests/unit/test_storage.py.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from services.proposals import (
    AiStatus,
    ProposalStatus,
    ProposalStore,
    ProposalSummary,
    customer_folder_name,
)


def write_proposal(root: Path, folder: str, version: int, *, customer: str | None = 'Klant',
                   uploaded_at: str | None = '2026-10-22T14:05:00+02:00',
                   status: str = 'READY_FOR_REVIEW', ai_status: str | None = None, raw: str | None = None):
    """One version folder with its proposal.json, like the AI run writes it."""
    version_dir = root / folder / f'v{version}'
    version_dir.mkdir(parents=True, exist_ok=True)
    data = {'status': status, 'ai_status': ai_status}
    if customer is not None:
        data['customer'] = customer
    if uploaded_at is not None:
        data['uploaded_at'] = uploaded_at
    (version_dir / 'proposal.json').write_text(raw if raw is not None else json.dumps(data), encoding='utf-8')
    return version_dir


@pytest.fixture
def root(tmp_path):
    return tmp_path / 'proposals'


@pytest.fixture
def store(root):
    return ProposalStore(root)


# ---------------------------------------------------------------------------
# The list
# ---------------------------------------------------------------------------
def test_tc_57_02_overview_shows_one_row_per_customer_with_its_latest_version(root, store):
    write_proposal(root, 'ostavel', 1, customer='Ostavel', uploaded_at='2026-10-20T10:00:00+02:00')
    write_proposal(root, 'ostavel', 2, customer='Ostavel', uploaded_at='2026-10-21T10:00:00+02:00')
    write_proposal(root, 'brunos', 1, customer='Brunos', uploaded_at='2026-10-19T10:00:00+02:00')

    rows = store.list_proposals()

    assert [(row.customer, row.version) for row in rows] == [('Ostavel', 2), ('Brunos', 1)]


def test_tc_57_02_the_highest_version_wins_even_if_it_was_uploaded_earlier(root, store):
    write_proposal(root, 'ostavel', 1, uploaded_at='2026-10-25T10:00:00+02:00')
    write_proposal(root, 'ostavel', 10, uploaded_at='2026-10-20T10:00:00+02:00')

    [row] = store.list_proposals()

    assert row.version == 10  # v10 > v2 > v1: compared as numbers, not as text


def test_tc_57_03_newest_upload_is_shown_first(root, store):
    write_proposal(root, 'a', 1, customer='A', uploaded_at='2026-10-20T10:00:00+02:00')
    write_proposal(root, 'b', 1, customer='B', uploaded_at='2026-10-22T10:00:00+02:00')
    write_proposal(root, 'c', 1, customer='C', uploaded_at='2026-10-21T10:00:00+02:00')

    assert [row.customer for row in store.list_proposals()] == ['B', 'C', 'A']


def test_tc_57_03_timezones_are_compared_correctly(root, store):
    # 09:30 UTC is later than 10:00 in Brussels (08:00 UTC)
    write_proposal(root, 'brussel', 1, customer='Brussel', uploaded_at='2026-10-22T10:00:00+02:00')
    write_proposal(root, 'utc', 1, customer='Utc', uploaded_at='2026-10-22T09:30:00Z')

    assert [row.customer for row in store.list_proposals()] == ['Utc', 'Brussel']


def test_tc_57_02_all_versions_returns_every_version(root, store):
    for version in (1, 2, 3):
        write_proposal(root, 'ostavel', version, uploaded_at=f'2026-10-2{version}T10:00:00+02:00')

    rows = store.list_proposals(all_versions=True)

    assert [row.version for row in rows] == [3, 2, 1]


def test_tc_57_09_empty_storage_gives_an_empty_overview(root, store):
    assert store.list_proposals() == []          # folder does not exist yet
    root.mkdir(parents=True)
    assert store.list_proposals() == []          # folder exists but is empty


# ---------------------------------------------------------------------------
# What one row contains
# ---------------------------------------------------------------------------
def test_tc_57_04_row_contains_customer_version_upload_time_status_and_ai_status(root, store):
    write_proposal(root, 'voorbeeldbedrijf-a', 1, customer='Voorbeeldbedrijf A',
                   uploaded_at='2026-10-22T14:05:00+02:00', status='AI_GENERATING', ai_status='RUNNING')

    [row] = store.list_proposals()

    assert row.to_dict() == {
        'id': 'voorbeeldbedrijf-a/v1',
        'customer': 'Voorbeeldbedrijf A',
        'version': 1,
        'uploaded_at': '2026-10-22T14:05:00+02:00',
        'status': 'AI_GENERATING',
        'ai_status': 'RUNNING',
        'can_open': False,
    }


@pytest.mark.parametrize('status', list(ProposalStatus))
def test_tc_57_05_every_status_is_read(root, store, status):
    write_proposal(root, 'klant', 1, status=status.value)

    [row] = store.list_proposals()

    assert row.status is status


@pytest.mark.parametrize('ai_status, expected', [('RUNNING', AiStatus.RUNNING), ('FAILED', AiStatus.FAILED),
                                                 (None, None), ('', None)])
def test_tc_57_05_ai_status_is_read_and_empty_means_none(root, store, ai_status, expected):
    write_proposal(root, 'klant', 1, ai_status=ai_status)

    [row] = store.list_proposals()

    assert row.ai_status is expected
    assert row.to_dict()['ai_status'] == (expected.value if expected else None)


@pytest.mark.parametrize('status, can_open', [
    (ProposalStatus.AI_GENERATING, False),       # nothing to open while the AI writes the first version
    (ProposalStatus.READY_FOR_REVIEW, True),
    (ProposalStatus.IN_REVIEW, True),
    (ProposalStatus.AI_CHECKING_REVIEW, True),
    (ProposalStatus.RETURNED, True),
])
def test_tc_57_06_openen_only_when_the_ai_is_not_writing_the_proposal(status, can_open):
    row = ProposalSummary('klant/v1', 'Klant', 1, datetime.now(UTC), status, None)

    assert row.can_open is can_open
    assert row.to_dict()['can_open'] is can_open


def test_tc_57_04_customer_name_falls_back_to_the_folder_name(root, store):
    write_proposal(root, 'ostavel', 1, customer=None)

    [row] = store.list_proposals()

    assert row.customer == 'ostavel'


def test_tc_57_04_version_comes_from_the_folder_name(root, store):
    write_proposal(root, 'ostavel', 4, raw=json.dumps({
        'customer': 'Ostavel', 'version': 99, 'uploaded_at': '2026-10-22T14:05:00+02:00',
        'status': 'READY_FOR_REVIEW', 'ai_status': None}))

    [row] = store.list_proposals()

    assert row.version == 4


@pytest.mark.parametrize('value, expected', [
    ('2026-10-22T14:05:00+02:00', datetime(2026, 10, 22, 12, 5, tzinfo=UTC)),
    ('2026-10-22T12:05:00Z', datetime(2026, 10, 22, 12, 5, tzinfo=UTC)),
    ('2026-10-22T12:05:00', datetime(2026, 10, 22, 12, 5, tzinfo=UTC)),  # no timezone = UTC
])
def test_tc_57_04_upload_time_formats_are_understood(root, store, value, expected):
    write_proposal(root, 'klant', 1, uploaded_at=value)

    [row] = store.list_proposals()

    assert row.uploaded_at == expected
    assert row.uploaded_at.utcoffset() is not None


# ---------------------------------------------------------------------------
# Broken data never breaks the overview
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('broken', [
    {'raw': '{not json'},
    {'raw': '["a list, not an object"]'},
    {'status': 'UNKNOWN'},
    {'ai_status': 'SLEEPING'},
    {'uploaded_at': None},
    {'uploaded_at': 'yesterday'},
])
def test_tc_57_01_broken_proposal_is_skipped_and_the_rest_is_shown(root, store, broken, caplog):
    write_proposal(root, 'kapot', 1, customer='Kapot', **broken)
    write_proposal(root, 'goed', 1, customer='Goed')

    rows = store.list_proposals()

    assert [row.customer for row in rows] == ['Goed']
    assert 'Skipping proposal kapot/v1' in caplog.text


def test_tc_57_01_version_folder_without_proposal_json_is_skipped(root, store, caplog):
    write_proposal(root, 'ostavel', 1, customer='Ostavel')
    (root / 'ostavel' / 'v2').mkdir()  # the AI run crashed before writing proposal.json

    [row] = store.list_proposals()

    assert row.version == 1
    assert 'proposal.json is missing' in caplog.text


def test_tc_57_01_other_files_and_folders_are_ignored(root, store):
    write_proposal(root, 'ostavel', 1, customer='Ostavel')
    (root / 'ostavel' / 'notes').mkdir()
    (root / 'ostavel' / 'readme.txt').write_text('x')
    (root / 'readme.txt').write_text('x')
    (root / 'leeg').mkdir()  # customer folder without versions

    assert [row.customer for row in store.list_proposals()] == ['Ostavel']


def test_tc_57_01_windows_bom_in_proposal_json_is_accepted(root, store):
    version_dir = write_proposal(root, 'ostavel', 1)
    data = {'customer': 'Ostavel', 'uploaded_at': '2026-10-22T14:05:00+02:00', 'status': 'READY_FOR_REVIEW'}
    (version_dir / 'proposal.json').write_text(json.dumps(data), encoding='utf-8-sig')

    [row] = store.list_proposals()

    assert row.customer == 'Ostavel'


# ---------------------------------------------------------------------------
# Status changes made by the AI run are visible in the overview
# ---------------------------------------------------------------------------
def test_tc_57_08_new_proposal_appears_with_ai_maakt_voorstel_and_bezig(store):
    before = datetime.now(UTC).replace(microsecond=0)

    ref = store.create_proposal('  Ostavel  ')

    [row] = store.list_proposals()
    assert (row.id, row.customer, row.version) == ('ostavel/v1', 'Ostavel', 1)
    assert (row.status, row.ai_status, row.can_open) == (ProposalStatus.AI_GENERATING, AiStatus.RUNNING, False)
    assert before <= row.uploaded_at <= before + timedelta(minutes=1)
    assert ref.id == 'ostavel/v1'


def test_tc_57_08_next_upload_of_the_same_customer_is_the_next_version(store):
    store.create_proposal('Ostavel')
    store.create_proposal('Ostavel')

    assert [row.version for row in store.list_proposals(all_versions=True)] == [2, 1]
    assert [row.version for row in store.list_proposals()] == [2]


def test_tc_57_07_status_update_keeps_customer_and_upload_time(root, store):
    ref = store.create_proposal('Ostavel')
    [before] = store.list_proposals()

    store.set_status(ref, ProposalStatus.READY_FOR_REVIEW, None)

    [after] = store.list_proposals()
    assert (after.status, after.ai_status, after.can_open) == (ProposalStatus.READY_FOR_REVIEW, None, True)
    assert (after.customer, after.uploaded_at) == (before.customer, before.uploaded_at)


def test_tc_57_07_failed_ai_run_shows_mislukt_and_keeps_the_error(root, store):
    ref = store.create_proposal('Ostavel')

    store.set_status(ref, ProposalStatus.AI_GENERATING, AiStatus.FAILED, error='Gemini is overloaded (503).')

    [row] = store.list_proposals()
    assert row.ai_status is AiStatus.FAILED
    data = json.loads((root / 'ostavel' / 'v1' / 'proposal.json').read_text(encoding='utf-8'))
    assert data['error'] == 'Gemini is overloaded (503).'

    store.set_status(ref, ProposalStatus.READY_FOR_REVIEW, None)  # a later success removes the error
    data = json.loads((root / 'ostavel' / 'v1' / 'proposal.json').read_text(encoding='utf-8'))
    assert 'error' not in data


def test_tc_57_08_empty_customer_name_is_refused(store):
    with pytest.raises(ValueError):
        store.create_proposal('   ')


@pytest.mark.parametrize('customer, folder', [
    ('Ostavel', 'ostavel'),
    ('Voorbeeldbedrijf A', 'voorbeeldbedrijf-a'),
    ('Voorbeeldbedrijf Ä & Co', 'voorbeeldbedrijf-a-co'),
    ('  --Café--  ', 'cafe'),
    ('???', 'klant'),
])
def test_tc_57_01_customer_folder_name_is_safe_and_readable(customer, folder):
    assert customer_folder_name(customer) == folder
