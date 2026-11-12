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
from pathlib import Path

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


def seed_proposals(storage=None, force: bool = False) -> None:
    if storage is None:
        storage = proposal_storage()

    print(f'Seeding proposals to: {storage.describe()}')

    with storage.session() as s:
        for folder, customer, version, uploaded_at, status, ai_status in EXAMPLES:
            version_dir = f'{folder}/v{version}'
            metadata_path = f'{version_dir}/proposal.json'

            if not force and s.exists(metadata_path):
                print(f'Exists, skipped: {metadata_path}')
                continue

            s.make_dirs(version_dir)

            excel_name = workbook_name(customer, version) if status != 'AI_GENERATING' else None

            metadata = {
                'customer': customer,
                'company': customer,
                'version': f'v{version}',
                'uploaded_at': uploaded_at,
                'createdDate': uploaded_at,
                'status': status,
                'ai_status': ai_status,
            }
            if excel_name:
                metadata['filename'] = excel_name

            s.write_text(metadata_path, json.dumps(metadata, indent=2, ensure_ascii=False))
            print(f'Created: {metadata_path}')

            if excel_name and TEMPLATE_PATH.is_file():
                excel_dest = f'{version_dir}/{excel_name}'
                if force or not s.exists(excel_dest):
                    s.upload_file(TEMPLATE_PATH, excel_dest)
                    print(f'Uploaded: {excel_dest}')


def main() -> None:
    parser = argparse.ArgumentParser(description='Seed sample proposals for development.')
    parser.add_argument('--force', '-f', action='store_true', help='Overwrite existing proposal files')
    parser.add_argument('--local', action='store_true', help='Force seeding local folder instead of SFTP')
    args = parser.parse_args()

    storage = LocalStorage(LOCAL_SHARED_DIR / 'proposals') if args.local else proposal_storage()
    seed_proposals(storage=storage, force=args.force)


if __name__ == '__main__':
    main()

