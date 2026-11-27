
"""Find observed exact-value correspondences in the historical XML pairs.

This is an independent, deterministic reference-evidence report. It does not
propose mappings, infer business rules, or ask Gemini to do a second task.

Only pairs selected for Gemini's prompt are inspected. Every reported value
must really occur at the stated path in BOTH files of the same historical pair.
Matches are unverified mapping candidates, not proof of semantic equivalence.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from difflib import SequenceMatcher

from defusedxml import ElementTree as SafeET


def _local(tag: str) -> str:
    return tag.rsplit('}', 1)[-1].split(':')[-1]


def _values_by_path(xml_text: str) -> dict[str, set[str]]:
    """Extract literal values from XML leaves/attributes, keeping XPath-style paths."""
    root = SafeET.fromstring(xml_text)
    values: dict[str, set[str]] = defaultdict(set)

    def visit(node: ET.Element, parent: str):
        path = f'{parent}/{_local(node.tag)}'

        if not list(node):
            value = (node.text or '').strip()
            if value:
                values[path].add(value)

        for name, value in node.attrib.items():
            if value.strip():
                values[f'{path}/@{_local(name)}'].add(value.strip())

        for child in node:
            visit(child, path)

    visit(root, '')
    return dict(values)


def _informative(value: str) -> bool:
    """Avoid easy coincidental matches (empty, flags, short codes, zero padding)."""
    if len(value) < 4 or len(value) > 150:
        return False

    if value.casefold() in {'true', 'false', 'none', 'null', 'yes', 'no'}:
        return False

    # ASCII mode preserves the original [0-9] matching behavior.
    if re.fullmatch(r'\d+', value, flags=re.ASCII) and len(set(value)) == 1:
        return False

    return True


def _path_similarity(source_path: str, target_path: str) -> float:
    """Sort matches for display; this score is NOT evidence of mapping correctness."""
    source_leaf = source_path.rsplit('/', 1)[-1].upper().replace('_', '')
    target_leaf = target_path.rsplit('/', 1)[-1].upper().replace('_', '')

    if source_leaf == target_leaf:
        return 1.0

    if source_leaf.endswith(target_leaf) or target_leaf.endswith(source_leaf):
        return 0.85

    return SequenceMatcher(None, source_leaf, target_leaf).ratio()


def _index_source_values(originals: dict[str, set[str]]) -> dict[str, list[str]]:
    """Index informative source values by the paths where they occur."""
    by_value: dict[str, list[str]] = defaultdict(list)

    for source_path, source_values in originals.items():
        for value in source_values:
            if _informative(value):
                by_value[value].append(source_path)

    return dict(by_value)


def _find_candidates(
    target_path: str,
    target_values: set[str],
    by_value: dict[str, list[str]],
) -> list[tuple]:
    """Find exact-value candidates for one historical target field."""
    candidates = []

    for value in target_values:
        if not _informative(value):
            continue

        paths = by_value.get(value, [])
        if not paths:
            continue

        for source_path in paths:
            similarity = _path_similarity(source_path, target_path)
            score = (similarity, min(len(value), 30), -len(paths))
            candidates.append((score, source_path, value, len(paths)))

    return candidates


def _build_evidence_record(pair: dict, target_path: str, candidate: tuple) -> dict:
    """Create an evidence record from the strongest observed candidate."""
    _, source_path, value, same_value_paths = candidate
    ambiguous = same_value_paths > 1

    note = (
        'Exact nonempty value observed in BOTH historical XML files; '
        'this does not prove the source-to-target business mapping.'
    )

    if ambiguous:
        note += (
            f' Ambiguous: this value also occurs at '
            f'{same_value_paths} original XML paths.'
        )

    return {
        'Reference pair': f"{pair['company']} / {pair['pair_id']}",
        'Historical Original': pair['original_filename'],
        'Historical Converted': pair['converted_filename'],
        'Evidence type': 'Exact value match (XML-checked)',
        'Historical source path': source_path,
        'Historical target path': target_path,
        'Example value': value,
        'Evidence note': note,
        'Usefulness': (
            'Ambiguous; expert review'
            if ambiguous
            else 'Candidate; expert review'
        ),
    }


def _collect_pair_evidence(
    pair: dict,
    selected_targets: list[str],
    per_target: dict[str, list[tuple]],
) -> None:
    """Collect the strongest exact-value match per target for one pair."""
    originals = _values_by_path(pair['original_xml'])
    converted = _values_by_path(pair['converted_xml'])
    by_value = _index_source_values(originals)

    for target_path in selected_targets:
        candidates = _find_candidates(
            target_path,
            converted.get(target_path, set()),
            by_value,
        )

        if not candidates:
            continue

        # Preserve the original ranking and deterministic tie-breaking.
        best = max(candidates, key=lambda x: (x[0], x[1], x[2]))

        record = _build_evidence_record(pair, target_path, best)
        per_target[target_path].append((best[0], record))


def extract_reference_evidence(
    selected_pairs: list[dict],
    target_paths: list[str],
    max_per_target: int = 2,
) -> list[dict]:
    """Return conservative, observed field-value matches for Excel's evidence tab.

    The matches are independent of Gemini's proposed source paths: a reviewer
    can see historical evidence even when Gemini proposes a bad mapping.

    Choose at most max_per_target matches per target, preferring distinct pairs
    and clearer source-field names. Trivial matching values are not presented.
    """
    if max_per_target < 1:
        return []

    selected_targets = list(dict.fromkeys(target_paths))
    per_target: dict[str, list[tuple]] = defaultdict(list)

    for pair in selected_pairs:
        _collect_pair_evidence(pair, selected_targets, per_target)

    results = []

    # Preserve target order and limit the number of historical pairs per target.
    for target_path in selected_targets:
        top = sorted(
            per_target[target_path],
            key=lambda x: x[0],
            reverse=True,
        )
        results.extend(row for _, row in top[:max_per_target])

    return results
