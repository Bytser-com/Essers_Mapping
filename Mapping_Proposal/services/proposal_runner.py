"""Run the AI mapping for one customer and keep its proposal status up to date.

While the AI works, the proposals overview shows "AI maakt voorstel" + "Bezig".
Afterwards it shows "Klaar om na te kijken", or "Mislukt" when the run failed.

Only the result goes to the shared storage (the SFTP server, see services/proposals.py);
the uploaded XML files stay local and are not copied to SFTP:

    <customer folder>/v<N>/
        proposal.json            status, updated during the run
        MProposal-<Klant>_V<N>.xlsx   the AI result, once the run succeeded
                                      (e.g. MProposal-Brunos_V2.xlsx, see workbook_name())

Two steps, so several uploads can all get their row ("AI maakt voorstel") straight
away while the AI handles them one by one (see services/incoming_watcher.py):
    start_proposal()     -> new row in the overview
    generate_proposal()  -> AI run, Excel to SFTP, status "Klaar om na te kijken"
"""
from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from scripts.config import SOURCE_DIR
from scripts.errors import GeminiError, InputDataError
from scripts.models import MappingResult, MappingSettings

from .proposals import AiStatus, ProposalRef, ProposalStatus, ProposalStore
from .storage import proposal_storage

logger = logging.getLogger(__name__)

def workbook_name(customer: str, version: int) -> str:
    """File name of the Excel proposal on SFTP: MProposal-<Klant>_V<N>.xlsx.

    The customer name keeps its capitals; spaces, accents and characters that are not
    allowed in file names are left out: "Brunos", 2 -> "MProposal-Brunos_V2.xlsx",
    "Voorbeeldbedrijf A", 1 -> "MProposal-VoorbeeldbedrijfA_V1.xlsx".
    """
    ascii_name = unicodedata.normalize('NFKD', customer).encode('ascii', 'ignore').decode('ascii')
    name = re.sub(r'[^A-Za-z0-9-]+', '', ascii_name) or 'Klant'
    return f'MProposal-{name}_V{version}.xlsx'

RunMapping = Callable[[MappingSettings], MappingResult]

def is_retryable_gemini_error(error: BaseException) -> bool:
    """Only transient Gemini failures can keep an upload in RUNNING state."""
    if not isinstance(error, GeminiError):
        return False
    if error.code == 429:
        # Unknown/daily quota errors are not safe to retry indefinitely.
        return 'minute quota' in str(error).lower()
    return error.code in (500, 502, 503, 504, 'timeout')



def _default_run() -> RunMapping:
    from scripts.pipeline import (
        run_mapping,  # imported here: tests do not need Gemini packages
    )
    return run_mapping


def start_proposal(customer: str, store: ProposalStore) -> ProposalRef:
    """Step 1: the new row appears in the overview: "AI maakt voorstel" / "Bezig"."""
    ref = store.create_proposal(customer)
    logger.info(f'Proposal {ref.id} created for {ref.customer}; AI status: running.')
    return ref


def generate_proposal(
    ref: ProposalRef,
    settings: MappingSettings,
    source_dir: Path,
    store: ProposalStore,
    run: RunMapping | None = None,
    *,
    retry_temporary: bool = False,
) -> MappingResult:
    """Step 2: let the AI analyse the XML in ``source_dir`` and store the Excel on SFTP.

    For automatic uploads, transient Gemini failures keep the status RUNNING so
    the watcher can resume the same checkpoints. Permanent errors still fail.
    """
    run = run or _default_run()
    try:
        if not any(Path(source_dir).glob('*.xml')):
            raise InputDataError(f'No customer XML files in {source_dir}.')
        result = run(replace(settings, source_dir=Path(source_dir)))
        store.save_file(ref, result.workbook_path, workbook_name(ref.customer, ref.version))
    except BaseException as error:
        if retry_temporary and is_retryable_gemini_error(error):
            logger.warning('Proposal %s: temporary Gemini failure; keeping it in progress.', ref.id)
        else:
            store.set_status(ref, ProposalStatus.AI_GENERATING, AiStatus.FAILED,
                             error=f'{type(error).__name__}: {error}'[:300])
            logger.warning('Proposal %s: AI run failed.', ref.id)
        raise

    # Done: "Klaar om na te kijken".
    store.set_status(ref, ProposalStatus.READY_FOR_REVIEW, None)
    logger.info(f'Proposal {ref.id} is ready for review.')
    return result


def run_for_customer(
    customer: str,
    settings: MappingSettings,
    *,
    source_dir: Path = SOURCE_DIR,
    store: ProposalStore | None = None,
    run: RunMapping | None = None,
) -> tuple[ProposalRef, MappingResult]:
    """Both steps at once (used by ``python main.py --customer``).

    ``store`` and ``run`` can be replaced in tests, so no real Gemini call or SFTP share is needed.
    """
    store = store or ProposalStore(proposal_storage())
    if not any(Path(source_dir).glob('*.xml')):
        raise InputDataError(f'No customer XML files in {source_dir}.')  # no row for an empty upload
    ref = start_proposal(customer, store)
    return ref, generate_proposal(ref, settings, source_dir, store, run)
