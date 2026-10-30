"""Run the AI mapping for one customer and keep its proposal status up to date.

While the AI works, the proposals overview shows "AI maakt voorstel" + "Bezig".
Afterwards it shows "Klaar om na te kijken", or "Mislukt" when the run failed.

Only the result goes to the shared storage (the SFTP share, see services/proposals.py);
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

from dataclasses import replace
import logging
from pathlib import Path
import re
import shutil
import unicodedata
from typing import Callable

from scripts.config import SOURCE_DIR, proposals_dir
from scripts.errors import InputDataError
from scripts.models import MappingResult, MappingSettings
from .proposals import AiStatus, ProposalRef, ProposalStatus, ProposalStore

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


def _default_run() -> RunMapping:
    from scripts.pipeline import run_mapping  # imported here: tests do not need Gemini packages
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
) -> MappingResult:
    """Step 2: let the AI analyse the XML in ``source_dir`` and store the Excel on SFTP.

    On any failure (also Ctrl+C) the row gets AI status "Mislukt", so it is never
    left on "Bezig"; the error is raised again for the caller.
    """
    run = run or _default_run()
    try:
        if not any(Path(source_dir).glob('*.xml')):
            raise InputDataError(f'No customer XML files in {source_dir}.')
        result = run(replace(settings, source_dir=Path(source_dir)))
        shutil.copy2(result.workbook_path, ref.folder / workbook_name(ref.customer, ref.version))
    except BaseException as error:
        store.set_status(ref, ProposalStatus.AI_GENERATING, AiStatus.FAILED,
                         error=f'{type(error).__name__}: {error}'[:300])
        logger.warning(f'Proposal {ref.id}: AI run failed.')
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
    store = store or ProposalStore(proposals_dir())
    if not any(Path(source_dir).glob('*.xml')):
        raise InputDataError(f'No customer XML files in {source_dir}.')  # no row for an empty upload
    ref = start_proposal(customer, store)
    return ref, generate_proposal(ref, settings, source_dir, store, run)
