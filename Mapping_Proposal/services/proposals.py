"""Reading and writing mapping proposals on the shared storage (the SFTP server).

Layout on the storage: one folder per customer, one subfolder per version, one subfolder per proposal type.

    <SFTP_SHARED_PROPOSALS_DIR>/
        voorbeeldbedrijf-a/
            v1/
                inbound/
                    proposal.json        metadata shown in the overview (required)
                    MProposal-<Klant>_V<N>.xlsx  the AI result (the uploaded XML is not stored on SFTP)
            v2/
                outbound/
                    proposal.json

The files live on the shared SFTPGo server of the infrastructure (sftp-shared, see
Kubernetes/base/shared-storage/sftp-shared.yaml); this service connects to it directly
over SFTP (services/storage.py). Locally, when SFTP_SHARED_HOST is not set, the same
layout lives in data/sftp-shared/proposals/ (see Scripts/seed.py for example data).

Example proposal.json:
    {
      "customer": "Voorbeeldbedrijf A",
      "proposal_type": "inbound",
      "uploaded_at": "2026-10-22T14:05:00+02:00",
      "status": "AI_GENERATING",
      "ai_status": "RUNNING"
    }
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from .storage import LocalStorage, Storage, StorageSession

logger = logging.getLogger(__name__)

# Name of the metadata file inside every version folder.
METADATA_FILE = 'proposal.json'

# Version folders are named v1, v2, v3, ...
_VERSION_FOLDER = re.compile(r'^v(\d+)$')


class ProposalStatus(StrEnum):
    """Workflow status of a proposal. The frontend translates these codes to labels."""

    AI_GENERATING = 'AI_GENERATING'            # "AI maakt voorstel"
    READY_FOR_REVIEW = 'READY_FOR_REVIEW'      # "Klaar om na te kijken"
    IN_REVIEW = 'IN_REVIEW'                    # "In review"
    AI_CHECKING_REVIEW = 'AI_CHECKING_REVIEW'  # "AI controleert review van analist"
    RETURNED = 'RETURNED'                      # "Teruggestuurd"


class AiStatus(StrEnum):
    """What the AI is doing for this proposal. ``None`` means nothing ("—" in the UI)."""

    RUNNING = 'RUNNING'  # "Bezig"
    FAILED = 'FAILED'    # "Mislukt"


@dataclass(frozen=True)
class ProposalSummary:
    """One row of the proposals overview."""

    id: str                 # "<customer folder>/v<version>" or "<customer folder>/v<version>/<proposal_type>", unique on the share
    customer: str
    version: int
    uploaded_at: datetime   # always timezone-aware
    status: ProposalStatus
    ai_status: AiStatus | None
    proposal_type: str = ''

    @property
    def can_open(self) -> bool:
        # While the AI is still writing the first proposal there is nothing to open yet.
        return self.status is not ProposalStatus.AI_GENERATING

    def to_dict(self) -> dict:
        """JSON-ready representation, used by the API response."""
        data = {
            'id': self.id,
            'customer': self.customer,
            'version': self.version,
            'uploaded_at': self.uploaded_at.isoformat(),
            'status': self.status.value,
            'ai_status': self.ai_status.value if self.ai_status else None,
            'can_open': self.can_open,
        }
        if self.proposal_type:
            data['proposal_type'] = self.proposal_type
            data['proposalType'] = self.proposal_type
        return data


@dataclass(frozen=True)
class ProposalRef:
    """A proposal version that was created on the shared storage (used while the AI runs)."""

    customer: str
    version: int
    folder: str             # "<customer folder>/v<version>/<proposal_type>", relative to the proposals root
    proposal_type: str = ''

    def __post_init__(self):
        if self.proposal_type and not self.proposal_type.islower():
            object.__setattr__(self, 'proposal_type', self.proposal_type.lower())

    @property
    def id(self) -> str:
        return self.folder


def customer_folder_name(customer: str) -> str:
    """Folder name for a customer: 'Voorbeeldbedrijf Ä & Co' -> 'voorbeeldbedrijf-a-co'."""
    ascii_name = unicodedata.normalize('NFKD', customer).encode('ascii', 'ignore').decode('ascii')
    slug = re.sub(r'[^a-z0-9]+', '-', ascii_name.lower()).strip('-')
    return slug or 'klant'


def proposal_type_folder_name(proposal_type: str) -> str:
    """Folder name for a proposal type: 'inbound' -> 'inbound', 'Inbound' -> 'inbound', 'inboud-accept' -> 'inboud-accept'."""
    ascii_name = unicodedata.normalize('NFKD', proposal_type).encode('ascii', 'ignore').decode('ascii')
    slug = re.sub(r'[^a-zA-Z0-9_-]+', '-', ascii_name).strip('-').lower()
    return slug or 'proposal'


class ProposalStore:
    """Reads and writes proposals with the layout described above.

    ``storage`` is the SFTP server (services/storage.SftpStorage) or, locally and in the
    tests, a folder: a Path is wrapped in a LocalStorage.
    """

    def __init__(
        self,
        storage: Storage | Path | str,
        packages_storage: Storage | Path | str | None = None,
    ):
        self.storage = LocalStorage(Path(storage)) if isinstance(storage, (str, Path)) else storage
        if packages_storage is not None:
            self._packages_storage = (
                LocalStorage(Path(packages_storage))
                if isinstance(packages_storage, (str, Path))
                else packages_storage
            )
        else:
            self._packages_storage = None

    @property
    def root(self):
        """Root of the proposals (a Path for a local folder, a remote path for SFTP)."""
        return self.storage.root

    def get_packages_storage(self) -> Storage | None:
        """Resolve the packages storage (configured, local sibling, or from settings)."""
        if self._packages_storage is not None:
            return self._packages_storage

        if isinstance(self.storage, LocalStorage):
            parent = self.storage.root.parent
            for candidate in ('packages', 'Packages'):
                pkg_dir = parent / candidate
                if pkg_dir.is_dir():
                    return LocalStorage(pkg_dir)
            return LocalStorage(parent / 'packages')

        try:
            from .storage import packages_storage
            return packages_storage()
        except Exception as e:
            logger.warning('Failed to resolve packages storage: %s', e)
            return None

    def get_latest_package_version(
        self,
        customer: str,
        session: StorageSession | None = None,
    ) -> int | None:
        """Find the latest package version number for this customer in /Packages, if any.

        Returns None if the customer has no packages or packages storage is unavailable.
        """
        customer = customer.strip()
        if not customer:
            return None

        # 1. If explicit packages_storage was configured, use it
        if self._packages_storage is not None:
            try:
                with self._packages_storage.session() as s:
                    return self._find_max_package_version_in_session(s, customer)
            except Exception as e:
                logger.warning('Failed to query configured packages storage for %r: %s', customer, e)
                return None

        # 2. If a live SFTP session was passed, reuse the SFTP client connection for /Packages
        if session is not None and hasattr(session, 'client'):
            import os
            pkg_root = os.getenv('SFTP_SHARED_PACKAGES_DIR', '/Packages').strip() or '/Packages'
            from .storage import _SftpSession
            try:
                pkg_session = _SftpSession(session.client, pkg_root)
                return self._find_max_package_version_in_session(pkg_session, customer)
            except Exception as e:
                logger.warning('Failed to check packages on SFTP for %r: %s', customer, e)
                return None

        # 3. If session is LocalStorage or self.storage is LocalStorage
        local_root = None
        if isinstance(session, LocalStorage):
            local_root = session.root
        elif isinstance(self.storage, LocalStorage):
            local_root = self.storage.root

        if local_root is not None:
            parent = local_root.parent
            for candidate in ('packages', 'Packages'):
                pkg_dir = parent / candidate
                if pkg_dir.is_dir():
                    try:
                        with LocalStorage(pkg_dir).session() as s:
                            return self._find_max_package_version_in_session(s, customer)
                    except Exception as e:
                        logger.warning('Failed to check local packages for %r: %s', customer, e)
                        return None
            return None

        # 4. Fallback: query default packages_storage
        pkg_store = self.get_packages_storage()
        if pkg_store is not None:
            try:
                with pkg_store.session() as s:
                    return self._find_max_package_version_in_session(s, customer)
            except Exception as e:
                logger.warning('Failed to query fallback packages storage for %r: %s', customer, e)
                return None

        return None

    def _find_max_package_version_in_session(self, s: StorageSession, customer: str) -> int | None:
        target_name = customer.strip().lower()
        target_slug = customer_folder_name(customer).lower()
        try:
            dirs = s.list_dirs('')
        except Exception:
            return None

        matched_dir = None
        for d in dirs:
            d_lower = d.lower()
            if (
                d_lower == target_name
                or d_lower == target_slug
                or customer_folder_name(d).lower() == target_slug
            ):
                matched_dir = d
                break
        if not matched_dir:
            return None

        try:
            version_dirs = s.list_dirs(matched_dir)
        except Exception:
            return None

        versions = [
            int(m.group(1))
            for name in version_dirs
            if (m := re.match(r'^[vV](\d+)$', name))
        ]
        return max(versions) if versions else None

    # -- Writing (used by the AI run, see services/proposal_runner.py) -----------------

    def create_proposal(self, customer: str, proposal_type: str = 'inbound', created_by: str = 'Analist A') -> ProposalRef:
        """Create the next version and proposal type folder for this customer with status 'AI is generating'.

        The overview shows the new row immediately, while the AI is still working.
        If the customer exists in /Packages, the proposal starts at latest package version + 1.
        Otherwise it starts at v1.
        """
        customer = customer.strip()
        if not customer:
            raise ValueError('customer name is empty')
        if proposal_type is None or not str(proposal_type).strip():
            raise ValueError('proposal type is empty')
        prop_type = str(proposal_type).strip().lower()
        type_dir = proposal_type_folder_name(prop_type)
        customer_dir = customer_folder_name(customer)
        with self.storage.session() as s:
            latest_pkg = self.get_latest_package_version(customer, session=s)
            s.make_dirs(customer_dir)
            existing = [int(m.group(1)) for name in s.list_dirs(customer_dir)
                        if (m := _VERSION_FOLDER.fullmatch(name))]
            if latest_pkg is not None:
                version = max(existing + [latest_pkg], default=0) + 1
            else:
                version = max(existing, default=0) + 1
            # Creating a folder that exists fails: if another run took this number, try the next.
            while not s.make_dir(f'{customer_dir}/v{version}'):
                version += 1
            folder = f'{customer_dir}/v{version}/{type_dir}'
            s.make_dirs(folder)
            now = datetime.now(UTC).isoformat(timespec='seconds')
            _write_metadata(s, folder, {
                'customer': customer,
                'company': customer,
                'version': f'v{version}',
                'proposal_type': prop_type,
                'proposalType': prop_type,
                'uploaded_at': now,
                'createdDate': now,
                'status': ProposalStatus.AI_GENERATING.value,
                'ai_status': AiStatus.RUNNING.value,
                'createdBy': created_by,
            })
        return ProposalRef(customer=customer, version=version, folder=folder, proposal_type=prop_type)

    def set_status(self, ref: ProposalRef, status: ProposalStatus,
                   ai_status: AiStatus | None, *, error: str = '') -> None:
        """Update status and AI status, keeping the other metadata (customer, upload time)."""
        with self.storage.session() as s:
            data = json.loads(s.read_text(f'{ref.folder}/{METADATA_FILE}'))
            data.update({
                'status': status.value,
                'ai_status': ai_status.value if ai_status else None,
                'updated_at': datetime.now(UTC).isoformat(timespec='seconds'),
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
            try:
                meta_path = f'{ref.folder}/{METADATA_FILE}'
                if s.exists(meta_path):
                    data = json.loads(s.read_text(meta_path))
                    data['filename'] = name
                    _write_metadata(s, ref.folder, data)
            except Exception as e:
                logger.warning('Failed to update filename in metadata: %s', e)

    def has_proposal(self, customer: str) -> bool:
        """Whether a proposal folder already exists on SFTP for this company."""
        customer = customer.strip()
        if not customer:
            return False
        customer_dir = customer_folder_name(customer)
        with self.storage.session() as s:
            if s.exists(customer_dir):
                return True
            existing_dirs = {d.lower() for d in s.list_dirs('')}
            return customer_dir.lower() in existing_dirs

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
            version_num = int(match.group(1))
            found_in_subdirs = False
            for type_dir in s.list_dirs(f'{customer_dir}/{name}'):
                type_meta_path = f'{customer_dir}/{name}/{type_dir}/{METADATA_FILE}'
                if s.exists(type_meta_path):
                    found_in_subdirs = True
                    try:
                        summary = _read_metadata(customer_dir, version_num, s.read_text(type_meta_path), proposal_type=type_dir)
                        if summary is not None:
                            result.append(summary)
                    except (OSError, ValueError, TypeError) as error:
                        logger.warning('Skipping proposal %s/%s/%s: %s', customer_dir, name, type_dir, error)
            if not found_in_subdirs:
                try:
                    legacy_path = f'{customer_dir}/{name}/{METADATA_FILE}'
                    if not s.exists(legacy_path):
                        raise ValueError(f'{METADATA_FILE} is missing')
                    summary = _read_metadata(customer_dir, version_num, s.read_text(legacy_path))
                    if summary is not None:
                        result.append(summary)
                except (OSError, ValueError, TypeError) as error:
                    logger.warning('Skipping proposal %s/%s: %s', customer_dir, name, error)
        return result


def _read_metadata(customer_folder: str, version: int, text: str, proposal_type: str = '') -> ProposalSummary | None:
    """Parse the proposal.json of one version folder. Raises ValueError when invalid."""
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f'{METADATA_FILE} must contain a JSON object')

    raw_status = data.get('status')
    if raw_status is None:
        return None

    try:
        status = ProposalStatus(raw_status)
    except ValueError:
        raise ValueError(f'unknown status {raw_status!r}') from None
    ai_value = data.get('ai_status')
    try:
        ai_status = AiStatus(ai_value) if ai_value else None
    except ValueError:
        raise ValueError(f'unknown ai_status {ai_value!r}') from None

    prop_type = str(data.get('proposal_type') or data.get('proposalType') or proposal_type or '').strip().lower()
    folder_id = f'{customer_folder}/v{version}/{prop_type}' if prop_type else f'{customer_folder}/v{version}'

    return ProposalSummary(
        id=folder_id,
        # The display name falls back to the folder name when "customer" is missing.
        customer=str(data.get('customer') or customer_folder).strip(),
        # The folder name is the source of truth for the version number.
        version=version,
        uploaded_at=_parse_timestamp(data.get('uploaded_at')),
        status=status,
        ai_status=ai_status,
        proposal_type=prop_type,
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
        moment = moment.replace(tzinfo=UTC)
    return moment


def _write_metadata(s: StorageSession, folder: str, data: dict) -> None:
    """Write proposal.json atomically, so the API never reads a half-written file."""
    s.write_text(f'{folder}/{METADATA_FILE}', json.dumps(data, indent=2, ensure_ascii=False))
