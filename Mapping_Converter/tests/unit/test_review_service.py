"""Loading a proposal workbook from the storage for the AI review (services/review.py)."""
import json

import pytest

from scripts.errors import ProposalNotFoundError
from services.review import ProposalWorkbook, load_proposal_workbook, review_workbook


def store(root, files, metadata=None):
    folder = root / 'nouryon' / 'v2' / 'inbound'
    folder.mkdir(parents=True)
    (folder / 'metadata.json').write_text(json.dumps(metadata or {}), encoding='utf-8')
    for name, data in files.items():
        (folder / name).write_bytes(data)


def test_loads_the_workbook_of_the_proposal(proposals_storage, proposals_root):
    store(proposals_root, {'MProposal-Nouryon_V2.xlsx': b'excel'})

    workbook = load_proposal_workbook(proposals_storage, 'Nouryon', 'v2', 'Inbound')

    assert workbook == ProposalWorkbook('nouryon/v2/inbound/MProposal-Nouryon_V2.xlsx', b'excel')


def test_version_number_without_prefix(proposals_storage, proposals_root):
    store(proposals_root, {'MProposal-Nouryon_V2.xlsx': b'excel'})
    assert load_proposal_workbook(proposals_storage, 'nouryon', '2', 'inbound').contents == b'excel'


def test_invalid_version_raises_value_error(proposals_storage):
    with pytest.raises(ValueError):
        load_proposal_workbook(proposals_storage, 'nouryon', 'latest', 'inbound')


def test_missing_workbook_raises_not_found(proposals_storage, proposals_root):
    store(proposals_root, {})
    with pytest.raises(ProposalNotFoundError):
        load_proposal_workbook(proposals_storage, 'nouryon', 'v2', 'inbound')


def test_review_workbook_passes_the_contents_to_the_pipeline(monkeypatch):
    seen = []
    def fake_run_review(contents):
        seen.append(contents)
        return {'decision': 'ACCEPTED'}

    monkeypatch.setattr('services.review.run_review', fake_run_review)

    assert review_workbook(ProposalWorkbook('a.xlsx', b'excel')) == {'decision': 'ACCEPTED'}
    assert seen == [b'excel']
