"""AI review of an approved proposal -> mapping package or back to the analyst (story 187).

The AI review is always a fake: ``review=`` is passed to finalize_proposal.
"""
import json
from datetime import UTC, datetime

import pytest

from scripts.errors import ProposalConflictError, ProposalNotFoundError
from scripts.excel_review import InvalidWorkbook
from scripts.gemini_review import ReviewUnavailable
from services.finalization import INVALID_WORKBOOK, finalize_proposal

NOW = datetime(2026, 11, 20, 15, 0, tzinfo=UTC)
STAMP = '2026-11-20T15:00:00+00:00'


@pytest.fixture
def approved(proposals_root, mapping_excel):
    """Nouryon/v2/inbound approved by the analyst; returns the metadata path."""
    folder = proposals_root / 'Nouryon' / 'v2' / 'inbound'
    folder.mkdir(parents=True)
    (folder / 'MProposal-Nouryon_V2.xlsx').write_bytes(mapping_excel)
    metadata = folder / 'metadata.json'
    metadata.write_text(json.dumps({
        'customer': 'Nouryon',
        'status': 'AI_CHECKING_REVIEW',
        'filename': 'MProposal-Nouryon_V2.xlsx',
        'approval_description': 'Leverdatum mapt nu op DeliveryDate',
        'approved_at': '2026-11-20T14:00:00+00:00',
    }), encoding='utf-8')
    return metadata


def reviewer(decision, summary='ok', findings=()):
    def review(contents):
        assert contents.startswith(b'PK')  # the stored workbook (an .xlsx is a zip file)
        return {'decision': decision, 'summary': summary, 'findings': list(findings), 'checked_mappings': 1}
    return review


def failing(error):
    def review(_contents):
        raise error
    return review


def run(proposals_storage, packages_storage, review):
    return finalize_proposal(proposals_storage, packages_storage, 'nouryon', 'v2', 'inbound', review=review, now=NOW)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


# ---------------------------------------------------------------------------
# ACCEPTED
# ---------------------------------------------------------------------------
def test_accepted_stores_the_package_as_new_version(proposals_storage, packages_storage, packages_root, approved):
    result = run(proposals_storage, packages_storage, reviewer('ACCEPTED'))

    package = read(packages_root / 'nouryon' / 'v2' / 'inbound' / 'MPackage.json')
    assert package['mappings'] == [{'source_path': '/SOURCE/HEADER/ID', 'target_path': '/TARGET/HDR/DOC_ID'}]
    assert package['meta']['package_version'] == '2.0.0'
    assert package['meta']['description'] == 'Leverdatum mapt nu op DeliveryDate'
    assert package['meta']['approved_at'] == '2026-11-20T14:00:00+00:00'
    assert package['meta']['date_created'] == STAMP
    assert result.status == 'APPROVED'
    assert result.package_path.endswith('/nouryon/v2/inbound/MPackage.json')


def test_accepted_makes_it_the_active_version(proposals_storage, packages_storage, packages_root, approved):
    run(proposals_storage, packages_storage, reviewer('ACCEPTED'))

    active = read(packages_root / 'nouryon' / 'active.json')
    assert active == {'inbound': {'version': 'v2', 'updated_at': STAMP, 'updated_by': 'analist_a'}}


def test_other_types_keep_their_active_version(proposals_storage, packages_storage, packages_root, approved):
    """Same file as Version_Control writes: one entry per package type."""
    active_file = packages_root / 'nouryon' / 'active.json'
    active_file.parent.mkdir(parents=True)
    outbound = {'version': 'v1', 'updated_at': '2026-11-01T10:00:00Z', 'updated_by': 'analist_b'}
    active_file.write_text(json.dumps({'outbound': outbound, 'inbound': {'version': 'v1'}}), encoding='utf-8')

    run(proposals_storage, packages_storage, reviewer('ACCEPTED'))

    active = read(active_file)
    assert active['outbound'] == outbound
    assert active['inbound']['version'] == 'v2'


def test_unreadable_active_file_is_replaced(proposals_storage, packages_storage, packages_root, approved):
    active_file = packages_root / 'nouryon' / 'active.json'
    active_file.parent.mkdir(parents=True)
    active_file.write_text('not json', encoding='utf-8')

    run(proposals_storage, packages_storage, reviewer('ACCEPTED'))

    assert read(active_file)['inbound']['version'] == 'v2'


def test_accepted_sets_the_proposal_to_approved(proposals_storage, packages_storage, approved):
    run(proposals_storage, packages_storage, reviewer('ACCEPTED', summary='Consistent'))

    data = read(approved)
    assert data['status'] == 'APPROVED'
    assert data['ai_status'] is None
    assert data['ai_review'] == {'decision': 'ACCEPTED', 'summary': 'Consistent', 'findings': [],
                                 'checked_mappings': 1, 'checked_at': STAMP}
    assert data['package_path'].endswith('/nouryon/v2/inbound/MPackage.json')
    assert data['approval_description'] == 'Leverdatum mapt nu op DeliveryDate'  # other fields are kept
    assert data['updated_at'] == STAMP


def test_existing_package_is_never_overwritten(proposals_storage, packages_storage, packages_root, approved):
    existing = packages_root / 'nouryon' / 'v2' / 'inbound' / 'MPackage.json'
    existing.parent.mkdir(parents=True)
    existing.write_text('{"old": true}', encoding='utf-8')

    with pytest.raises(ProposalConflictError):
        run(proposals_storage, packages_storage, reviewer('ACCEPTED'))

    assert read(existing) == {'old': True}
    assert read(approved)['status'] == 'AI_CHECKING_REVIEW'


# ---------------------------------------------------------------------------
# REJECTED / invalid workbook / no review
# ---------------------------------------------------------------------------
def test_rejected_returns_the_proposal_with_findings(proposals_storage, packages_storage, packages_root, approved):
    result = run(proposals_storage, packages_storage, reviewer('REJECTED', 'Conflict', ['Rij 3: dubbel doelveld']))

    data = read(approved)
    assert data['status'] == 'RETURNED'
    assert data['ai_status'] == 'FAILED'
    assert data['ai_review']['decision'] == 'REJECTED'
    assert data['ai_review']['findings'] == ['Rij 3: dubbel doelveld']
    assert result.status == 'RETURNED'
    assert result.findings == ['Rij 3: dubbel doelveld']
    assert list(packages_root.iterdir()) == []  # no package, no active version


def test_unknown_decision_is_never_an_acceptance(proposals_storage, packages_storage, packages_root, approved):
    assert run(proposals_storage, packages_storage, reviewer('MAYBE')).status == 'RETURNED'
    assert list(packages_root.iterdir()) == []


def test_invalid_workbook_returns_the_proposal(proposals_storage, packages_storage, approved):
    result = run(proposals_storage, packages_storage, failing(InvalidWorkbook('Missing "Mapping Proposal" worksheet.')))

    data = read(approved)
    assert data['status'] == 'RETURNED'
    assert data['ai_review']['summary'] == INVALID_WORKBOOK
    assert data['ai_review']['findings'] == ['Missing "Mapping Proposal" worksheet.']
    assert result.status == 'RETURNED'


@pytest.mark.parametrize('error', [ReviewUnavailable('quota'), RuntimeError('boom')])
def test_unavailable_review_changes_nothing(proposals_storage, packages_storage, packages_root, approved, error):
    """The caller (routers/approve.py) marks the review as failed; /ai-retry restarts it."""
    before = read(approved)

    with pytest.raises(type(error)):
        run(proposals_storage, packages_storage, failing(error))

    assert read(approved) == before
    assert list(packages_root.iterdir()) == []


def test_old_review_error_is_cleared_on_the_next_run(proposals_storage, packages_storage, approved):
    data = read(approved)
    data['ai_status'] = 'FAILED'
    data['ai_review_error'] = 'Gemini 503'
    approved.write_text(json.dumps(data), encoding='utf-8')

    run(proposals_storage, packages_storage, reviewer('ACCEPTED'))

    assert 'ai_review_error' not in read(approved)


# ---------------------------------------------------------------------------
# Preconditions
# ---------------------------------------------------------------------------
def test_only_a_proposal_in_ai_review_is_processed(proposals_storage, packages_storage, approved):
    data = read(approved)
    data['status'] = 'IN_REVIEW'
    approved.write_text(json.dumps(data), encoding='utf-8')

    with pytest.raises(ProposalConflictError):
        run(proposals_storage, packages_storage, reviewer('ACCEPTED'))


def test_unknown_proposal_is_not_found(proposals_storage, packages_storage):
    with pytest.raises(ProposalNotFoundError):
        run(proposals_storage, packages_storage, reviewer('ACCEPTED'))


def test_result_to_dict(proposals_storage, packages_storage, approved):
    result = run(proposals_storage, packages_storage, reviewer('REJECTED', 'x', ['y'])).to_dict()
    assert result == {'company': 'Nouryon', 'version': 'v2', 'proposal_type': 'inbound', 'status': 'RETURNED',
                      'summary': 'x', 'findings': ['y'], 'package_path': None}
