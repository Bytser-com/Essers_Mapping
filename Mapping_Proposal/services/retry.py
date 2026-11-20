"""Retry stuck or failed proposals and incomplete uploads."""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from scripts.config import incoming_dir
from services.incoming_watcher import FAILED_DIR, PROCESSING_SUFFIX, PROPOSAL_REF, RETRY_STATE
from services.proposals import AiStatus, ProposalRef, ProposalStatus, ProposalStore

logger = logging.getLogger(__name__)


def retry_failed_proposals(
    store: ProposalStore,
    incoming: Path | None = None,
    customer: str | None = None,
    version: int | None = None,
    proposal_type: str | None = None,
) -> list[dict]:
    """Find all stuck (mislukt) proposals or failed uploads, reset them to running, and re-enqueue them."""
    incoming = incoming if incoming is not None else incoming_dir()
    retried: list[dict] = []
    seen_refs: set[str] = set()

    customer_filter = customer.strip().lower() if customer else None
    type_filter = proposal_type.strip().lower() if proposal_type else None

    # 1. Check incoming / failed directory for aborted/failed upload folders
    failed_dir = incoming / FAILED_DIR
    if failed_dir.is_dir():
        for folder in sorted(failed_dir.iterdir()):
            if not folder.is_dir():
                continue

            ref: ProposalRef | None = None
            ref_file = folder / PROPOSAL_REF
            if ref_file.is_file():
                try:
                    data = json.loads(ref_file.read_text(encoding='utf-8'))
                    ref = ProposalRef(
                        customer=str(data['customer']),
                        version=int(data['version']),
                        folder=str(data['folder']),
                        proposal_type=str(data.get('proposal_type') or ''),
                    )
                except Exception as e:
                    logger.warning('Failed to parse proposal_ref in %s: %s', folder.name, e)

            # Check if this matches filters if any
            if ref:
                if customer_filter and ref.customer.lower() != customer_filter:
                    continue
                if version is not None and ref.version != version:
                    continue
                if type_filter and ref.proposal_type.lower() != type_filter:
                    continue

            # Remove error and retry state files
            (folder / 'error.txt').unlink(missing_ok=True)
            (folder / RETRY_STATE).unlink(missing_ok=True)

            # Move folder back to incoming
            target_name = folder.name.removesuffix(PROCESSING_SUFFIX)
            target = incoming / target_name
            counter = 1
            while target.exists():
                counter += 1
                target = incoming / f'{target_name}-{counter}'

            try:
                shutil.move(str(folder), str(target))
                logger.info('Moved failed upload %s back to %s for retry', folder.name, target.name)
            except Exception as e:
                logger.error('Failed to move %s back to %s: %s', folder.name, target.name, e)
                continue

            if ref and store.exists(ref):
                try:
                    store.set_status(ref, ProposalStatus.AI_GENERATING, AiStatus.RUNNING)
                    seen_refs.add(ref.id)
                except Exception as e:
                    logger.warning('Failed to update status for %s: %s', ref.id, e)

            retried.append({
                'customer': ref.customer if ref else folder.name,
                'version': ref.version if ref else None,
                'proposal_type': ref.proposal_type if ref else None,
                'folder': target.name,
                'status': 're-queued',
            })

    # 2. Check incoming directory for *.processing folders with expired/exhausted retry state
    if incoming.is_dir():
        for folder in sorted(incoming.glob('*' + PROCESSING_SUFFIX)):
            if not folder.is_dir():
                continue

            ref = None
            ref_file = folder / PROPOSAL_REF
            if ref_file.is_file():
                try:
                    data = json.loads(ref_file.read_text(encoding='utf-8'))
                    ref = ProposalRef(
                        customer=str(data['customer']),
                        version=int(data['version']),
                        folder=str(data['folder']),
                        proposal_type=str(data.get('proposal_type') or ''),
                    )
                except Exception:
                    pass

            if ref:
                if customer_filter and ref.customer.lower() != customer_filter:
                    continue
                if version is not None and ref.version != version:
                    continue
                if type_filter and ref.proposal_type.lower() != type_filter:
                    continue

            # Reset retry state so watcher picks it up immediately
            retry_file = folder / RETRY_STATE
            if retry_file.is_file():
                retry_file.unlink(missing_ok=True)

            if ref and store.exists(ref):
                try:
                    store.set_status(ref, ProposalStatus.AI_GENERATING, AiStatus.RUNNING)
                    seen_refs.add(ref.id)
                except Exception as e:
                    logger.warning('Failed to update status for %s: %s', ref.id, e)

            retried.append({
                'customer': ref.customer if ref else folder.name,
                'version': ref.version if ref else None,
                'proposal_type': ref.proposal_type if ref else None,
                'folder': folder.name,
                'status': 'reset-processing',
            })

    # 3. Check proposals in store that have ai_status == FAILED
    try:
        all_proposals = store.list_proposals(all_versions=True)
    except Exception as e:
        logger.warning('Failed to list proposals from store: %s', e)
        all_proposals = []

    for prop in all_proposals:
        if prop.id in seen_refs:
            continue
        if prop.ai_status is AiStatus.FAILED or (prop.status is ProposalStatus.AI_GENERATING and prop.ai_status != AiStatus.RUNNING):
            if customer_filter and prop.customer.lower() != customer_filter:
                continue
            if version is not None and prop.version != version:
                continue
            if type_filter and prop.proposal_type.lower() != type_filter:
                continue

            ref = ProposalRef(
                customer=prop.customer,
                version=prop.version,
                folder=prop.id,
                proposal_type=prop.proposal_type,
            )
            try:
                store.set_status(ref, ProposalStatus.AI_GENERATING, AiStatus.RUNNING)
            except Exception as e:
                logger.warning('Failed to set status for %s: %s', ref.id, e)

            retried.append({
                'customer': prop.customer,
                'version': prop.version,
                'proposal_type': prop.proposal_type,
                'folder': prop.id,
                'status': 'reset-status',
            })

    return retried
