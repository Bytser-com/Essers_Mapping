"""Start the AI automatically for every upload that arrives in the source folder.

Agreement with the upload story (whoever stores the uploaded files):

    data/source/<upload-id>/            one new folder per upload (any unique name);
                                        INCOMING_DIR overrides data/source/
        order_1.xml, order_2.xml, ...   one or more XML files of that upload
        upload.json                     written LAST: {"customer": "Ostavel"}

``upload.json`` marks the upload as complete, so an upload of several files is never
started halfway. All XML files of one upload together give one proposal for that customer.

What the watcher does with a complete upload:
    1. claims it (renames <upload-id> to <upload-id>.processing, atomic, so it is
       picked up only once),
    2. creates the proposal on SFTP straight away: a new row "AI maakt voorstel",
    3. runs the AI; the Excel goes to SFTP and the row becomes "Klaar om na te kijken",
    4. deletes the uploaded files when the proposal is ready (the Excel is on SFTP);
       a failed upload is moved to failed/ with an error.txt, so it can be checked.
Uploads are registered all at once but handled by the AI one after another (a queue,
oldest first); uploads that arrive while the AI is busy join the end of the queue.

Runs inside the API (started in api.py), or separately:
    python -m services.incoming_watcher          keep watching
    python -m services.incoming_watcher --once   handle what is there now, then stop
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from scripts.config import (
    ai_batch_size,
    ai_history_pairs,
    ai_limit_targets,
    ai_retry_delay_seconds,
    ai_retry_max_attempts,
    ai_retry_max_delay_seconds,
    ai_source_samples,
    incoming_dir,
    incoming_poll_seconds,
)
from scripts.models import MappingSettings

from .proposal_runner import RunMapping, generate_proposal, is_retryable_gemini_error, start_proposal
from .proposals import AiStatus, ProposalRef, ProposalStatus, ProposalStore
from .storage import proposal_storage

logger = logging.getLogger(__name__)

UPLOAD_MARKER = 'upload.json'
PROPOSAL_REF = 'proposal_ref.json'
PROCESSING_SUFFIX = '.processing'
PROCESSED_DIR = 'processed'
FAILED_DIR = 'failed'
RETRY_STATE = 'retry_state.json'


def configure_ai_logging() -> None:
    """Enable AI batch INFO messages in Uvicorn without noisy dependency logs."""
    for name in ('scripts', 'services'):
        component = logging.getLogger(name)
        component.setLevel(logging.INFO)
        if not component.hasHandlers():
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
            component.addHandler(handler)


@dataclass
class ClaimedUpload:
    folder: Path        # <INCOMING_DIR>/<upload-id>.processing
    ref: ProposalRef    # the proposal (row) created for it


class IncomingWatcher:
    def __init__(self, incoming: Path, store: ProposalStore,
                 settings: MappingSettings | None = None, run: RunMapping | None = None):
        self.incoming = Path(incoming)
        self.store = store
        self.settings = settings or MappingSettings()
        self.run = run

    # -- One pass ------------------------------------------------------------------

    def run_once(self) -> int:
        """Handle the queue: register every complete upload, then let the AI handle them one
        by one (oldest first). Uploads that arrive meanwhile get their row on Home right away
        and join the end of the queue. Returns the number of uploads handled."""
        # Check previously interrupted uploads BEFORE claiming new ones, to avoid
        # enqueueing each newly claimed .processing folder twice.
        queue = self.ready_retries()
        queue.extend(self.register_new_uploads())
        handled = 0
        while queue:
            self.process(queue.pop(0))
            handled += 1
            queue.extend(self.register_new_uploads())
        return handled

    def register_new_uploads(self) -> list[ClaimedUpload]:
        """Claim complete uploads (oldest first) and give each its row on Home right away."""
        if not self.incoming.is_dir():
            return []
        ready = [folder for folder in self.incoming.iterdir()
                 if folder.is_dir() and not _is_internal(folder.name) and (folder / UPLOAD_MARKER).is_file()]
        ready.sort(key=lambda folder: (folder / UPLOAD_MARKER).stat().st_mtime)
        claimed = []
        for folder in ready:
            claimed_folder = folder.with_name(folder.name + PROCESSING_SUFFIX)
            try:
                os.rename(folder, claimed_folder)  # atomic: only one watcher wins
            except OSError:
                continue  # taken by another watcher, or just removed
            try:
                customer = _read_customer(claimed_folder)
                if not any(claimed_folder.glob('*.xml')):
                    raise ValueError('the upload contains no XML files')
            except (OSError, ValueError) as error:
                logger.warning(f'Upload {folder.name} rejected: {error}')
                self._finish(claimed_folder, FAILED_DIR, error=str(error))
                continue
            try:
                ref = start_proposal(customer, self.store)
            except Exception as error:
                # Storage (SFTP) not reachable: give the upload back, it is retried next time.
                logger.warning(f'Upload {folder.name} waits: proposal could not be created: {error}')
                os.rename(claimed_folder, folder)
                continue
            (claimed_folder / PROPOSAL_REF).write_text(json.dumps(
                {'customer': ref.customer, 'version': ref.version, 'folder': ref.folder}), encoding='utf-8')
            claimed.append(ClaimedUpload(claimed_folder, ref))
        return claimed

    def process(self, upload: ClaimedUpload) -> bool:
        """Run one upload, preserving its proposal version on temporary failures."""
        try:
            generate_proposal(upload.ref, self.settings, upload.folder, self.store,
                              self.run, retry_temporary=True)
        except Exception as error:
            if is_retryable_gemini_error(error):
                state = self._read_retry_state(upload.folder)
                attempts = int(state.get('attempts', 0)) + 1
                maximum = ai_retry_max_attempts()
                if attempts < maximum:
                    delay = min(ai_retry_delay_seconds() * (2 ** (attempts - 1)),
                                ai_retry_max_delay_seconds())
                    state = {'attempts': attempts, 'next_retry_at': time.time() + delay,
                             'last_error': f'{type(error).__name__}: {error}'[:300]}
                    self._write_retry_state(upload.folder, state)
                    logger.warning('Proposal %s: temporary Gemini failure (%s); '
                                   'scheduled attempt %d/%d in %.0f seconds. '
                                   'Same proposal and checkpoints retained.',
                                   upload.ref.id, error, attempts + 1, maximum, delay)
                    return False
                self.store.set_status(upload.ref, ProposalStatus.AI_GENERATING, AiStatus.FAILED,
                                      error=f'Gemini failed after {maximum} job attempts: {error}'[:300])
                logger.warning('Proposal %s: maximum %d upload attempts exhausted.',
                               upload.ref.id, maximum)
            logger.warning('Upload %s: %s: %s', upload.folder.name,
                           type(error).__name__, error)
            self._finish(upload.folder, FAILED_DIR,
                         error=f'{type(error).__name__}: {error}')
            return False
        # Done: the proposal is on SFTP, so the uploaded source files are not needed anymore.
        shutil.rmtree(upload.folder, ignore_errors=True)
        return True

    @staticmethod
    def _read_retry_state(folder: Path) -> dict:
        file = folder / RETRY_STATE
        if not file.is_file():
            return {}
        return json.loads(file.read_text(encoding='utf-8'))

    @staticmethod
    def _write_retry_state(folder: Path, data: dict) -> None:
        file = folder / RETRY_STATE
        temp = file.with_suffix('.json.tmp')
        temp.write_text(json.dumps(data, indent=2), encoding='utf-8')
        os.replace(temp, file)

    def ready_retries(self) -> list[ClaimedUpload]:
        """Resume due uploads, including those interrupted by an API restart."""
        if not self.incoming.is_dir():
            return []
        ready = []
        for folder in sorted(self.incoming.glob('*' + PROCESSING_SUFFIX)):
            ref_file = folder / PROPOSAL_REF
            if not ref_file.is_file():
                continue
            try:
                state = self._read_retry_state(folder)
                if float(state.get('next_retry_at', 0)) > time.time():
                    continue
                data = json.loads(ref_file.read_text(encoding='utf-8'))
                ref = ProposalRef(customer=data['customer'], version=data['version'],
                                  folder=str(data['folder']))
                ready.append(ClaimedUpload(folder, ref))
            except (ValueError, TypeError, KeyError, OSError) as error:
                logger.warning('Cannot resume upload %s: %s', folder.name, error)
        return ready

    def recover_interrupted(self) -> int:
        """Keep interrupted uploads and their checkpoints available after restart."""
        pending = sum(1 for folder in self.incoming.glob('*' + PROCESSING_SUFFIX)
                      if (folder / PROPOSAL_REF).is_file()) if self.incoming.is_dir() else 0
        if pending:
            logger.info('Found %d interrupted/in-progress upload(s); resuming when due.', pending)
        return pending

    # -- Keep watching -------------------------------------------------------------

    def watch(self, stop: threading.Event, interval: float) -> None:
        """Check the folder every ``interval`` seconds until ``stop`` is set."""
        configure_ai_logging()
        self.recover_interrupted()
        logger.info(f'Watching {self.incoming} for uploads (every {interval:g} s).')
        while not stop.is_set():
            try:
                self.run_once()
            except Exception:  # never let one bad upload stop the watcher
                logger.exception('Incoming watcher: unexpected error; continuing.')
            stop.wait(interval)

    # -- Helpers -------------------------------------------------------------------

    def _finish(self, folder: Path, target: str, error: str = '') -> None:
        """Move a handled upload out of the way, so it is never picked up again."""
        destination_root = self.incoming / target
        destination_root.mkdir(parents=True, exist_ok=True)
        name = folder.name.removesuffix(PROCESSING_SUFFIX)
        destination, counter = destination_root / name, 1
        while destination.exists():
            counter += 1
            destination = destination_root / f'{name}-{counter}'
        if error:
            (folder / 'error.txt').write_text(error + '\n', encoding='utf-8')
        os.replace(folder, destination)


def _is_internal(name: str) -> bool:
    return name in {PROCESSED_DIR, FAILED_DIR} or name.endswith(PROCESSING_SUFFIX)


def _read_customer(folder: Path) -> str:
    data = json.loads((folder / UPLOAD_MARKER).read_text(encoding='utf-8-sig'))
    customer = str(data.get('customer') or '').strip() if isinstance(data, dict) else ''
    if not customer:
        raise ValueError(f'{UPLOAD_MARKER} has no customer name')
    return customer


def default_watcher(run: RunMapping | None = None) -> IncomingWatcher:
    """Watcher with the configured folder and storage (INCOMING_DIR, SFTP_SHARED_*, AI_LIMIT_TARGETS)."""
    return IncomingWatcher(incoming_dir(), ProposalStore(proposal_storage()),
                           MappingSettings(limit_targets=ai_limit_targets(),
                                           source_samples=ai_source_samples(),
                                           history_pairs=ai_history_pairs(),
                                           batch_size=ai_batch_size()), run)


def start_in_background(watcher_factory: Callable[[], IncomingWatcher] = default_watcher
                        ) -> tuple[threading.Thread, threading.Event]:
    """Start watching in a background thread (used by api.py). Set the event to stop."""
    stop = threading.Event()
    thread = threading.Thread(target=watcher_factory().watch, args=(stop, incoming_poll_seconds()),
                              name='incoming-watcher', daemon=True)
    thread.start()
    return thread, stop


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description='Start the AI for every complete upload in INCOMING_DIR.')
    parser.add_argument('--once', action='store_true', help='Handle the uploads that are there now, then stop.')
    args = parser.parse_args(argv)
    configure_ai_logging()
    watcher = default_watcher()
    if args.once:
        watcher.recover_interrupted()
        print(f'{watcher.run_once()} upload(s) handled.')
        return
    try:
        watcher.watch(threading.Event(), incoming_poll_seconds())
    except KeyboardInterrupt:
        print('Stopped.')


if __name__ == '__main__':
    main()
