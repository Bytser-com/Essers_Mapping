"""SFTP storage service for Mapping Converter: stores JSON mapping packages on SFTP."""

from __future__ import annotations

import json
import logging
import os
import posixpath
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from models import MappingPackage, PackageMeta

logger = logging.getLogger(__name__)
DEFAULT_PACKAGES_DIR = "/Packages"
DEFAULT_PROPOSALS_DIR = "/Proposals"

# Try loading .env if python-dotenv is present
try:
    from dotenv import load_dotenv

    for parent in Path(__file__).resolve().parents:
        candidate = parent / ".env"
        if candidate.is_file():
            load_dotenv(candidate)
            break
except ImportError:
    pass


class SftpError(Exception):
    """Raised when an error occurs during SFTP operations."""

    pass


class SftpFileNotFoundError(SftpError):
    """Raised when the requested proposal file or directory does not exist on SFTP."""

    pass


@dataclass(frozen=True)
class SftpConfig:
    host: str
    port: int = 2222
    user: str = "shareduser"
    password: str = "devpassword"
    packages_dir: str = DEFAULT_PACKAGES_DIR
    proposals_dir: str = DEFAULT_PROPOSALS_DIR
    allow_unknown_keys: bool = True
    timeout: float = 15.0


def get_sftp_config() -> SftpConfig:
    """Read SFTP configuration from environment variables with smart dev defaults."""
    host = os.getenv("SFTP_SHARED_HOST", "localhost").strip()
    try:
        port = int(os.getenv("SFTP_SHARED_PORT", "2222"))
    except ValueError:
        port = 2222

    pkg_dir = os.getenv("SFTP_SHARED_PACKAGES_DIR", DEFAULT_PACKAGES_DIR).strip() or DEFAULT_PACKAGES_DIR
    if not pkg_dir.startswith("/"):
        pkg_dir = "/" + pkg_dir

    prop_dir = os.getenv("SFTP_SHARED_PROPOSALS_DIR", DEFAULT_PROPOSALS_DIR).strip() or DEFAULT_PROPOSALS_DIR
    if not prop_dir.startswith("/"):
        prop_dir = "/" + prop_dir

    allow_unknown = os.getenv("SFTP_ALLOW_UNKNOWN_KEYS", "true").strip().lower() in (
        "true",
        "1",
        "yes",
    )

    user = os.getenv("SFTP_SHARED_USER", "shareduser").strip() or "shareduser"
    password = os.getenv("SFTP_SHARED_PASSWORD", "").strip()
    if not password and host in ("localhost", "127.0.0.1"):
        password = "devpassword"

    return SftpConfig(
        host=host,
        port=port,
        user=user,
        password=password,
        packages_dir=pkg_dir,
        proposals_dir=prop_dir,
        allow_unknown_keys=allow_unknown,
    )


def normalize_version(version: str | int) -> str:
    """Normalize folder version to 'v<N>' format (e.g. 3 -> 'v3', 'V4' -> 'v4')."""
    v_str = str(version).strip().lower()
    match = re.search(r"\d+", v_str)
    if match:
        return f"v{match.group(0)}"
    return v_str if v_str else "v1"


def format_semver(version: str | int) -> str:
    """Format version into semantic version (e.g. 'v4' or '4' -> '4.0.0', '1.0.0' -> '1.0.0')."""
    v_str = str(version).strip()
    if "." in v_str:
        return v_str.lstrip("vV")
    match = re.search(r"\d+", v_str)
    if match:
        return f"{match.group(0)}.0.0"
    return "1.0.0"


def normalize_slug(text: str) -> str:
    """Normalize company name or message type to clean lowercase string."""
    cleaned = text.strip().lower()
    return re.sub(r"[^\w.-]+", "_", cleaned).strip("_")


def build_package_sftp_path(
    company: str,
    version: str | int,
    message_type: str,
    base_dir: str | None = None,
) -> str:
    """Build the normalized remote path on the SFTP server.

    Example:
        /Packages/nouryon/v3/inbound/MPackage.json
    """
    clean_company = normalize_slug(company)
    clean_version = normalize_version(version)
    clean_type = normalize_slug(message_type)
    filename = "MPackage.json"

    if base_dir is None:
        cfg = get_sftp_config()
        base_dir = cfg.packages_dir

    base = base_dir.rstrip("/")
    return posixpath.join(base, clean_company, clean_version, clean_type, filename)


def _sftp_makedirs(sftp_client: Any, remote_dir: str) -> None:
    """Recursively create directories over SFTP."""
    parts = [p for p in remote_dir.split("/") if p]
    current = "/" if remote_dir.startswith("/") else ""
    for part in parts:
        current = posixpath.join(current, part)
        try:
            sftp_client.stat(current)
        except OSError:
            try:
                sftp_client.mkdir(current)
            except OSError:
                pass


def save_json_to_sftp(
    json_content: str | bytes,
    remote_path: str,
    config: SftpConfig | None = None,
) -> str:
    """Upload a JSON string or bytes to the SFTP server at the given remote path.

    If host is explicitly set to 'none' or 'local', falls back to local storage under
    `data/sftp-shared` so offline tests can run without an active SFTP container.
    """
    if config is None:
        config = get_sftp_config()

    if isinstance(json_content, str):
        data_bytes = json_content.encode("utf-8")
    else:
        data_bytes = json_content

    if config.host.lower() in ("none", "local", "offline"):
        custom_local = os.getenv("LOCAL_SFTP_SHARED_DIR")
        if custom_local:
            local_base = Path(custom_local)
        else:
            parents = list(Path(__file__).resolve().parents)
            base_dir = parents[1] if len(parents) > 1 else parents[0]
            local_base = base_dir / "data" / "sftp-shared"
        clean_rel = remote_path.lstrip("/")
        local_target = local_base / clean_rel
        local_target.parent.mkdir(parents=True, exist_ok=True)
        local_target.write_bytes(data_bytes)
        logger.info("SFTP host set to '%s'. Saved locally to: %s", config.host, local_target)
        return remote_path

    try:
        import paramiko
    except ImportError as exc:
        raise SftpError(
            "Het pakket 'paramiko' is niet geïnstalleerd. Installeer het via: pip install paramiko"
        ) from exc

    transport = None
    try:
        transport = paramiko.Transport((config.host, config.port))
        transport.banner_timeout = config.timeout
        transport.connect(username=config.user, password=config.password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        sftp.get_channel().settimeout(config.timeout)

        remote_dir = posixpath.dirname(remote_path)
        _sftp_makedirs(sftp, remote_dir)

        with sftp.open(remote_path, "wb") as remote_file:
            remote_file.write(data_bytes)

        logger.info("Mapping package successfully uploaded to SFTP %s:%s: %s", config.host, config.port, remote_path)
        return remote_path
    except Exception as exc:
        msg = f"Fout bij uploaden naar SFTP {config.host}:{config.port} ({remote_path}): {exc}"
        logger.error(msg)
        raise SftpError(msg) from exc
    finally:
        if transport is not None:
            try:
                transport.close()
            except Exception:
                pass


def save_mapping_package_to_sftp(
    package: MappingPackage,
    company: str,
    version: str | int,
    message_type: str,
    user_created: str = "analist_a",
    package_version: str | None = None,
    config: SftpConfig | None = None,
) -> str:
    """Ensure metadata header is present and upload the MappingPackage directly to SFTP."""
    if config is None:
        config = get_sftp_config()

    clean_company = normalize_slug(company)
    clean_type = normalize_slug(message_type)
    resolved_pkg_ver = package_version or format_semver(version)

    # Attach metadata header if not already present
    if package.meta is None:
        now_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        package.meta = PackageMeta(
            client_name=clean_company,
            package_version=resolved_pkg_ver,
            package_type=clean_type,
            date_created=now_utc,
            user_created=user_created or "analist_a",
        )

    remote_path = build_package_sftp_path(
        company=company,
        version=version,
        message_type=message_type,
        base_dir=config.packages_dir,
    )
    json_str = package.model_dump_json(indent=2)
    return save_json_to_sftp(json_str, remote_path, config=config)


def _clean_alphanumeric(text: str) -> str:
    """Normalize text by keeping only lowercase alphanumeric characters."""
    return re.sub(r"[^a-z0-9]+", "", text.strip().lower())


def download_proposal_excel_from_sftp(
    company: str,
    version: str | int,
    proposal_type: str,
    config: SftpConfig | None = None,
) -> tuple[bytes, str]:
    """Retrieve an Excel proposal file from SFTP for the given company, version, and proposal type.

    Checks '/Proposals/<company>/<version>/<type>/' (and falls back to
    '/Proposals/<company>/<version>/' if type subfolder does not exist).
    Returns (file_bytes, remote_file_path).
    Raises SftpFileNotFoundError if the folder or workbook is not found.
    Raises SftpError if a connection or transfer error occurs.
    """
    if config is None:
        config = get_sftp_config()

    clean_company = normalize_slug(company)
    clean_version = normalize_version(version)
    clean_type = normalize_slug(proposal_type)
    c_norm = _clean_alphanumeric(company)
    v_norm = _clean_alphanumeric(clean_version)
    t_norm = _clean_alphanumeric(clean_type)

    # 1. Local fallback for offline/test environments
    if config.host.lower() in ("none", "local", "offline"):
        local_bases: list[Path] = []
        custom_local = os.getenv("LOCAL_SFTP_SHARED_DIR")
        if custom_local:
            local_bases.append(Path(custom_local))

        parents = list(Path(__file__).resolve().parents)
        repo_root = parents[1] if len(parents) > 1 else parents[0]
        local_bases.extend(
            [
                repo_root / "data" / "sftp-shared",
                repo_root / "data" / "shared-sftp",
                repo_root / "Mapping_Proposal" / "data" / "sftp-shared",
                repo_root,
                Path("data/sftp-shared").resolve(),
                Path("data/shared-sftp").resolve(),
            ]
        )

        for base in local_bases:
            if not base.exists():
                continue

            clean_prop = config.proposals_dir.lstrip("/")
            candidate_roots = [
                base / clean_prop,
                base / clean_prop.lower(),
                base / clean_prop.capitalize(),
                base / "Proposals",
                base / "proposals",
                base,
            ]

            for prop_root in candidate_roots:
                if not prop_root.is_dir():
                    continue

                # Match company directory
                matched_company_dir = None
                for c_cand in prop_root.iterdir():
                    if c_cand.is_dir() and (
                        _clean_alphanumeric(c_cand.name) == c_norm or normalize_slug(c_cand.name) == clean_company
                    ):
                        matched_company_dir = c_cand
                        break

                if not matched_company_dir:
                    continue

                # Match version directory
                matched_version_dir = None
                for v_cand in matched_company_dir.iterdir():
                    if v_cand.is_dir() and (
                        normalize_version(v_cand.name) == clean_version
                        or _clean_alphanumeric(v_cand.name) in (v_norm, _clean_alphanumeric(str(version)))
                    ):
                        matched_version_dir = v_cand
                        break

                if not matched_version_dir:
                    continue

                # Check type directory
                matched_type_dir = None
                for t_cand in matched_version_dir.iterdir():
                    if t_cand.is_dir() and _clean_alphanumeric(t_cand.name) == t_norm:
                        matched_type_dir = t_cand
                        break

                search_dirs = [matched_type_dir, matched_version_dir] if matched_type_dir else [matched_version_dir]

                for search_dir in search_dirs:
                    if not search_dir or not search_dir.is_dir():
                        continue

                    # Check metadata for filename
                    preferred_file = None
                    for meta_name in ("proposal.json", "metadata.json"):
                        meta_file = search_dir / meta_name
                        if meta_file.is_file():
                            try:
                                meta_data = json.loads(meta_file.read_text(encoding="utf-8-sig"))
                                if meta_data.get("filename"):
                                    cand = search_dir / meta_data["filename"]
                                    if cand.is_file():
                                        preferred_file = cand
                                        break
                            except Exception:
                                pass

                    if preferred_file:
                        logger.info("Found proposal Excel locally via metadata: %s", preferred_file)
                        return preferred_file.read_bytes(), str(preferred_file)

                    # Scan for .xlsx / .xls files
                    excels = [
                        f
                        for f in search_dir.iterdir()
                        if f.is_file() and f.suffix.lower() in (".xlsx", ".xls") and not f.name.startswith(".")
                    ]
                    if excels:
                        # Prefer ones starting with mproposal
                        mprop = [f for f in excels if f.name.lower().startswith("mproposal")]
                        chosen = mprop[0] if mprop else excels[0]
                        logger.info("Found proposal Excel locally: %s", chosen)
                        return chosen.read_bytes(), str(chosen)

        raise SftpFileNotFoundError(
            f"No Excel proposal file found on local storage for company '{company}', "
            f"version '{version}', type '{proposal_type}'."
        )

    # 2. Live SFTP retrieval via Paramiko
    try:
        import paramiko
    except ImportError as exc:
        raise SftpError(
            "Het pakket 'paramiko' is niet geïnstalleerd. Installeer het via: pip install paramiko"
        ) from exc

    transport = None
    try:
        transport = paramiko.Transport((config.host, config.port))
        transport.banner_timeout = config.timeout
        transport.connect(username=config.user, password=config.password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        sftp.get_channel().settimeout(config.timeout)

        # 1. Locate proposals directory
        proposals_dir = config.proposals_dir
        company_entries = None
        for cand_dir in (proposals_dir, proposals_dir.lower(), "/Proposals", "/proposals"):
            try:
                company_entries = sftp.listdir(cand_dir)
                proposals_dir = cand_dir
                break
            except OSError:
                continue

        if company_entries is None:
            raise SftpFileNotFoundError(f"Proposals directory '{config.proposals_dir}' does not exist on SFTP.")

        # 2. Locate company directory
        matched_company_name = None
        for entry in company_entries:
            if _clean_alphanumeric(entry) == c_norm or normalize_slug(entry) == clean_company:
                matched_company_name = entry
                break

        if not matched_company_name:
            raise SftpFileNotFoundError(f"Company directory for '{company}' not found on SFTP at {proposals_dir}.")

        company_path = posixpath.join(proposals_dir, matched_company_name)

        # 3. Locate version directory
        try:
            version_entries = sftp.listdir(company_path)
        except OSError as exc:
            raise SftpFileNotFoundError(f"Could not read company directory '{company_path}' on SFTP: {exc}") from exc

        matched_version_name = None
        for entry in version_entries:
            if normalize_version(entry) == clean_version or _clean_alphanumeric(entry) in (
                v_norm,
                _clean_alphanumeric(str(version)),
            ):
                matched_version_name = entry
                break

        if not matched_version_name:
            raise SftpFileNotFoundError(
                f"Version directory for '{version}' not found for company '{company}' at {company_path} on SFTP."
            )

        version_path = posixpath.join(company_path, matched_version_name)

        # 4. Locate type directory or fallback to version directory
        try:
            type_or_file_entries = sftp.listdir(version_path)
        except OSError as exc:
            raise SftpFileNotFoundError(f"Could not read version directory '{version_path}' on SFTP: {exc}") from exc

        matched_type_name = None
        for entry in type_or_file_entries:
            if _clean_alphanumeric(entry) == t_norm:
                matched_type_name = entry
                break

        target_dirs = []
        if matched_type_name:
            target_dirs.append(posixpath.join(version_path, matched_type_name))
        target_dirs.append(version_path)

        chosen_file_path = None
        for target_dir in target_dirs:
            try:
                target_entries = sftp.listdir(target_dir)
            except OSError:
                continue

            # Check metadata.json or proposal.json
            for meta_name in ("proposal.json", "metadata.json"):
                if meta_name in target_entries:
                    try:
                        with sftp.open(posixpath.join(target_dir, meta_name), "r") as mf:
                            meta_content = mf.read()
                            if isinstance(meta_content, bytes):
                                meta_content = meta_content.decode("utf-8-sig")
                            meta_data = json.loads(meta_content)
                            preferred = meta_data.get("filename")
                            if preferred and preferred in target_entries:
                                chosen_file_path = posixpath.join(target_dir, preferred)
                                break
                    except Exception:
                        pass
                if chosen_file_path:
                    break

            if chosen_file_path:
                break

            excel_files = [f for f in target_entries if f.lower().endswith((".xlsx", ".xls")) and not f.startswith(".")]
            if excel_files:
                mprop = [f for f in excel_files if f.lower().startswith("mproposal")]
                chosen_name = mprop[0] if mprop else excel_files[0]
                chosen_file_path = posixpath.join(target_dir, chosen_name)
                break

        if not chosen_file_path:
            raise SftpFileNotFoundError(
                f"No Excel proposal file (.xlsx) found for company '{company}', "
                f"version '{version}', type '{proposal_type}' at {version_path} on SFTP."
            )

        with sftp.open(chosen_file_path, "rb") as rf:
            contents = rf.read()

        logger.info(
            "Successfully retrieved proposal Excel from SFTP %s:%s at %s (%d bytes)",
            config.host,
            config.port,
            chosen_file_path,
            len(contents),
        )
        return contents, chosen_file_path

    except SftpFileNotFoundError:
        raise
    except SftpError:
        raise
    except Exception as exc:
        msg = f"Fout bij ophalen van proposal van SFTP {config.host}:{config.port}: {exc}"
        logger.error(msg)
        raise SftpError(msg) from exc
    finally:
        if transport is not None:
            try:
                transport.close()
            except Exception:
                pass
