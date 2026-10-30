"""Fit criteria: the AI makes a mapping proposal for an uploaded XML.

  FC1  Voor elke geüploade XML maakt de AI een mappingproposal voor de ingevulde klant.
  FC2  Het Excel-voorstel wordt opgeslagen in de map proposals/ van die klant op SFTP.
  FC3  Zodra de AI klaar is, krijgt de proposal in de lijst op Home de status
       "Klaar om na te kijken".
  TC   Na een geslaagde upload staat er een nieuwe rij in de lijst op Home met de klantnaam,
       de versie, de datum en tijd van upload en de status "AI maakt voorstel".
       Techniek: equivalence partitioning (geldig bestand). Voorwaarde: TC-60-01 net uitgevoerd.
       Testdata: order_ostavel.xml, klantnaam Ostavel.

An upload arrives the way the upload story delivers it: one folder in the incoming folder
with the XML file(s) and, written last, upload.json with the customer name. The watcher
(services/incoming_watcher.py) then starts the AI automatically.

The real pipeline runs (reading the XML, validating, building the Excel from the template);
only Gemini is replaced by a fake answer, so the tests are free and always give the same
result. The SFTP share is a temporary folder with the same layout (see services/proposals.py).
How the Home page shows these statuses is tested in
Frontend/src/__tests__/functional/ProposalOverview.fitcriteria.test.tsx.
"""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil

from openpyxl import load_workbook
import pytest

import scripts.pipeline as pipeline
from services.incoming_watcher import IncomingWatcher
from scripts.models import MappingSettings
from services.proposal_runner import workbook_name
from services.proposals import AiStatus, ProposalStatus, ProposalStore

FIXTURES = Path(__file__).resolve().parent.parent / 'fixtures'
OSTAVEL_XML = FIXTURES / 'source' / 'order_ostavel.xml'
SETTINGS = MappingSettings(history_pairs=1, source_samples=2, limit_targets=0)


class FakeGemini:
    """Stands in for Gemini: proposes a DIRECT mapping for every requested target field
    and remembers which customer XML files it received."""

    def __init__(self):
        self.received_xml_files = []
        self.on_call = None

    def __call__(self, source_fields, target_fields, reference_examples=None, **kwargs):
        self.received_xml_files.append(sorted(doc['filename'] for doc in kwargs['source_documents']))
        if self.on_call:
            self.on_call()
        source = next(f['path'] for f in source_fields if f['path'].endswith('/OrderNumber'))
        return [{
            'source_path': source, 'target_path': target['path'], 'rule_type': 'DIRECT',
            'confidence': 80, 'requires_review': True, 'review_priority': 'Medium',
            'reason': 'Test proposal', 'evidence': '', 'fixed_value': '', 'transformation': '',
            'condition': '', 'lookup': '', 'loop': '', 'review_question': 'Klopt dit?',
            'risk_category': '',
        } for target in target_fields]


@pytest.fixture
def sftp(tmp_path):
    """The proposals/ folder on the SFTP share (a temporary folder in the tests)."""
    return ProposalStore(tmp_path / 'sftp-shared' / 'proposals')


@pytest.fixture
def ai(tmp_path, monkeypatch):
    """Real pipeline with test data: small historical example, output in tmp, fake Gemini."""
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.setattr(pipeline, 'HISTORICAL_DIR', FIXTURES / 'historical')
    monkeypatch.setattr(pipeline, 'ROOT', tmp_path)
    monkeypatch.setattr(pipeline, 'RUNS_DIR', tmp_path / 'output' / 'runs')
    gemini = FakeGemini()
    monkeypatch.setattr(pipeline, 'run_gemini', gemini)
    return gemini


@pytest.fixture
def incoming(tmp_path):
    return tmp_path / 'incoming'


@pytest.fixture
def watcher(incoming, sftp, ai):
    return IncomingWatcher(incoming, sftp, SETTINGS)


def upload(incoming: Path, upload_id: str, customer: str, *xml_files: Path, complete: bool = True) -> Path:
    """Simulates TC-60-01: the upload story stores the files, then upload.json as the last step."""
    folder = incoming / upload_id
    folder.mkdir(parents=True)
    for file in xml_files:
        shutil.copy(file, folder / file.name)
    if complete:
        (folder / 'upload.json').write_text(json.dumps({'customer': customer}), encoding='utf-8')
    return folder


def xml_variant(tmp_path, name: str, order_number: str) -> Path:
    """Another valid interface: same structure as order_ostavel.xml, other order number."""
    file = tmp_path / name
    file.write_text(OSTAVEL_XML.read_text(encoding='utf-8').replace('SO-OST-0001', order_number), encoding='utf-8')
    return file


def test_fc1_ai_makes_a_mapping_proposal_for_each_upload_for_the_entered_customer(tmp_path, incoming, sftp, ai, watcher):
    # One upload with two XML files, one upload with one XML file.
    upload(incoming, 'upload-1', 'Ostavel', OSTAVEL_XML, xml_variant(tmp_path, 'order_ostavel_2.xml', 'SO-OST-0002'))
    upload(incoming, 'upload-2', 'Klant B', xml_variant(tmp_path, 'order_klant_b.xml', 'SO-KLB-0042'))

    assert watcher.run_once() == 2  # started automatically, nobody ran a command

    # One proposal per upload, each for the customer that was entered.
    assert sorted(p.customer for p in sftp.list_proposals()) == ['Klant B', 'Ostavel']
    # The AI analysed exactly the XML file(s) of that upload: both files of the first upload together.
    assert sorted(ai.received_xml_files) == [['order_klant_b.xml'], ['order_ostavel.xml', 'order_ostavel_2.xml']]
    # Handled uploads are moved away, so they never start a second time.
    assert watcher.run_once() == 0
    assert sorted(p.name for p in (incoming / 'processed').iterdir()) == ['upload-1', 'upload-2']


def test_fc1_upload_starts_only_when_complete(incoming, sftp, watcher):
    folder = upload(incoming, 'upload-1', 'Ostavel', OSTAVEL_XML, complete=False)  # still uploading

    assert watcher.run_once() == 0
    assert sftp.list_proposals() == []

    (folder / 'upload.json').write_text(json.dumps({'customer': 'Ostavel'}), encoding='utf-8')
    assert watcher.run_once() == 1
    assert [p.customer for p in sftp.list_proposals()] == ['Ostavel']


def test_fc2_excel_proposal_is_saved_in_the_proposals_folder_of_that_customer(incoming, sftp, watcher):
    upload(incoming, 'upload-1', 'Ostavel', OSTAVEL_XML)

    watcher.run_once()

    excel = sftp.root / 'ostavel' / 'v1' / 'MProposal-Ostavel_V1.xlsx'  # naming convention
    assert excel.is_file()
    sheet = load_workbook(excel)['Mapping Proposal']
    headers = [cell.value for cell in sheet[2]]
    first_row = dict(zip(headers, (cell.value for cell in sheet[3])))
    assert first_row['Source full path'] == '/OutboundOrder/Head/OrderNumber'  # from order_ostavel.xml
    assert first_row['Proposed rule type'] == 'DIRECT'
    # Only the Excel goes to SFTP, only in the folder of this customer; the XML stays off SFTP.
    on_sftp = [p.relative_to(sftp.root).as_posix() for p in sftp.root.rglob('*') if p.is_file()]
    assert sorted(on_sftp) == ['ostavel/v1/MProposal-Ostavel_V1.xlsx', 'ostavel/v1/proposal.json']


def test_fc3_status_becomes_ready_for_review_when_the_ai_is_done(incoming, sftp, watcher):
    upload(incoming, 'upload-1', 'Ostavel', OSTAVEL_XML)

    watcher.run_once()

    [row] = sftp.list_proposals()
    assert row.status is ProposalStatus.READY_FOR_REVIEW  # "Klaar om na te kijken"
    assert row.ai_status is None
    assert row.can_open is True


def test_tc_new_row_after_upload_with_name_version_date_and_ai_maakt_voorstel(tmp_path, incoming, sftp, ai, watcher):
    """Testdata: order_ostavel.xml, klantnaam Ostavel. Checked while the AI is still working."""
    rows_during_ai = []
    ai.on_call = lambda: rows_during_ai.append({p.customer: p.to_dict() for p in sftp.list_proposals()})
    upload(incoming, 'upload-1', 'Ostavel', OSTAVEL_XML)
    upload(incoming, 'upload-2', 'Klant B', xml_variant(tmp_path, 'order_klant_b.xml', 'SO-KLB-0042'))
    upload_moment = datetime.now(timezone.utc).replace(microsecond=0)

    watcher.run_once()

    # While the AI works on the first upload, both uploads already have their row.
    rows = rows_during_ai[0]
    assert set(rows) == {'Ostavel', 'Klant B'}
    row = rows['Ostavel']
    assert row['version'] == 1
    uploaded_at = datetime.fromisoformat(row['uploaded_at'])
    assert upload_moment - timedelta(seconds=1) <= uploaded_at <= upload_moment + timedelta(minutes=1)
    assert row['status'] == ProposalStatus.AI_GENERATING.value  # "AI maakt voorstel"
    assert row['ai_status'] == AiStatus.RUNNING.value


@pytest.mark.parametrize('customer, version, expected', [
    ('Brunos', 2, 'MProposal-Brunos_V2.xlsx'),               # the example of the naming convention
    ('Ostavel', 1, 'MProposal-Ostavel_V1.xlsx'),
    ('Voorbeeldbedrijf A', 1, 'MProposal-VoorbeeldbedrijfA_V1.xlsx'),
    ('Café Ärger & Co.', 10, 'MProposal-CafeArgerCo_V10.xlsx'),
])
def test_fc2_excel_file_name_follows_the_naming_convention(customer, version, expected):
    assert workbook_name(customer, version) == expected
