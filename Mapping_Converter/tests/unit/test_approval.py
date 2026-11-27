import json
from datetime import UTC, datetime

import pytest

from scripts.errors import ProposalConflictError, ProposalNotFoundError
from services.approval import approve_proposal, clean_description
from services.statuses import ProposalStatus

AI_CHECKING_REVIEW = ProposalStatus.AI_CHECKING_REVIEW.value
NOW = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)


def write_metadata(root, status='In review', *, customer='nouryon', version='v1',
                   proposal_type='inbound', filename='metadata.json', **extra):
    folder = root / customer / version / proposal_type
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    path.write_text(json.dumps({'customer': 'Nouryon', 'status': status, **extra}), encoding='utf-8')
    return path


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


# --- happy path -------------------------------------------------------------

def test_approve_sets_ai_checking_review_and_stores_description(proposals_root, proposals_storage):
    path = write_metadata(proposals_root, uploaded_at='2026-11-19T09:00:00+00:00')

    result = approve_proposal(proposals_storage, 'nouryon', 'v1', 'inbound',
                              'Eerste versie voor Nouryon', now=NOW)

    data = read(path)
    assert data['status'] == AI_CHECKING_REVIEW
    assert data['approval_description'] == 'Eerste versie voor Nouryon'
    assert data['approved_at'] == '2026-11-20T10:00:00+00:00'
    assert data['uploaded_at'] == '2026-11-19T09:00:00+00:00'  # other fields are kept
    assert result.status == AI_CHECKING_REVIEW
    assert result.to_dict()['proposal_type'] == 'inbound'


@pytest.mark.parametrize('status', ['READY_FOR_REVIEW', 'IN_REVIEW', 'In review'])
def test_approvable_statuses(proposals_root, proposals_storage, status):
    write_metadata(proposals_root, status=status)
    assert approve_proposal(proposals_storage, 'nouryon', 'v1', 'inbound', 'Ok').status == AI_CHECKING_REVIEW


def test_description_is_stripped(proposals_root, proposals_storage):
    path = write_metadata(proposals_root)
    approve_proposal(proposals_storage, 'nouryon', 'v1', 'inbound', '  Kolom datum aangepast  ')
    assert read(path)['approval_description'] == 'Kolom datum aangepast'


def test_lookup_is_case_insensitive(proposals_root, proposals_storage):
    write_metadata(proposals_root, customer='Nouryon', proposal_type='Inbound')
    result = approve_proposal(proposals_storage, 'NOURYON', 'V1', 'inbound', 'Ok')
    assert (result.company, result.version, result.proposal_type) == ('Nouryon', 'v1', 'Inbound')


def test_proposal_json_is_used_when_metadata_json_is_missing(proposals_root, proposals_storage):
    path = write_metadata(proposals_root, filename='proposal.json')
    approve_proposal(proposals_storage, 'nouryon', 'v1', 'inbound', 'Ok')
    assert read(path)['status'] == AI_CHECKING_REVIEW


def test_metadata_json_wins_over_proposal_json(proposals_root, proposals_storage):
    preferred = write_metadata(proposals_root, filename='metadata.json')
    other = write_metadata(proposals_root, filename='proposal.json')
    approve_proposal(proposals_storage, 'nouryon', 'v1', 'inbound', 'Ok')
    assert read(preferred)['status'] == AI_CHECKING_REVIEW
    assert read(other)['status'] == 'In review'


# --- description ------------------------------------------------------------

@pytest.mark.parametrize('description', [None, '', '   ', '\t\n'])
def test_empty_description_is_allowed(description):
    assert clean_description(description) == ''


def test_description_of_200_characters_is_allowed():
    assert len(clean_description('a' * 200)) == 200


def test_description_longer_than_200_characters_is_rejected():
    with pytest.raises(ValueError, match='200'):
        clean_description('a' * 201)


def test_invalid_description_does_not_change_metadata(proposals_root, proposals_storage):
    path = write_metadata(proposals_root)
    with pytest.raises(ValueError):
        approve_proposal(proposals_storage, 'nouryon', 'v1', 'inbound', 'a' * 201)
    assert read(path)['status'] == 'In review'


# --- status -----------------------------------------------------------------

def test_cannot_approve_while_ai_review_is_running(proposals_root, proposals_storage):
    path = write_metadata(proposals_root, status=AI_CHECKING_REVIEW, approval_description='Eerste')
    with pytest.raises(ProposalConflictError, match='AI-controle is al bezig'):
        approve_proposal(proposals_storage, 'nouryon', 'v1', 'inbound', 'Tweede')
    assert read(path)['approval_description'] == 'Eerste'  # cannot be changed afterwards


@pytest.mark.parametrize('status', ['AI_GENERATING', 'RETURNED', None])
def test_other_statuses_cannot_be_approved(proposals_root, proposals_storage, status):
    write_metadata(proposals_root, status=status)
    with pytest.raises(ProposalConflictError):
        approve_proposal(proposals_storage, 'nouryon', 'v1', 'inbound', 'Ok')


def test_invalid_json_is_a_conflict(proposals_root, proposals_storage):
    path = write_metadata(proposals_root)
    path.write_text('{niet geldig', encoding='utf-8')
    with pytest.raises(ProposalConflictError, match='geen geldige JSON'):
        approve_proposal(proposals_storage, 'nouryon', 'v1', 'inbound', 'Ok')


# --- not found / invalid parameters -----------------------------------------

@pytest.mark.parametrize(('company', 'version', 'proposal_type'), [
    ('onbekend', 'v1', 'inbound'),
    ('nouryon', 'v9', 'inbound'),
    ('nouryon', 'v1', 'outbound'),
])
def test_unknown_proposal_is_not_found(proposals_root, proposals_storage, company, version, proposal_type):
    write_metadata(proposals_root)
    with pytest.raises(ProposalNotFoundError):
        approve_proposal(proposals_storage, company, version, proposal_type, 'Ok')


def test_folder_without_metadata_is_not_found(proposals_root, proposals_storage):
    (proposals_root / 'nouryon' / 'v1' / 'inbound').mkdir(parents=True)
    with pytest.raises(ProposalNotFoundError, match='Geen metadata'):
        approve_proposal(proposals_storage, 'nouryon', 'v1', 'inbound', 'Ok')


@pytest.mark.parametrize(('company', 'version', 'proposal_type', 'message'), [
    ('', 'v1', 'inbound', 'Bedrijf'),
    ('a' * 21, 'v1', 'inbound', 'Bedrijf'),
    ('nouryon', 'v1', '', 'Proposaltype'),
    ('nouryon', 'v1', 'a' * 21, 'Proposaltype'),
    ('nouryon', '1', 'inbound', 'Versie'),
    ('nouryon', 'versie1', 'inbound', 'Versie'),
])
def test_invalid_parameters_are_rejected(proposals_storage, company, version, proposal_type, message):
    with pytest.raises(ValueError, match=message):
        approve_proposal(proposals_storage, company, version, proposal_type, 'Ok')
