"""Find observed exact-value correspondences in the historical XML pairs.

This is an independent, deterministic reference-evidence report. It does not
propose mappings, infer business rules, or ask Gemini to do a second task.

Only pairs selected for Gemini's prompt are inspected. Every reported value
must really occur at the stated path in BOTH files of the same historical pair.
Matches are unverified mapping *candidates*, not proof of semantic equivalence.
"""
from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
import re
import xml.etree.ElementTree as ET


def _local(tag: str) -> str:
    return tag.rsplit('}', 1)[-1].split(':')[-1]


def _values_by_path(xml_text: str) -> dict[str, set[str]]:
    """Extract literal values from XML leaves/attributes, keeping XPath-style paths."""
    root = ET.fromstring(xml_text)
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
    if re.fullmatch(r'[0-9]+', value) and len(set(value)) == 1:
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


def extract_reference_evidence(selected_pairs: list[dict], target_paths: list[str],
                               max_per_target: int = 2) -> list[dict]:
    """Return conservative, observed field-value matches for Excel's evidence tab.

    The matches are independent of Gemini's proposed source paths: a reviewer
    can see historical evidence even when Gemini proposes a bad mapping.
    Choose at most `max_per_target` matches per target, preferring distinct pairs
    and clearer source-field names. Trivial matching values are not presented.
    """
    if max_per_target < 1:
        return []
    selected_targets = list(dict.fromkeys(target_paths))
    per_target: dict[str, list[tuple]] = defaultdict(list)

    for pair in selected_pairs:
        originals = _values_by_path(pair['original_xml'])
        converted = _values_by_path(pair['converted_xml'])
        # Reverse-index values so that each target value finds matching source
        # paths efficiently (instead of comparing every possible path pair).
        by_value: dict[str, list[str]] = defaultdict(list)
        for source_path, source_values in originals.items():
            for value in source_values:
                if _informative(value):
                    by_value[value].append(source_path)

        for target_path in selected_targets:
            candidates = []
            for value in converted.get(target_path, set()):
                if not _informative(value):
                    continue
                paths = by_value.get(value, [])
                if not paths:
                    continue
                # Match may be ambiguous if the same value occurs at multiple
                # source paths. This is explicitly reported, not hidden.
                for source_path in paths:
                    similarity = _path_similarity(source_path, target_path)
                    score = (similarity, min(len(value), 30), -len(paths))
                    candidates.append((score, source_path, value, len(paths)))
            if candidates:
                # One entry per historical pair per target; favor similar
                # field names but don't present this as verified mapping logic.
                score, source_path, value, same_value_paths = max(candidates,
                    key=lambda x: (x[0], x[1], x[2]))
                ambiguous = same_value_paths > 1
                note = ('Exact nonempty value observed in BOTH historical XML files; '
                        'this does not prove the source-to-target business mapping.')
                if ambiguous:
                    note += (f' Ambiguous: this value also occurs at '
                             f'{same_value_paths} original XML paths.')
                record = {
                    'Reference pair': f"{pair['company']} / {pair['pair_id']}",
                    'Historical Original': pair['original_filename'],
                    'Historical Converted': pair['converted_filename'],
                    'Evidence type': 'Exact value match (XML-checked)',
                    'Historical source path': source_path,
                    'Historical target path': target_path,
                    'Example value': value,
                    'Evidence note': note,
                    'Usefulness': ('Ambiguous; expert review' if ambiguous
                                   else 'Candidate; expert review'),
                }
                per_target[target_path].append((score, record))

    results = []
    # Interleave targets in original target order. Limit two historical pairs
    # per target to keep Reference Evidence readable.
    for target_path in selected_targets:
        top = sorted(per_target[target_path], key=lambda x: x[0], reverse=True)
        results.extend(row for _, row in top[:max_per_target])
    return results
