"""Discover source paths, match historical XML pairs, and select complete XML examples.

Python does not decide any business mappings or rewrite the XML sent to Gemini.
"""
from collections import defaultdict
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def _local(tag: str) -> str:
    return tag.rsplit('}', 1)[-1].split(':')[-1]


def parse_xml_files(xml_files: list[Path]) -> list[dict]:
    """Return the original, full field inventory for exactly the specified XML files."""
    found = defaultdict(lambda: {'count': 0, 'files': set(), 'examples': []})

    for file in sorted(Path(p) for p in xml_files):
        try:
            root = ET.parse(file).getroot()
        except ET.ParseError as error:
            raise ValueError(f'Invalid XML file {file}: {error}') from error

        def record(path: str, kind: str, value: str):
            item = found[(path, kind)]
            item['count'] += 1
            item['files'].add(file.name)
            if value and value not in item['examples'] and len(item['examples']) < 3:
                item['examples'].append(value[:100])

        def visit(node, parent_path: str):
            path = f'{parent_path}/{_local(node.tag)}'
            children = list(node)
            if not children:
                record(path, 'element', (node.text or '').strip())
            for key, value in node.attrib.items():
                record(f'{path}/@{_local(key)}', 'attribute', str(value).strip())
            for child in children:
                visit(child, path)

        visit(root, '')

    return [
        {
            'path': path,
            'field': path.rsplit('/', 1)[-1],
            'kind': kind,
            'count': info['count'],
            'files': sorted(info['files']),
            'examples': info['examples'],
        }
        for (path, kind), info in sorted(found.items())
    ]


PAIR_PATTERN = re.compile(r'^(?P<stem>.+)_(?P<role>original|converted)\.xml$', re.I)


def discover_historical_pairs(historical_dir: str | Path) -> list[dict]:
    """Discover matched pairs, fail on incomplete or duplicate pairs.

    Handles Original/Converted in the same folder OR in nested original/converted
    subfolders, as in the Hempel ZIP. Dataset folders stay separate, preventing
    name collisions between Christeyns's small and large collections.
    """
    historical_dir = Path(historical_dir)
    if not historical_dir.is_dir():
        raise FileNotFoundError(f'Missing historical folder: {historical_dir}')

    result = []
    companies = sorted(path for path in historical_dir.iterdir() if path.is_dir())
    if not companies:
        raise ValueError(f'No company folders in {historical_dir}')

    for company_dir in companies:
        grouped = {}
        for file in sorted(company_dir.rglob('*.xml')):
            match = PAIR_PATTERN.fullmatch(file.name)
            if not match:
                raise ValueError(f'Cannot classify historical XML filename: {file}')
            stem = match.group('stem')
            role = match.group('role').lower()
            record = grouped.setdefault(stem.casefold(), {'stem': stem})
            if role in record:
                raise ValueError(f'Duplicate {role} for {company_dir.name}/{stem}: {file}')
            record[role] = file

        if not grouped:
            raise ValueError(f'No XML pairs found in {company_dir}')
        for record in grouped.values():
            if 'original' not in record or 'converted' not in record:
                raise ValueError(f'Incomplete historical pair: {company_dir.name}/{record["stem"]}')
            result.append({
                'company': company_dir.name,
                'pair_id': record['stem'],
                'original_file': record['original'],
                'converted_file': record['converted'],
            })

    return sorted(result, key=lambda x: (x['company'], x['pair_id']))


def read_raw_xml(file: str | Path) -> str:
    """Read the original XML text without translating/rearranging XML tags.

    Honors the declared XML encoding; UTF-8 (with optional BOM) is the fallback.
    Raises on undecodable input rather than silently dropping characters.
    """
    data = Path(file).read_bytes()
    declaration = re.search(br'<\?xml[^>]*encoding=[\'\"]([^\'\"]+)', data[:256], re.I)
    encoding = declaration.group(1).decode('ascii') if declaration else 'utf-8-sig'
    return data.decode(encoding)


def leaf_values(xml_file: str | Path) -> dict[str, list[str]]:
    """Collect values at all element/attribute paths, preserving repetitions.

    Used to pick representative raw XML documents by structural diversity.
    """
    root = ET.parse(xml_file).getroot()
    result = defaultdict(list)

    def visit(node, parent):
        path = parent + '/' + _local(node.tag)
        children = list(node)
        if not children:
            result[path].append((node.text or '').strip())
        for key, value in node.attrib.items():
            result[path + '/@' + _local(key)].append(str(value).strip())
        for child in children:
            visit(child, path)

    visit(root, '')
    return dict(result)


def select_raw_examples(xml_files: list[Path], sample_count: int, max_chars: int = 200000) -> list[dict]:
    """Select structurally varied COMPLETE raw documents; never truncate XML.

    Selection uses structural coverage alone, not semantic mappings. Files outside
    the sample remain represented in the full source-field inventory.
    """
    if sample_count < 1 or max_chars < 1:
        raise ValueError('sample_count and max_chars must be positive')
    profiles = []
    for file in sorted(map(Path, xml_files)):
        content = read_raw_xml(file)
        # Count occurrence cardinality as well as unique paths, to reward examples
        # with realistic multi-item/partner structures.
        counts = {p: len(v) for p, v in leaf_values(file).items()}
        structural = {(p, min(4, n)) for p, n in counts.items()}
        profiles.append((file, content, structural))

    chosen, used, covered = [], set(), set()
    while len(chosen) < min(sample_count, len(profiles)):
        eligible = []
        for file, content, structural in profiles:
            if file in used or sum(len(d['xml']) for d in chosen) + len(content) > max_chars:
                continue
            new_paths = len(structural - covered)
            # Prefer novel structure; cost only breaks ties and prevents huge
            # files from crowding out all other examples.
            score = (new_paths, len(structural), -len(content), file.name)
            eligible.append((score, file, content, structural))
        if not eligible:
            break
        _, file, content, structural = max(eligible, key=lambda x: x[0])
        chosen.append({'filename': file.name, 'xml': content, 'path': file})
        used.add(file)
        covered.update(structural)
    if not chosen:
        raise ValueError('No complete XML document fits the configured raw XML budget')
    return chosen


def select_historical_examples(pairs: list[dict], per_company: int = 1) -> list[dict]:
    """Choose real matched raw XML pairs across companies (no business logic)."""
    if per_company < 0:
        raise ValueError('per_company must be >=0')
    if per_company == 0:
        return []
    by_company = defaultdict(list)
    for pair in pairs:
        by_company[pair['company']].append(pair)
    selected = []
    for company, group in sorted(by_company.items()):
        # Sample structurally informative originals first, with varied cardinality.
        # Keep selected original/converted pairing intact.
        original_files = [pair['original_file'] for pair in group]
        # Budget large enough that selecting examples is determined by diversity,
        # not request size. The caller must check the eventual total prompt size.
        docs = select_raw_examples(original_files, per_company, max_chars=100000000)
        pair_by_file = {pair['original_file']: pair for pair in group}
        for doc in docs:
            pair = pair_by_file[doc['path']]
            selected.append({
                'company': company, 'pair_id': pair['pair_id'],
                'original_filename': pair['original_file'].name,
                'converted_filename': pair['converted_file'].name,
                'original_xml': doc['xml'],
                'converted_xml': read_raw_xml(pair['converted_file']),
            })
    return selected
