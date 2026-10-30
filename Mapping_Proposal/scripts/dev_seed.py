"""Create example proposals for local development (no SFTP server needed).

Run from the Mapping_Proposal folder:

    python -m scripts.dev_seed

It writes the six example proposals from the Home design into
data/sftp-shared/proposals/ (data/ is not in Git). It always writes to that local
folder, never to SHARED_MOUNT_PATH, so it cannot touch the real SFTP share.
Existing proposal.json files are left alone; delete the folder to start over.
"""
from __future__ import annotations

import json

from .config import LOCAL_SHARED_DIR

# (folder, customer, version, uploaded_at, status, ai_status)
EXAMPLES = [
    ('voorbeeldbedrijf-a', 'Voorbeeldbedrijf A', 1, '2026-10-22T14:05:00+02:00', 'AI_GENERATING', 'RUNNING'),
    ('voorbeeldbedrijf-b', 'Voorbeeldbedrijf B', 2, '2026-10-21T10:30:00+02:00', 'READY_FOR_REVIEW', None),
    ('voorbeeldbedrijf-c', 'Voorbeeldbedrijf C', 1, '2026-10-20T16:45:00+02:00', 'AI_CHECKING_REVIEW', 'RUNNING'),
    ('voorbeeldbedrijf-d', 'Voorbeeldbedrijf D', 3, '2026-10-19T09:15:00+02:00', 'RETURNED', 'FAILED'),
    ('voorbeeldbedrijf-e', 'Voorbeeldbedrijf E', 1, '2026-10-18T11:00:00+02:00', 'READY_FOR_REVIEW', None),
    ('voorbeeldbedrijf-f', 'Voorbeeldbedrijf F', 2, '2026-10-17T13:20:00+02:00', 'IN_REVIEW', None),
]


def main() -> None:
    root = LOCAL_SHARED_DIR / 'proposals'
    for folder, customer, version, uploaded_at, status, ai_status in EXAMPLES:
        path = root / folder / f'v{version}' / 'proposal.json'
        if path.exists():
            print(f'Exists, skipped: {path}')
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        metadata = {'customer': customer, 'uploaded_at': uploaded_at,
                    'status': status, 'ai_status': ai_status}
        path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f'Created: {path}')


if __name__ == '__main__':
    main()
