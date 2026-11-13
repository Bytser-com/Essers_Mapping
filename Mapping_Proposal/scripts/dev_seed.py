"""Create example proposals for local development and UI testing.

Run from the Mapping_Proposal folder:

    python -m scripts.dev_seed
    python -m scripts.dev_seed --force
    python -m scripts.dev_seed --local

It writes the six example proposals from the Home design into the active storage
(SFTP server when configured in .env, or data/sftp-shared/proposals/ otherwise).
For proposals that can be reviewed, it also includes a sample Excel workbook so
they can be opened and tested in the frontend.
"""
from __future__ import annotations

import argparse
import json

from services.proposal_runner import workbook_name
from services.storage import LocalStorage, proposal_storage

from .config import LOCAL_SHARED_DIR, TEMPLATE_PATH

# (folder, customer, version, uploaded_at, status, ai_status)
EXAMPLES = [
    ('voorbeeldbedrijf-a', 'Voorbeeldbedrijf A', 1, '2026-10-22T14:05:00+02:00', 'AI_GENERATING', 'RUNNING'),
    ('voorbeeldbedrijf-b', 'Voorbeeldbedrijf B', 2, '2026-10-21T10:30:00+02:00', 'READY_FOR_REVIEW', None),
    ('voorbeeldbedrijf-c', 'Voorbeeldbedrijf C', 1, '2026-10-20T16:45:00+02:00', 'AI_CHECKING_REVIEW', 'RUNNING'),
    ('voorbeeldbedrijf-d', 'Voorbeeldbedrijf D', 3, '2026-10-19T09:15:00+02:00', 'RETURNED', 'FAILED'),
    ('voorbeeldbedrijf-e', 'Voorbeeldbedrijf E', 1, '2026-10-18T11:00:00+02:00', 'READY_FOR_REVIEW', None),
    ('voorbeeldbedrijf-f', 'Voorbeeldbedrijf F', 2, '2026-10-17T13:20:00+02:00', 'IN_REVIEW', None),
]



def _build_metadata(
    customer: str,
    version: int,
    uploaded_at: str,
    status: str,
    ai_status: str,
    excel_name: str | None,
) -> dict:
    """Build metadata for an example proposal."""
    metadata = {
        'customer': customer,
        'company': customer,
        'version': f'v{version}',
        'uploaded_at': uploaded_at,
        'createdDate': uploaded_at,
        'status': status,
        'ai_status': ai_status,
        'uploadUser': 'exampleUser',
        'upload_user': 'exampleUser',
        'createdBy': 'exampleUser',
    }

    if excel_name:
        metadata['filename'] = excel_name

    return metadata


def _upload_example_workbook(
    session,
    version_dir: str,
    excel_name: str | None,
    force: bool,
) -> None:
    """Upload the example workbook when needed."""
    if not excel_name or not TEMPLATE_PATH.is_file():
        return

    excel_dest = f'{version_dir}/{excel_name}'

    if force or not session.exists(excel_dest):
        session.upload_file(TEMPLATE_PATH, excel_dest)
        print(f'Uploaded: {excel_dest}')



def seed_proposals(storage=None, force: bool = False) -> None:
    """Seed example proposals into the configured storage."""
    if storage is None:
        storage = proposal_storage()

    print(f'Seeding proposals to: {storage.describe()}')

    with storage.session() as session:
        for folder, customer, version, uploaded_at, status, ai_status in EXAMPLES:
            version_dir = f'{folder}/v{version}'
            metadata_path = f'{version_dir}/proposal.json'

            if not force and session.exists(metadata_path):
                print(f'Exists, skipped: {metadata_path}')
                continue

            session.make_dirs(version_dir)

            excel_name = (
                workbook_name(customer, version)
                if status != 'AI_GENERATING'
                else None
            )

            metadata = _build_metadata(
                customer,
                version,
                uploaded_at,
                status,
                ai_status,
                excel_name,
            )

            session.write_text(
                metadata_path,
                json.dumps(metadata, indent=2, ensure_ascii=False),
            )
            print(f'Created: {metadata_path}')

            _upload_example_workbook(
                session,
                version_dir,
                excel_name,
                force,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description='Seed sample proposals for development.')
    parser.add_argument('--force', '-f', action='store_true', help='Overwrite existing proposal files')
    parser.add_argument('--local', action='store_true', help='Force seeding local folder instead of SFTP')
    args = parser.parse_args()

    storage = LocalStorage(LOCAL_SHARED_DIR / 'proposals') if args.local else proposal_storage()
    seed_proposals(storage=storage, force=args.force)


if __name__ == '__main__':
    main()

