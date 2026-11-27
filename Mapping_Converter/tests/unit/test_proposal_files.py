import json

import pytest

from scripts.errors import ProposalConflictError, ProposalNotFoundError
from services.proposal_files import (
    ProposalLocation,
    find_proposal,
    read_metadata,
    validate_reference,
    write_metadata,
)
from services.statuses import APPROVABLE_STATUSES, ProposalStatus


def make_proposal(root, customer='Nouryon', version='v1', proposal_type='inbound', filename='metadata.json'):
    folder = root / customer / version / proposal_type
    folder.mkdir(parents=True, exist_ok=True)
    (folder / filename).write_text(json.dumps({'status': 'In review'}), encoding='utf-8')
    return folder / filename


def test_validate_reference_trims_the_parameters():
    assert validate_reference(' nouryon ', ' v1 ', ' inbound ') == ('nouryon', 'v1', 'inbound')


def test_find_proposal_returns_the_real_folder_names(proposals_root, proposals_storage):
    make_proposal(proposals_root)

    with proposals_storage.session() as s:
        location = find_proposal(s, 'NOURYON', 'V1', 'Inbound')

    assert location == ProposalLocation('Nouryon', 'v1', 'inbound', 'Nouryon/v1/inbound/metadata.json')
    assert location.folder == 'Nouryon/v1/inbound'


def test_read_and_write_metadata_round_trip(proposals_root, proposals_storage):
    path = make_proposal(proposals_root, filename='proposal.json')

    with proposals_storage.session() as s:
        location = find_proposal(s, 'nouryon', 'v1', 'inbound')
        data = read_metadata(s, location)
        data['status'] = ProposalStatus.RETURNED.value
        write_metadata(s, location, data)

    assert json.loads(path.read_text(encoding='utf-8')) == {'status': 'RETURNED'}


def test_metadata_that_is_not_an_object_is_a_conflict(proposals_root, proposals_storage):
    path = make_proposal(proposals_root)
    path.write_text('[1, 2, 3]', encoding='utf-8')

    with proposals_storage.session() as s, pytest.raises(ProposalConflictError, match='JSON-object'):
        read_metadata(s, find_proposal(s, 'nouryon', 'v1', 'inbound'))


def test_missing_customer_folder_is_not_found(proposals_storage):
    with proposals_storage.session() as s, pytest.raises(ProposalNotFoundError, match='Bedrijf'):
        find_proposal(s, 'onbekend', 'v1', 'inbound')


def test_statuses_compare_equal_to_the_codes_in_the_metadata():
    assert ProposalStatus.AI_CHECKING_REVIEW == 'AI_CHECKING_REVIEW'
    assert {'READY_FOR_REVIEW', 'IN_REVIEW', 'In review'} == set(APPROVABLE_STATUSES)
    assert 'RETURNED' not in APPROVABLE_STATUSES


def test_delete_proposal_after_conversion_removes_whole_customer_folder(proposals_root, proposals_storage):
    from services.proposal_files import delete_proposal_after_conversion

    make_proposal(proposals_root, customer='Nouryon', version='v1', proposal_type='inbound')

    with proposals_storage.session() as s:
        delete_proposal_after_conversion(s, 'Nouryon', 'v1', 'inbound')

    assert not (proposals_root / 'Nouryon').exists()


def test_delete_proposal_after_conversion_preserves_other_type(proposals_root, proposals_storage):
    from services.proposal_files import delete_proposal_after_conversion

    make_proposal(proposals_root, customer='Nouryon', version='v1', proposal_type='inbound')
    make_proposal(proposals_root, customer='Nouryon', version='v1', proposal_type='outbound')

    with proposals_storage.session() as s:
        delete_proposal_after_conversion(s, 'Nouryon', 'v1', 'inbound')

    assert not (proposals_root / 'Nouryon' / 'v1' / 'inbound').exists()
    assert (proposals_root / 'Nouryon' / 'v1' / 'outbound').exists()
    assert (proposals_root / 'Nouryon').exists()


def test_delete_proposal_after_conversion_nonexistent_customer(proposals_storage):
    from services.proposal_files import delete_proposal_after_conversion

    with proposals_storage.session() as s:
        delete_proposal_after_conversion(s, 'nonexistent', 'v1', 'inbound')

