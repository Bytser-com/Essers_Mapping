"""Discover XML leaf fields, paths, occurrence counts and representative values.

Prototype assumption: local element names uniquely identify fields. XML namespaces
are stripped for matching; namespace collisions need a future enhancement.
"""
from collections import defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET


def _local(tag: str) -> str:
    return tag.rsplit('}', 1)[-1].split(':')[-1]


def parse_xml_directory(folder: str | Path) -> list[dict]:
    folder = Path(folder)
    xml_files = sorted(folder.rglob('*.xml')) if folder.is_dir() else []
    found = defaultdict(lambda: {'count': 0, 'files': set(), 'examples': []})

    for file in xml_files:
        try:
            root = ET.parse(file).getroot()
        except ET.ParseError as error:
            raise ValueError(f'Invalid XML file {file}: {error}') from error

        def record(path: str, kind: str, value: str):
            key = (path, kind)
            item = found[key]
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
