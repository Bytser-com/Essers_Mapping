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
    4. moves the upload to processed/ (or failed/ with an error.txt).
Uploads are registered all at once but handled by the AI one after another.

Runs inside the API (started in api.py), or separately:
    python -m services.incoming_watcher          keep watching
    python -m services.incoming_watcher --once   handle what is there now, then stop
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import threading
from typing import Callable

from scripts.config import ai_limit_targets, incoming_dir, incoming_poll_seconds, proposals_dir
from scripts.models import MappingSettings
from .proposal_runner import RunMapping, generate_proposal, start_proposal
from .proposals import AiStatus, ProposalRef, ProposalStatus, ProposalStore

logger = logging.getLogger(__name__)

UPLOAD_MARKER = 'upload.json'
PROPOSAL_REF = 'proposal_ref.json'
PROCESSING_SUFFIX = '.processing'
PROCESSED_DIR = 'processed'
FAILED_DIR = 'failed'


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
        """Register every complete upload, then let the AI handle them. Returns the count."""
        claimed = self.register_new_uploads()
        for upload in claimed:
            self.process(upload)
        return len(claimed)

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
            ref = start_proposal(customer, self.store)
            (claimed_folder / PROPOSAL_REF).write_text(json.dumps(
                {'customer': ref.customer, 'version': ref.version, 'folder': str(ref.folder)}), encoding='utf-8')
            claimed.append(ClaimedUpload(claimed_folder, ref))
        return claimed

    def process(self, upload: ClaimedUpload) -> bool:
        """Run the AI for one registered upload. Returns True when the proposal is ready."""
        try:
            generate_proposal(upload.ref, self.settings, upload.folder, self.store, self.run)
        except Exception as error:  # the status is already "Mislukt"; keep watching
            logger.warning(f'Upload {upload.folder.name}: {type(error).__name__}: {error}')
            self._finish(upload.folder, FAILED_DIR, error=f'{type(error).__name__}: {error}')
            return False
        self._finish(upload.folder, PROCESSED_DIR)
        return True

    def recover_interrupted(self) -> int:
        """After a restart: uploads that were still being processed are marked "Mislukt",
        so no row stays on "Bezig". Call once at start-up, before watching."""
        if not self.incoming.is_dir():
            return 0
        count = 0
        for folder in self.incoming.glob('*' + PROCESSING_SUFFIX):
            ref_file = folder / PROPOSAL_REF
            if ref_file.is_file():
                data = json.loads(ref_file.read_text(encoding='utf-8'))
                ref = ProposalRef(customer=data['customer'], version=data['version'], folder=Path(data['folder']))
                if (ref.folder / 'proposal.json').is_file():
                    self.store.set_status(ref, ProposalStatus.AI_GENERATING, AiStatus.FAILED,
                                          error='Interrupted: the service restarted during the AI run.')
            self._finish(folder, FAILED_DIR, error='Interrupted: the service restarted during the AI run.')
            count += 1
        return count

    # -- Keep watching -------------------------------------------------------------

    def watch(self, stop: threading.Event, interval: float) -> None:
        """Check the folder every ``interval`` seconds until ``stop`` is set."""
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
    """Watcher with the configured folders (INCOMING_DIR, SHARED_MOUNT_PATH, AI_LIMIT_TARGETS)."""
    return IncomingWatcher(incoming_dir(), ProposalStore(proposals_dir()),
                           MappingSettings(limit_targets=ai_limit_targets()), run)


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
    logging.basicConfig(level=logging.INFO, format='%(message)s')
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
