"""Structural checks only. These do not verify business semantics."""
from collections import Counter

RULE_TYPES = {
    'DIRECT', 'FIXED', 'DEFAULT_IF_EMPTY', 'DERIVED', 'CONDITIONAL',
    'LOOKUP', 'LOOP', 'FORMAT_DATE', 'REVIEW_REQUIRED',
}


def validate_mappings(proposals: list, source_fields: list, target_fields: list):
    source_paths = {item['path'] for item in source_fields}
    target_paths = {item['path'] for item in target_fields}
    accepted, rejected, issues = [], [], []

    for index, original in enumerate(proposals, start=1):
        if not isinstance(original, dict):
            rejected.append({'index': index, 'reason': 'Not an object', 'proposal': original})
            continue

        mapping = {key: original.get(key, '') for key in (
            'source_path', 'target_path', 'rule_type', 'confidence',
            'requires_review', 'review_priority', 'reason', 'evidence',
            'fixed_value', 'transformation', 'condition', 'lookup', 'loop',
            'review_question', 'risk_category',
        )}
        target_path = str(mapping['target_path']).strip()
        source_path = str(mapping['source_path']).strip()
        rule = str(mapping['rule_type']).strip().upper()
        problem = []

        if target_path not in target_paths:
            rejected.append({'index': index, 'reason': 'Unknown target path', 'proposal': original})
            continue
        if rule not in RULE_TYPES:
            problem.append(f'Unknown rule type: {rule}')
            rule = 'REVIEW_REQUIRED'
        if source_path and source_path not in source_paths:
            problem.append(f'Source path not found: {source_path}')
        if not source_path and rule not in {'FIXED', 'REVIEW_REQUIRED'}:
            problem.append('Non-FIXED proposal has no source path')
        if rule == 'FIXED' and not str(mapping['fixed_value']).strip():
            problem.append('FIXED mapping has no fixed value')
        try:
            confidence = int(float(mapping['confidence']))
        except (ValueError, TypeError):
            confidence = 0
            problem.append('Invalid confidence value')
        if not 0 <= confidence <= 100:
            confidence = max(0, min(100, confidence))
            problem.append('Confidence outside 0–100')

        mapping['target_path'] = target_path
        mapping['source_path'] = source_path
        mapping['rule_type'] = rule
        mapping['confidence'] = confidence
        mapping['requires_review'] = (
            mapping['requires_review'] is True
            or str(mapping['requires_review']).lower() in {'true', 'yes', '1'}
            or bool(problem)
        )
        if mapping['requires_review'] and str(mapping['review_priority']).lower() not in ('high', 'critical'):
            mapping['review_priority'] = 'High' if problem else (mapping['review_priority'] or 'Medium')
        mapping['validation_issues'] = problem
        accepted.append(mapping)
        if problem:
            issues.append({'index': index, 'target_path': target_path, 'issues': problem})

    # Duplicate proposals are not necessarily wrong when conditions or loops differ.
    counts = Counter(m['target_path'] for m in accepted)
    for mapping in accepted:
        if counts[mapping['target_path']] > 1:
            message = 'Multiple proposals for same target; verify conditions/priority'
            mapping['validation_issues'].append(message)
            mapping['requires_review'] = True
    return accepted, rejected, issues
