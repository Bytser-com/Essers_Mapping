"""Security checks for XML input parsing, using synthetic test data."""

import pytest
from defusedxml.common import DefusedXmlException

from scripts.xml_parser import leaf_values, parse_xml_files


def test_xml_field_inventory_with_normal_document(tmp_path):
    document = tmp_path / 'source.xml'
    document.write_text('<Root><Item code="A"><Name>Example</Name></Item></Root>', encoding='utf-8')

    fields = parse_xml_files([document])
    assert {field['path'] for field in fields} == {'/Root/Item/@code', '/Root/Item/Name'}
    assert leaf_values(document)['/Root/Item/Name'] == ['Example']


def test_xml_entity_declarations_are_rejected(tmp_path):
    document = tmp_path / 'unsafe.xml'
    document.write_text(
        '<!DOCTYPE Root [<!ENTITY injected "unexpected">]><Root>&injected;</Root>',
        encoding='utf-8',
    )

    with pytest.raises(ValueError, match='Invalid XML file'):
        parse_xml_files([document])
    with pytest.raises(DefusedXmlException):
        leaf_values(document)
