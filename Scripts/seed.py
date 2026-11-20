#!/usr/bin/env python3
"""Central seeding script for local development, testing, and CI/CD.

Seeds sample proposals and mapping packages into the configured storage
(SFTP server when configured in .env, or local data/sftp-shared/ otherwise).

Usage from repository root:
    python Scripts/seed.py                 # Seeds both proposals and packages
    python Scripts/seed.py --force         # Overwrite existing files
    python Scripts/seed.py --local         # Force local storage instead of SFTP
    python Scripts/seed.py --proposals     # Seed only proposals
    python Scripts/seed.py --packages      # Seed only mapping packages
    python Scripts/seed.py --client <name> # Filter by client
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import posixpath
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sample Proposals Configuration
# ---------------------------------------------------------------------------
# (folder, customer, version, uploaded_at, status, ai_status, proposal_type)
PROPOSAL_EXAMPLES = [
    ('voorbeeldbedrijf-a', 'Voorbeeldbedrijf A', 1, '2026-10-22T14:05:00+02:00', 'AI_GENERATING', 'RUNNING', 'inbound'),
    ('voorbeeldbedrijf-b', 'Voorbeeldbedrijf B', 2, '2026-10-21T10:30:00+02:00', 'READY_FOR_REVIEW', None, 'outbound'),
    ('voorbeeldbedrijf-c', 'Voorbeeldbedrijf C', 1, '2026-10-20T16:45:00+02:00', 'AI_CHECKING_REVIEW', 'RUNNING', 'inboud-accept'),
    ('voorbeeldbedrijf-d', 'Voorbeeldbedrijf D', 3, '2026-10-19T09:15:00+02:00', 'RETURNED', 'FAILED', 'inbound'),
    ('voorbeeldbedrijf-e', 'Voorbeeldbedrijf E', 1, '2026-10-18T11:00:00+02:00', 'READY_FOR_REVIEW', None, 'outbound'),
    ('voorbeeldbedrijf-f', 'Voorbeeldbedrijf F', 2, '2026-10-17T13:20:00+02:00', 'IN_REVIEW', None, 'inbound'),
]

TEMPLATE_PATH = ROOT / 'Mapping_Proposal' / 'templates' / 'mapping_template.xlsx'


def _build_proposal_metadata(
    customer: str,
    version: int,
    uploaded_at: str,
    status: str,
    ai_status: str | None,
    prop_type: str,
    excel_name: str | None,
) -> dict[str, Any]:
    """Build metadata dictionary for an example proposal."""
    metadata: dict[str, Any] = {
        'customer': customer,
        'company': customer,
        'version': f'v{version}',
        'proposal_type': prop_type,
        'proposalType': prop_type,
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

    if status == 'RETURNED':
        metadata['ai_review'] = {
            'decision': 'REJECTED',
            'summary': 'Het voorstel bevat tegenstrijdige mappings en ongeldige regels voor meerdere doelvelden.',
            'findings': [
                "Doelveld '/Order/DeliveryDate' heeft tegenstrijdige bronpaden: '/Shipment/EstDate' en '/Shipment/ActualDate' zonder conditie.",
                "Doelveld '/Order/Lines/Quantity' heeft regel DIRECT geselecteerd maar het bronpad ontbreekt op rij 4.",
                "Doelveld '/Order/TotalAmount' heeft regel FIXED geselecteerd maar geen vaste waarde ingevuld op rij 7.",
            ],
            'checked_mappings': 7,
        }

    return metadata


# ---------------------------------------------------------------------------
# Sample Mapping Packages Configuration
# ---------------------------------------------------------------------------
PACKAGE_EXAMPLES: list[dict[str, Any]] = [
    {
        "company": "nouryon",
        "version": "v1",
        "package_type": "inbound",
        "package": {
            "schema_version": "1.0",
            "meta": {
                "client_name": "nouryon",
                "package_version": "1.0.0",
                "package_type": "inbound",
                "date_created": "2024-06-19T12:00:00Z",
                "user_created": "analist_a",
                "description": "Mapping for inbound IDOC conversion from DELVRY03 to SHP_OBDLV_SAVE_REPLICA05"
            },
            "mappings": [
                {"source_path": "/DELVRY03/IDOC/@BEGIN", "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/@BEGIN"},
                {"source_path": "/DELVRY03/IDOC/E1EDL20/@SEGMENT", "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1SHP_OBDLV_SAVE_REPLICA/@SEGMENT"},
                {"source_path": "/DELVRY03/IDOC/E1EDL20/E1ADRM1/@SEGMENT", "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1SHP_OBDLV_SAVE_REPLICA/E1BPADR1/@SEGMENT"},
                {"source_path": "/DELVRY03/IDOC/E1EDL20/E1ADRM1/PARTNER_ID", "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1SHP_OBDLV_SAVE_REPLICA/E1BPADR1/ADDR_NO"},
                {"source_path": "/DELVRY03/IDOC/E1EDL20/E1ADRM1/CITY1", "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1SHP_OBDLV_SAVE_REPLICA/E1BPADR1/CITY"},
                {"source_path": "/DELVRY03/IDOC/E1EDL20/E1ADRM1/COUNTRY1", "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1SHP_OBDLV_SAVE_REPLICA/E1BPADR1/COUNTRY"},
                {"source_path": "/DELVRY03/IDOC/E1EDL20/E1ADRM1/E1ADRE1/@SEGMENT", "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1SHP_OBDLV_SAVE_REPLICA/E1BPADR1/E1BPADR11/@SEGMENT"},
                {"source_path": "/DELVRY03/IDOC/E1EDL20/E1ADRM1/COUNTRY1", "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1SHP_OBDLV_SAVE_REPLICA/E1BPADR1/E1BPADR11/COUNTRYISO"},
                {"source_path": "/DELVRY03/IDOC/E1EDL20/E1ADRM1/E_MAIL", "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1SHP_OBDLV_SAVE_REPLICA/E1BPADR1/E1BPADR11/E_MAIL"},
                {"source_path": "/DELVRY03/IDOC/E1EDL20/E1ADRM1/LANGUAGE", "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1SHP_OBDLV_SAVE_REPLICA/E1BPADR1/E1BPADR11/LANGU_ISO"},
                {"source_path": "/DELVRY03/IDOC/E1EDL20/E1ADRM1/HOUSE_SUPL", "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1SHP_OBDLV_SAVE_REPLICA/E1BPADR1/HOUSE_NO"},
                {"source_path": "/DELVRY03/IDOC/E1EDL20/E1ADRM1/NAME1", "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1SHP_OBDLV_SAVE_REPLICA/E1BPADR1/NAME"},
                {"source_path": "/DELVRY03/IDOC/E1EDL20/E1ADRM1/NAME2", "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1SHP_OBDLV_SAVE_REPLICA/E1BPADR1/NAME_2"},
                {"source_path": None, "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1SHP_OBDLV_SAVE_REPLICA/E1BPADR1/NAME_3"},
                {"source_path": "/DELVRY03/IDOC/E1EDL20/E1ADRM1/POSTL_COD1", "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1SHP_OBDLV_SAVE_REPLICA/E1BPADR1/POSTL_COD1"},
                {"source_path": "/DELVRY03/IDOC/E1EDL20/E1ADRM1/STREET1", "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1SHP_OBDLV_SAVE_REPLICA/E1BPADR1/STREET"},
                {"source_path": "/DELVRY03/IDOC/E1EDL20/E1ADRM1/POSTL_PBOX", "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1SHP_OBDLV_SAVE_REPLICA/E1BPADR1/STR_SUPPL1"},
                {"source_path": "/DELVRY03/IDOC/E1EDL20/E1ADRM1/NAME1", "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1SHP_OBDLV_SAVE_REPLICA/E1BPADR1/STR_SUPPL2"},
                {"source_path": None, "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1SHP_OBDLV_SAVE_REPLICA/E1BPADR1/TEL1_NUMBER"},
                {"source_path": "/DELVRY03/IDOC/E1EDL20/E1EDT13/@SEGMENT", "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1SHP_OBDLV_SAVE_REPLICA/E1BPDLVDEADLN/@SEGMENT"},
                {"source_path": "/DELVRY03/IDOC/E1EDL20/E1EDT13/NTANF", "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1SHP_OBDLV_SAVE_REPLICA/E1BPDLVDEADLN/TIMESTAMP_UTC"},
                {"source_path": "/DELVRY03/IDOC/E1EDL20/E1EDT13/QUALF", "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1SHP_OBDLV_SAVE_REPLICA/E1BPDLVDEADLN/TIMETYPE"}
            ]
        }
    },
    {
        "company": "brunos",
        "version": "v1",
        "package_type": "outbound",
        "package": {
            "schema_version": "1.0",
            "meta": {
                "client_name": "brunos",
                "package_version": "1.0.0",
                "package_type": "outbound",
                "date_created": "2024-07-01T09:30:00Z",
                "user_created": "analist_b",
                "description": "Mapping package for Brunos outbound shipment notifications"
            },
            "mappings": [
                {"source_path": "/ORDER/HEADER/ID", "target_path": "/SHIPMENT/HEADER/ORDER_ID"},
                {"source_path": "/ORDER/CUSTOMER/NAME", "target_path": "/SHIPMENT/RECIPIENT/NAME"},
                {"source_path": "/ORDER/CUSTOMER/ADDRESS", "target_path": "/SHIPMENT/RECIPIENT/ADDRESS"},
                {"source_path": "/ORDER/CUSTOMER/CITY", "target_path": "/SHIPMENT/RECIPIENT/CITY"},
                {"source_path": "/ORDER/LINES/LINE/ITEM_ID", "target_path": "/SHIPMENT/ITEMS/ITEM/PRODUCT_ID"},
                {"source_path": "/ORDER/LINES/LINE/QTY", "target_path": "/SHIPMENT/ITEMS/ITEM/QUANTITY"}
            ]
        }
    }
]


# ---------------------------------------------------------------------------
# Environment Loader
# ---------------------------------------------------------------------------
def load_env() -> None:
    """Load environment variables from repository root .env."""
    candidates = [
        ROOT / '.env',
        ROOT / 'Mapping_Proposal' / '.env',
    ]
    for env_path in candidates:
        if env_path.is_file():
            try:
                for line in env_path.read_text(encoding='utf-8').splitlines():
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if line.startswith('export '):
                        line = line[len('export '):].strip()
                    if '=' in line:
                        k, v = line.split('=', 1)
                        k = k.strip()
                        v = v.strip().strip('\'"')
                        if k and k not in os.environ:
                            os.environ[k] = v
                break
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Local Storage Seeder
# ---------------------------------------------------------------------------
def seed_local(
    target_proposals: Path | None,
    target_packages: Path | None,
    force: bool = False,
    client: str | None = None,
) -> tuple[list[str], list[str]]:
    """Seed proposals and/or packages into local directories."""
    created_props: list[str] = []
    created_pkgs: list[str] = []

    # 1. Seed proposals
    if target_proposals is not None:
        target_proposals.mkdir(parents=True, exist_ok=True)
        for folder, customer, version, uploaded_at, status, ai_status, prop_type in PROPOSAL_EXAMPLES:
            if client and customer.lower() != client.lower() and folder.lower() != client.lower():
                continue

            version_dir = target_proposals / folder / f'v{version}' / prop_type
            version_dir.mkdir(parents=True, exist_ok=True)
            meta_path = version_dir / 'proposal.json'

            excel_name = f"{customer.replace(' ', '_')}_v{version}_mapping.xlsx" if status != 'AI_GENERATING' else None

            if force or not meta_path.is_file():
                metadata = _build_proposal_metadata(customer, version, uploaded_at, status, ai_status, prop_type, excel_name)
                meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
                logger.info("Created local proposal metadata: %s", meta_path)
                created_props.append(str(meta_path))
            else:
                logger.info("Local proposal exists, skipped: %s", meta_path)

            if excel_name and TEMPLATE_PATH.is_file():
                dest_excel = version_dir / excel_name
                if force or not dest_excel.is_file():
                    dest_excel.write_bytes(TEMPLATE_PATH.read_bytes())
                    logger.info("Created local proposal workbook: %s", dest_excel)

    # 2. Seed mapping packages
    if target_packages is not None:
        target_packages.mkdir(parents=True, exist_ok=True)
        for item in PACKAGE_EXAMPLES:
            company = item["company"]
            version = item["version"]
            prop_type = item["package_type"]

            if client and company.lower() != client.lower():
                continue

            pkg_dir = target_packages / company / version / prop_type
            pkg_dir.mkdir(parents=True, exist_ok=True)
            pkg_file = pkg_dir / "MPackage.json"

            if force or not pkg_file.is_file():
                content = json.dumps(item["package"], indent=2, ensure_ascii=False) + "\n"
                pkg_file.write_text(content, encoding="utf-8")
                logger.info("Created local mapping package: %s", pkg_file)
                created_pkgs.append(str(pkg_file))
            else:
                logger.info("Local mapping package exists, skipped: %s", pkg_file)

    return created_props, created_pkgs


# ---------------------------------------------------------------------------
# SFTP Storage Seeder
# ---------------------------------------------------------------------------
def seed_sftp(
    seed_proposals_flag: bool = True,
    seed_packages_flag: bool = True,
    force: bool = False,
    client: str | None = None,
) -> tuple[list[str], list[str]]:
    """Seed proposals and/or mapping packages directly onto the SFTP server."""
    import paramiko

    host = os.getenv("SFTP_SHARED_HOST", "localhost")
    port = int(os.getenv("SFTP_SHARED_PORT", "2222"))
    user = os.getenv("SFTP_SHARED_USER", "shareduser")
    password = os.getenv("SFTP_SHARED_PASSWORD", "devpassword")
    props_base = os.getenv("SFTP_SHARED_PROPOSALS_DIR", "/Proposals").strip() or "/Proposals"
    pkgs_base = os.getenv("SFTP_SHARED_PACKAGES_DIR", "/Packages").strip() or "/Packages"

    logger.info("Connecting to SFTP server %s:%d as %s", host, port, user)

    transport = paramiko.Transport((host, port))
    transport.connect(username=user, password=password)
    sftp = paramiko.SFTPClient.from_transport(transport)
    created_props: list[str] = []
    created_pkgs: list[str] = []

    def make_remote_dirs(path: str) -> None:
        parts = [p for p in path.split('/') if p]
        curr = '/' if path.startswith('/') else ''
        for part in parts:
            curr = posixpath.join(curr, part) if curr != '/' else f'/{part}'
            try:
                sftp.stat(curr)
            except OSError:
                try:
                    sftp.mkdir(curr)
                except OSError:
                    pass

    try:
        # 1. Seed proposals
        if seed_proposals_flag:
            make_remote_dirs(props_base)
            for folder, customer, version, uploaded_at, status, ai_status, prop_type in PROPOSAL_EXAMPLES:
                if client and customer.lower() != client.lower() and folder.lower() != client.lower():
                    continue

                version_dir = posixpath.join(props_base, folder, f'v{version}', prop_type)
                make_remote_dirs(version_dir)
                meta_file = posixpath.join(version_dir, 'proposal.json')

                excel_name = f"{customer.replace(' ', '_')}_v{version}_mapping.xlsx" if status != 'AI_GENERATING' else None

                exists = False
                try:
                    sftp.stat(meta_file)
                    exists = True
                except OSError:
                    pass

                if force or not exists:
                    metadata = _build_proposal_metadata(customer, version, uploaded_at, status, ai_status, prop_type, excel_name)
                    content = json.dumps(metadata, indent=2, ensure_ascii=False) + '\n'
                    temp_meta = posixpath.join(version_dir, '.proposal.json.tmp')
                    with sftp.open(temp_meta, 'wb') as f:
                        f.write(content.encode('utf-8'))
                    try:
                        sftp.posix_rename(temp_meta, meta_file)
                    except OSError:
                        try:
                            sftp.remove(meta_file)
                        except OSError:
                            pass
                        sftp.rename(temp_meta, meta_file)
                    logger.info("Created SFTP proposal metadata: %s", meta_file)
                    created_props.append(meta_file)
                else:
                    logger.info("SFTP proposal exists, skipped: %s", meta_file)

                if excel_name and TEMPLATE_PATH.is_file():
                    excel_file = posixpath.join(version_dir, excel_name)
                    excel_exists = False
                    try:
                        sftp.stat(excel_file)
                        excel_exists = True
                    except OSError:
                        pass
                    if force or not excel_exists:
                        sftp.put(str(TEMPLATE_PATH), excel_file)
                        logger.info("Created SFTP proposal workbook: %s", excel_file)

        # 2. Seed packages
        if seed_packages_flag:
            make_remote_dirs(pkgs_base)
            for item in PACKAGE_EXAMPLES:
                company = item["company"]
                version = item["version"]
                prop_type = item["package_type"]

                if client and company.lower() != client.lower():
                    continue

                folder = posixpath.join(pkgs_base, company, version, prop_type)
                make_remote_dirs(folder)
                remote_file = posixpath.join(folder, "MPackage.json")

                exists = False
                try:
                    sftp.stat(remote_file)
                    exists = True
                except OSError:
                    pass

                if force or not exists:
                    content = json.dumps(item["package"], indent=2, ensure_ascii=False) + "\n"
                    temp_file = posixpath.join(folder, ".MPackage.json.tmp")
                    with sftp.open(temp_file, "wb") as f:
                        f.write(content.encode("utf-8"))
                    try:
                        sftp.posix_rename(temp_file, remote_file)
                    except OSError:
                        try:
                            sftp.remove(remote_file)
                        except OSError:
                            pass
                        sftp.rename(temp_file, remote_file)
                    logger.info("Created SFTP mapping package: %s", remote_file)
                    created_pkgs.append(remote_file)
                else:
                    logger.info("SFTP mapping package exists, skipped: %s", remote_file)

    finally:
        sftp.close()
        transport.close()

    return created_props, created_pkgs


# ---------------------------------------------------------------------------
# Central Entry Point
# ---------------------------------------------------------------------------
def seed_all(
    force: bool = False,
    local: bool = False,
    proposals: bool = True,
    packages: bool = True,
    client: str | None = None,
) -> tuple[list[str], list[str]]:
    """Seed proposals and/or mapping packages based on environment and options."""
    load_env()
    sftp_host = os.getenv("SFTP_SHARED_HOST")

    if not local and sftp_host:
        try:
            return seed_sftp(
                seed_proposals_flag=proposals,
                seed_packages_flag=packages,
                force=force,
                client=client,
            )
        except Exception as e:
            logger.warning("SFTP seeding failed (%s), falling back to local storage", e)

    local_base = ROOT / "Mapping_Proposal" / "data" / "sftp-shared"
    target_props = (local_base / "proposals") if proposals else None
    target_pkgs = (local_base / "packages") if packages else None

    return seed_local(
        target_proposals=target_props,
        target_packages=target_pkgs,
        force=force,
        client=client,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Central seeder for proposals and mapping packages.")
    parser.add_argument("--force", "-f", action="store_true", help="Overwrite existing files in storage")
    parser.add_argument("--local", action="store_true", help="Force local filesystem storage instead of SFTP")
    parser.add_argument("--proposals", action="store_true", help="Seed only proposals")
    parser.add_argument("--packages", action="store_true", help="Seed only mapping packages")
    parser.add_argument("--client", "-c", type=str, default=None, help="Filter by client name")
    args = parser.parse_args()

    # If neither flag is passed, seed both by default
    do_proposals = args.proposals or not args.packages
    do_packages = args.packages or not args.proposals

    try:
        props, pkgs = seed_all(
            force=args.force,
            local=args.local,
            proposals=do_proposals,
            packages=do_packages,
            client=args.client,
        )
        print(f"Seeding completed: {len(props)} proposal file(s), {len(pkgs)} package(s) written.")
        return 0
    except Exception as e:
        logger.error("Seeding failed: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
