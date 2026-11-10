"""Reading and writing mapping proposals on the shared storage (the SFTP server).

Layout on the storage: one folder per customer, one subfolder per version.

    <SFTP_SHARED_REMOTE_DIR>/proposals/
        voorbeeldbedrijf-a/
            v1/
                proposal.json        metadata shown in the overview (required)
                MProposal-<Klant>_V<N>.xlsx  the AI result (the uploaded XML is not stored on SFTP)
            v2/
                proposal.json

The files live on the shared SFTPGo server of the infrastructure (sftp-shared, see
Kubernetes/base/shared-storage/sftp-shared.yaml); this service connects to it directly
over SFTP (services/storage.py). Locally, when SFTP_SHARED_HOST is not set, the same
layout lives in data/sftp-shared/proposals/ (see scripts/dev_seed.py for example data).

Example proposal.json:
    {
      "customer": "Voorbeeldbedrijf A",
      "uploaded_at": "2026-10-22T14:05:00+02:00",
      "status": "AI_GENERATING",
      "ai_status": "RUNNING"
    }
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import json
import logging
from pathlib import Path
import re
import unicodedata

from .storage import LocalStorage, Storage, StorageSession

logger = logging.getLogger(__name__)

# Name of the metadata file inside every version folder.
METADATA_FILE = 'proposal.json'

# Version folders are named v1, v2, v3, ...
_VERSION_FOLDER = re.compile(r'^v(\d+)$')


class ProposalStatus(str, Enum):
    """Workflow status of a proposal. The frontend translates these codes to labels."""

    AI_GENERATING = 'AI_GENERATING'            # "AI maakt voorstel"
    READY_FOR_REVIEW = 'READY_FOR_REVIEW'      # "Klaar om na te kijken"
    IN_REVIEW = 'IN_REVIEW'                    # "In review"
    AI_CHECKING_REVIEW = 'AI_CHECKING_REVIEW'  # "AI controleert review van analist"
    RETURNED = 'RETURNED'                      # "Teruggestuurd"


class AiStatus(str, Enum):
    """What the AI is doing for this proposal. ``None`` means nothing ("—" in the UI)."""

    RUNNING = 'RUNNING'  # "Bezig"
    FAILED = 'FAILED'    # "Mislukt"


@dataclass(frozen=True)
class ProposalSummary:
    """One row of the proposals overview."""

    id: str                 # "<customer folder>/v<version>", unique on the share
    customer: str
    version: int
    uploaded_at: datetime   # always timezone-aware
    status: ProposalStatus
    ai_status: AiStatus | None

    @property
    def can_open(self) -> bool:
        # While the AI is still writing the first proposal there is nothing to open yet.
        return self.status is not ProposalStatus.AI_GENERATING

    def to_dict(self) -> dict:
        """JSON-ready representation, used by the API response."""
        return {
            'id': self.id,
            'customer': self.customer,
            'version': self.version,
            'uploaded_at': self.uploaded_at.isoformat(),
            'status': self.status.value,
            'ai_status': self.ai_status.value if self.ai_status else None,
            'can_open': self.can_open,
        }


@dataclass(frozen=True)
class ProposalRef:
    """A proposal version that was created on the shared storage (used while the AI runs)."""

    customer: str
    version: int
    folder: str             # "<customer folder>/v<version>", relative to the proposals root

    @property
    def id(self) -> str:
        return self.folder


def customer_folder_name(customer: str) -> str:
    """Folder name for a customer: 'Voorbeeldbedrijf Ä & Co' -> 'voorbeeldbedrijf-a-co'."""
    ascii_name = unicodedata.normalize('NFKD', customer).encode('ascii', 'ignore').decode('ascii')
    slug = re.sub(r'[^a-z0-9]+', '-', ascii_name.lower()).strip('-')
    return slug or 'klant'


class ProposalStore:
    """Reads and writes proposals with the layout described above.

    ``storage`` is the SFTP server (services/storage.SftpStorage) or, locally and in the
    tests, a folder: a Path is wrapped in a LocalStorage.
    """

    def __init__(self, storage: Storage | Path | str):
        self.storage = LocalStorage(Path(storage)) if isinstance(storage, (str, Path)) else storage

    @property
    def root(self):
        """Root of the proposals (a Path for a local folder, a remote path for SFTP)."""
        return self.storage.root

    # -- Writing (used by the AI run, see services/proposal_runner.py) -----------------

    def create_proposal(self, customer: str) -> ProposalRef:
        """Create the next version folder for this customer with status 'AI is generating'.

        The overview shows the new row immediately, while the AI is still working.
        """
        customer = customer.strip()
        if not customer:
            raise ValueError('customer name is empty')
        customer_dir = customer_folder_name(customer)
        with self.storage.session() as s:
            s.make_dirs(customer_dir)
            existing = [int(m.group(1)) for name in s.list_dirs(customer_dir)
                        if (m := _VERSION_FOLDER.fullmatch(name))]
            version = max(existing, default=0) + 1
            # Creating a folder that exists fails: if another run took this number, try the next.
            while not s.make_dir(f'{customer_dir}/v{version}'):
                version += 1
            folder = f'{customer_dir}/v{version}'
            now = datetime.now(timezone.utc).isoformat(timespec='seconds')
            _write_metadata(s, folder, {
                'customer': customer, 'uploaded_at': now, 'updated_at': now,
                'status': ProposalStatus.AI_GENERATING.value, 'ai_status': AiStatus.RUNNING.value,
            })
        return ProposalRef(customer=customer, version=version, folder=folder)

    def set_status(self, ref: ProposalRef, status: ProposalStatus,
                   ai_status: AiStatus | None, *, error: str = '') -> None:
        """Update status and AI status, keeping the other metadata (customer, upload time)."""
        with self.storage.session() as s:
            data = json.loads(s.read_text(f'{ref.folder}/{METADATA_FILE}'))
            data.update({
                'status': status.value,
                'ai_status': ai_status.value if ai_status else None,
                'updated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            })
            if error:
                data['error'] = error  # short message for analysts/logs; not shown in the overview yet
            else:
                data.pop('error', None)
            _write_metadata(s, ref.folder, data)

    def save_file(self, ref: ProposalRef, local_path: Path, name: str) -> None:
        """Upload a file (the Excel proposal) into the version folder of ``ref``."""
        with self.storage.session() as s:
            s.upload_file(Path(local_path), f'{ref.folder}/{name}')

    def exists(self, ref: ProposalRef) -> bool:
        """Whether the proposal.json of ``ref`` exists on the storage."""
        with self.storage.session() as s:
            return s.exists(f'{ref.folder}/{METADATA_FILE}')

    # -- Reading ----------------------------------------------------------------------

    def list_proposals(self, *, all_versions: bool = False) -> list[ProposalSummary]:
        """All proposals, newest upload first.

        By default only the latest version of each customer is returned (one row
        per customer, as on the Home page). ``all_versions=True`` returns every version.
        Folders with missing or invalid metadata are skipped with a warning, so one
        broken upload never breaks the whole overview.
        """
        proposals = []
        with self.storage.session() as s:
            customers = s.list_dirs('')
            if not customers:
                # Nothing has been uploaded yet: an empty overview, not an error.
                logger.info('No proposals yet on %s', self.storage.describe())
            for customer_dir in customers:
                versions = self._read_customer(s, customer_dir)
                if not versions:
                    continue
                if all_versions:
                    proposals.extend(versions)
                else:
                    proposals.append(max(versions, key=lambda p: p.version))

        # Newest first; customer name and version make the order stable.
        proposals.sort(key=lambda p: (p.uploaded_at, p.customer.casefold(), p.version), reverse=True)
        return proposals

    def _read_customer(self, s: StorageSession, customer_dir: str) -> list[ProposalSummary]:
        result = []
        for name in s.list_dirs(customer_dir):
            match = _VERSION_FOLDER.fullmatch(name)
            if not match:
                continue  # other folders next to the versions are ignored
            try:
                path = f'{customer_dir}/{name}/{METADATA_FILE}'
                if not s.exists(path):
                    raise ValueError(f'{METADATA_FILE} is missing')
                result.append(_read_metadata(customer_dir, int(match.group(1)), s.read_text(path)))
            except (OSError, ValueError, TypeError) as error:
                logger.warning('Skipping proposal %s/%s: %s', customer_dir, name, error)
        return result


def _read_metadata(customer_folder: str, version: int, text: str) -> ProposalSummary:
    """Parse the proposal.json of one version folder. Raises ValueError when invalid."""
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f'{METADATA_FILE} must contain a JSON object')

    try:
        status = ProposalStatus(data.get('status'))
    except ValueError:
        raise ValueError(f'unknown status {data.get("status")!r}') from None
    ai_value = data.get('ai_status')
    try:
        ai_status = AiStatus(ai_value) if ai_value else None
    except ValueError:
        raise ValueError(f'unknown ai_status {ai_value!r}') from None

    return ProposalSummary(
        id=f'{customer_folder}/v{version}',
        # The display name falls back to the folder name when "customer" is missing.
        customer=str(data.get('customer') or customer_folder).strip(),
        # The folder name is the source of truth for the version number.
        version=version,
        uploaded_at=_parse_timestamp(data.get('uploaded_at')),
        status=status,
        ai_status=ai_status,
    )


def _parse_timestamp(value) -> datetime:
    """ISO 8601 timestamp. 'Z' is accepted; a time without timezone is taken as UTC."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError('uploaded_at is missing')
    text = value.strip()
    if text.endswith(('Z', 'z')):
        text = text[:-1] + '+00:00'  # Python 3.10 does not understand 'Z'
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(f'uploaded_at is not an ISO 8601 timestamp: {value!r}') from None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def _write_metadata(s: StorageSession, folder: str, data: dict) -> None:
    """Write proposal.json atomically, so the API never reads a half-written file."""
    s.write_text(f'{folder}/{METADATA_FILE}', json.dumps(data, indent=2, ensure_ascii=False))
