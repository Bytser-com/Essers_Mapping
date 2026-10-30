"""Reading mapping proposals from the shared storage (the SFTP share).

Layout on the share: one folder per customer, one subfolder per version.

    <SHARED_MOUNT_PATH>/proposals/
        voorbeeldbedrijf-a/
            v1/
                proposal.json        metadata shown in the overview (required)
                MProposal-<Klant>_V<N>.xlsx  the AI result (the uploaded XML is not stored on SFTP)
            v2/
                proposal.json

In Kubernetes the SFTP share is mounted into this container as a normal folder
(SHARED_MOUNT_PATH=/mnt/sftp-shared, see Kubernetes/base/preparation/mapping-proposal.yaml),
so no SFTP client is needed to read it. Locally, while there is no SFTP server yet,
the same layout lives in data/sftp-shared/ (see scripts/dev_seed.py for example data).

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
import os
from pathlib import Path
import re
import unicodedata

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
    folder: Path            # <root>/<customer folder>/v<version>

    @property
    def id(self) -> str:
        return f'{self.folder.parent.name}/v{self.version}'


def customer_folder_name(customer: str) -> str:
    """Folder name for a customer: 'Voorbeeldbedrijf Ä & Co' -> 'voorbeeldbedrijf-a-co'."""
    ascii_name = unicodedata.normalize('NFKD', customer).encode('ascii', 'ignore').decode('ascii')
    slug = re.sub(r'[^a-z0-9]+', '-', ascii_name.lower()).strip('-')
    return slug or 'klant'


class ProposalStore:
    """Reads and writes proposal metadata in a folder with the layout described above."""

    def __init__(self, root: Path):
        self.root = Path(root)

    # -- Writing (used by the AI run, see services/proposal_runner.py) -----------------

    def create_proposal(self, customer: str) -> ProposalRef:
        """Create the next version folder for this customer with status 'AI is generating'.

        The overview shows the new row immediately, while the AI is still working.
        """
        customer = customer.strip()
        if not customer:
            raise ValueError('customer name is empty')
        customer_dir = self.root / customer_folder_name(customer)
        customer_dir.mkdir(parents=True, exist_ok=True)
        existing = [int(m.group(1)) for p in customer_dir.iterdir()
                    if (m := _VERSION_FOLDER.fullmatch(p.name))]
        version = max(existing, default=0) + 1
        # mkdir without exist_ok is atomic: if another run took this number, try the next.
        while True:
            folder = customer_dir / f'v{version}'
            try:
                folder.mkdir()
                break
            except FileExistsError:
                version += 1
        now = datetime.now(timezone.utc).isoformat(timespec='seconds')
        _write_metadata(folder, {
            'customer': customer, 'uploaded_at': now, 'updated_at': now,
            'status': ProposalStatus.AI_GENERATING.value, 'ai_status': AiStatus.RUNNING.value,
        })
        return ProposalRef(customer=customer, version=version, folder=folder)

    def set_status(self, ref: ProposalRef, status: ProposalStatus,
                   ai_status: AiStatus | None, *, error: str = '') -> None:
        """Update status and AI status, keeping the other metadata (customer, upload time)."""
        path = ref.folder / METADATA_FILE
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        data.update({
            'status': status.value,
            'ai_status': ai_status.value if ai_status else None,
            'updated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        })
        if error:
            data['error'] = error  # short message for analysts/logs; not shown in the overview yet
        else:
            data.pop('error', None)
        _write_metadata(ref.folder, data)

    # -- Reading ----------------------------------------------------------------------

    def list_proposals(self, *, all_versions: bool = False) -> list[ProposalSummary]:
        """All proposals, newest upload first.

        By default only the latest version of each customer is returned (one row
        per customer, as on the Home page). ``all_versions=True`` returns every version.
        Folders with missing or invalid metadata are skipped with a warning, so one
        broken upload never breaks the whole overview.
        """
        if not self.root.is_dir():
            # Nothing has been uploaded yet: an empty overview, not an error.
            logger.info('Proposals folder does not exist yet: %s', self.root)
            return []

        proposals = []
        for customer_dir in sorted(p for p in self.root.iterdir() if p.is_dir()):
            versions = self._read_customer(customer_dir)
            if not versions:
                continue
            if all_versions:
                proposals.extend(versions)
            else:
                proposals.append(max(versions, key=lambda p: p.version))

        # Newest first; customer name and version make the order stable.
        proposals.sort(key=lambda p: (p.uploaded_at, p.customer.casefold(), p.version), reverse=True)
        return proposals

    def _read_customer(self, customer_dir: Path) -> list[ProposalSummary]:
        result = []
        for version_dir in sorted(customer_dir.iterdir()):
            match = _VERSION_FOLDER.fullmatch(version_dir.name)
            if not version_dir.is_dir() or not match:
                continue  # other files/folders next to the versions are ignored
            try:
                result.append(_read_metadata(customer_dir.name, int(match.group(1)), version_dir))
            except (OSError, ValueError, TypeError) as error:
                logger.warning('Skipping proposal %s/%s: %s', customer_dir.name, version_dir.name, error)
        return result


def _read_metadata(customer_folder: str, version: int, version_dir: Path) -> ProposalSummary:
    """Parse proposal.json of one version folder. Raises ValueError when invalid."""
    path = version_dir / METADATA_FILE
    if not path.is_file():
        raise ValueError(f'{METADATA_FILE} is missing')
    data = json.loads(path.read_text(encoding='utf-8-sig'))  # -sig: tolerate a Windows BOM
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


def _write_metadata(version_dir: Path, data: dict) -> None:
    """Write proposal.json atomically, so the API never reads a half-written file."""
    temp = version_dir / f'.{METADATA_FILE}.tmp'
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(temp, version_dir / METADATA_FILE)
