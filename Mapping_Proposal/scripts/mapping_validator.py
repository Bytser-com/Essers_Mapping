"""Structural checks only. These do not verify business semantics.

All structural rules live here, so the batch-retry check in the pipeline and the
final validation can never disagree with each other.
"""
from collections import Counter

# The only rule types Gemini may use (also listed in prompt.txt).
RULE_TYPES = {
    'DIRECT', 'FIXED', 'DEFAULT_IF_EMPTY', 'DERIVED', 'CONDITIONAL',
    'LOOKUP', 'LOOP', 'FORMAT_DATE', 'REVIEW_REQUIRED', 'NOT_MAPPED',
}

# The 15 fields of one proposal, in the order of the Gemini response schema.
MAPPING_KEYS = (
    'source_path', 'target_path', 'rule_type', 'confidence',
    'requires_review', 'review_priority', 'reason', 'evidence',
    'fixed_value', 'transformation', 'condition', 'lookup', 'loop',
    'review_question', 'risk_category',
)


def _clean(value) -> str:
    # None becomes '' (instead of the text 'None'); surrounding spaces are removed.
    return str(value if value is not None else '').strip()


def structural_problems(proposal: dict, source_paths: set[str]) -> tuple[str, list[str]]:
    """Check one proposal's rule type, source path and fixed value.

    Returns the normalised rule type (unknown types become REVIEW_REQUIRED) and
    the list of problems found.
    """
    source_path = _clean(proposal.get('source_path'))
    rule = _clean(proposal.get('rule_type')).upper()
    problems = []
    # An unknown rule type is reported and treated as REVIEW_REQUIRED for the
    # remaining checks (same behaviour as the original validator).
    if rule not in RULE_TYPES:
        problems.append(f'Unknown rule type: {rule}')
        rule = 'REVIEW_REQUIRED'
    # Gemini may only use paths that really exist in the new customer's XML.
    if source_path and source_path not in source_paths:
        problems.append(f'Source path not found: {source_path}')
    # Only a fixed value, an open review question or an explicit "no mapping
    # possible" (NOT_MAPPED) may do without a source.
    if not source_path and rule not in {'FIXED', 'REVIEW_REQUIRED', 'NOT_MAPPED'}:
        problems.append('Non-FIXED proposal has no source path')
    # NOT_MAPPED means no source could be found, so a source path contradicts it.
    if rule == 'NOT_MAPPED' and source_path:
        problems.append('NOT_MAPPED should have an empty source path')
    if rule == 'FIXED' and not _clean(proposal.get('fixed_value')):
        problems.append('FIXED mapping has no fixed value')
    return rule, problems


def find_proposals_needing_retry(proposals: list, batch: list[dict], source_paths: set[str]) -> list[dict]:
    """Target fields of this batch that Gemini omitted, duplicated, or answered invalidly."""
    retry = []
    for field in batch:
        path = field['path']
        choices = [p for p in proposals if isinstance(p, dict) and p.get('target_path') == path]
        # Exactly one proposal per target is expected: 0 = omitted, 2+ = duplicated.
        if len(choices) != 1:
            retry.append(field)
            continue
        _, problems = structural_problems(choices[0], source_paths)
        if problems:
            retry.append(field)
    return retry



def _normalize_confidence(value, problems: list[str]) -> int:
    """Convert confidence to an integer between 0 and 100."""
    try:
        confidence = int(float(value))
    except (ValueError, TypeError):
        confidence = 0
        problems.append('Invalid confidence value')

    if not 0 <= confidence <= 100:
        confidence = max(0, min(100, confidence))
        problems.append('Confidence outside 0–100')

    return confidence


def _normalize_risk_category(value, problems: list[str]) -> str:
    """Normalize risk severity, requiring review for unsupported values."""
    risk_raw = _clean(value).upper()

    if risk_raw in {'LOW', 'MEDIUM', 'HIGH'}:
        return risk_raw

    if risk_raw == 'NONE':
        return 'LOW'

    problems.append(
        f'Risk severity must be LOW/MEDIUM/HIGH; received: {risk_raw or "(empty)"}'
    )
    return 'HIGH'


def _requires_review(value, problems: list[str], rule: str) -> bool:
    """Determine whether the proposal requires human review."""
    return (
        value is True
        or str(value).lower() in {'true', 'yes', '1'}
        or bool(problems)
        or rule == 'NOT_MAPPED'
    )


def _normalize_review_priority(mapping: dict, problems: list[str]) -> None:
    """Assign review priority when a proposal requires review."""
    if (
        mapping['requires_review']
        and str(mapping['review_priority']).lower() not in ('high', 'critical')
    ):
        mapping['review_priority'] = (
            'High' if problems else (mapping['review_priority'] or 'Medium')
        )


def _normalize_mapping(mapping: dict, source_paths: set[str]) -> list[str]:
    """Normalize mapping fields and return structural validation issues."""
    rule, problems = structural_problems(mapping, source_paths)

    mapping['target_path'] = _clean(mapping['target_path'])
    mapping['source_path'] = _clean(mapping['source_path'])
    mapping['rule_type'] = rule
    mapping['confidence'] = _normalize_confidence(
        mapping['confidence'], problems
    )
    mapping['risk_category'] = _normalize_risk_category(
        mapping.get('risk_category'), problems
    )
    mapping['requires_review'] = _requires_review(
        mapping['requires_review'], problems, rule
    )

    _normalize_review_priority(mapping, problems)

    mapping['validation_issues'] = problems
    return problems


def _flag_duplicate_targets(accepted: list[dict]) -> None:
    """Flag repeated target paths for human review."""
    counts = Counter(mapping['target_path'] for mapping in accepted)

    for mapping in accepted:
        if counts[mapping['target_path']] > 1:
            message = 'Multiple proposals for same target; verify conditions/priority'
            mapping['validation_issues'].append(message)
            mapping['requires_review'] = True



def validate_mappings(proposals: list, source_fields: list, target_fields: list):
    """Validate and normalize proposals without checking business semantics."""
    source_paths = {item['path'] for item in source_fields}
    target_paths = {item['path'] for item in target_fields}

    accepted, rejected, issues = [], [], []

    for index, original in enumerate(proposals, start=1):
        if not isinstance(original, dict):
            rejected.append({
                'index': index,
                'reason': 'Not an object',
                'proposal': original,
            })
            continue

        # Copy only the known keys; ignore extra fields from Gemini.
        mapping = {key: original.get(key, '') for key in MAPPING_KEYS}
        target_path = _clean(mapping['target_path'])

        if target_path not in target_paths:
            rejected.append({
                'index': index,
                'reason': 'Unknown target path',
                'proposal': original,
            })
            continue

        problems = _normalize_mapping(mapping, source_paths)
        accepted.append(mapping)

        if problems:
            issues.append({
                'index': index,
                'target_path': target_path,
                'issues': problems,
            })

    _flag_duplicate_targets(accepted)

    return accepted, rejected, issues
