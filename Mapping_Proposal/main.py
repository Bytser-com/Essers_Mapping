"""Essers XML mapping prototype: command-line entry point.

Run ``python main.py --preview`` first, then ``python main.py``.
All logic lives in ``scripts/pipeline.py``; this file only reads the command-line
options and prints the result, so the same pipeline can also be used by an API.
"""
from __future__ import annotations

import argparse
import logging
import sys

from scripts.errors import MappingError
from scripts.models import MappingSettings
from scripts.pipeline import log_preview, preview_mapping, run_mapping
from services.proposal_runner import run_for_customer


# ---------------------------------------------------------------------------
# Command-line options. Names and defaults are unchanged from the original
# main.py, so every command in the README keeps working.
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Create an AI source-to-target mapping proposal from XML examples.')
    parser.add_argument('--history-pairs', type=int, default=1,
                        help='Complete original/converted examples from EACH historical company (default 1).')
    parser.add_argument('--source-samples', type=int, default=2,
                        help='Complete raw new-customer XML examples sent to Gemini (default 2).')
    parser.add_argument('--max-source-chars', type=int, default=180000,
                        help='Combined character budget for raw new-customer examples (default 180000).')
    parser.add_argument('--limit-targets', type=int, default=10,
                        help='Number of target fields to propose (default 10, 0 = all).')
    parser.add_argument('--batch-size', type=int, default=10,
                        help='Target fields per Gemini request (default 10).')
    parser.add_argument('--target-segment', default='',
                        help='Optional target segment filter, e.g. E1BPOBDLVITEM.')
    parser.add_argument('--model', default='', help='Optional override for GEMINI_MODEL from .env.')
    parser.add_argument('--customer', default='',
                        help='Customer name: register the run as a proposal, so the overview shows its status.')
    parser.add_argument('--preview', action='store_true',
                        help='Show exactly what would be sent, without calling Gemini.')
    return parser


# ---------------------------------------------------------------------------
# Logging: the scripts use ``logging`` instead of ``print``. Here we route those
# messages to the console so the output looks the same as before.
# ---------------------------------------------------------------------------
class _ConsoleFormatter(logging.Formatter):
    """Plain messages for progress; a level prefix for warnings and errors."""

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        return message if record.levelno <= logging.INFO else f'{record.levelname}: {message}'


def _configure_logging() -> None:
    # Only our own 'scripts.*' loggers are shown; noisy library loggers
    # (httpx, google-genai) stay silent.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_ConsoleFormatter())
    for name in ('scripts', 'services'):  # the AI pipeline and the proposal services
        tool_logger = logging.getLogger(name)
        tool_logger.handlers[:] = [handler]
        tool_logger.setLevel(logging.INFO)
        tool_logger.propagate = False


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Convert the command-line options into the settings object that the
    # pipeline (and later the API) understands.
    settings = MappingSettings(
        history_pairs=args.history_pairs, source_samples=args.source_samples,
        max_source_chars=args.max_source_chars, limit_targets=args.limit_targets,
        batch_size=args.batch_size, target_segment=args.target_segment, model=args.model,
    )
    # Invalid numbers (e.g. --batch-size 0) are reported as a normal argparse error.
    try:
        settings.validate()
    except ValueError as error:
        parser.error(str(error))
    _configure_logging()

    # Expected problems (missing key, bad input data, Gemini quota) arrive as a
    # MappingError and are shown as one readable line instead of a traceback.
    # Exit codes: 0 = success, 1 = error, 130 = stopped with Ctrl+C.
    try:
        if args.preview:
            log_preview(preview_mapping(settings))
            print('Preview only: no Gemini request and no Excel output.')
        elif args.customer:
            # The proposals overview shows "AI maakt voorstel / Bezig" during this run.
            run_for_customer(args.customer, settings)
        else:
            run_mapping(settings)
    except MappingError as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('Interrupted. Completed batches are saved; run the same command to resume.', file=sys.stderr)
        return 130
    return 0


if __name__ == '__main__':
    sys.exit(main())
