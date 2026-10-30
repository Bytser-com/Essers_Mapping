"""Input and output data structures of the mapping pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MappingSettings:
    """What to send to Gemini. Defaults match the original command-line defaults."""

    history_pairs: int = 1          # complete original/converted pairs per historical company
    source_samples: int = 2         # complete raw new-customer XMLs sent to Gemini
    max_source_chars: int = 180000  # combined character budget for those raw XMLs
    limit_targets: int = 10         # number of target fields to propose (0 = all)
    batch_size: int = 10            # target fields per Gemini request
    target_segment: str = ''        # optional target segment filter, e.g. E1BPOBDLVITEM
    model: str = ''                 # optional override of GEMINI_MODEL
    source_dir: Path | None = None  # folder with the new customer's XML (default: data/source)

    def validate(self) -> None:
        # Same rule as the original main.py: counts may be 0 where that has a
        # meaning ("no history" / "all targets"), all other numbers must be >= 1.
        if (self.history_pairs < 0 or self.source_samples < 1 or self.max_source_chars < 1
                or self.limit_targets < 0 or self.batch_size < 1):
            raise ValueError('history-pairs and limit-targets must be >=0; other numbers must be >=1.')


# Returned by preview_mapping(). Contains only counts and file names, never XML
# content, so it is safe to show in a console or (later) an API response.
@dataclass
class PreviewResult:
    """What a run with these settings would send, without calling Gemini."""

    companies: dict[str, int]
    source_file_count: int
    source_field_count: int
    converted_file_count: int
    target_path_count: int
    selected_target_count: int
    source_documents: list[str]
    historical_documents: list[str]
    first_request_chars: int
    batch_count: int
    source_budget_warning: bool


# Returned by run_mapping(). The Excel file itself stays on disk at workbook_path.
@dataclass
class MappingResult:
    """Outcome of a completed mapping run."""

    run_id: str
    run_dir: Path
    workbook_path: Path
    mapping_rows: int
    placeholders: int
    rejected_proposals: int
    structural_issues: int
    batches_restored: int = 0
    warnings: list[str] = field(default_factory=list)
