"""Unit tests for deterministic historical XML reference-evidence matching.

These tests use synthetic XML only: no Gemini API key, network, SFTP, or
real customer data is required.
"""

import xml.etree.ElementTree as ET

import pytest

from scripts.historical_evidence import (
    _informative,
    _local,
    _path_similarity,
    _values_by_path,
    extract_reference_evidence,
)


def make_pair(original: str, converted: str, *, company: str = "example",
              pair_id: str = "001") -> dict:
    """Supply the exact data shape expected by extract_reference_evidence."""
    return {
        "company": company,
        "pair_id": pair_id,
        "original_filename": f"{pair_id}_Original.xml",
        "converted_filename": f"{pair_id}_Converted.xml",
        "original_xml": original,
        "converted_xml": converted,
    }


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("Value", "Value"),
        ("ns:Value", "Value"),
        ("{urn:test}Value", "Value"),
    ],
)
def test_local_strips_namespace_formats(tag, expected):
    assert _local(tag) == expected


def test_values_by_path_trims_text_and_attributes_and_merges_repetitions():
    xml = (
        '<Root status=" ready ">'
        '<Item code=" A123 "><City> Gent </City><Empty> </Empty></Item>'
        '<Item code="B456"><City> Bonn </City></Item>'
        '</Root>'
    )

    assert _values_by_path(xml) == {
        "/Root/@status": {"ready"},
        "/Root/Item/@code": {"A123", "B456"},
        "/Root/Item/City": {"Gent", "Bonn"},
    }


def test_values_by_path_skips_empty_attributes():
    xml = '<Root empty=" " valid=" A123 "><Value>Gent</Value></Root>'
    assert _values_by_path(xml) == {
        "/Root/@valid": {"A123"},
        "/Root/Value": {"Gent"},
    }


def test_values_by_path_handles_namespaced_elements_and_attributes():
    xml = (
        '<t:Root xmlns:t="urn:test">'
        '<t:Address t:code="A-001"><t:City> Gent </t:City></t:Address>'
        '</t:Root>'
    )
    assert _values_by_path(xml) == {
        "/Root/Address/@code": {"A-001"},
        "/Root/Address/City": {"Gent"},
    }


def test_values_by_path_does_not_treat_parent_mixed_text_as_leaf_value():
    assert _values_by_path("<Root>ignored<Child>found</Child></Root>") == {
        "/Root/Child": {"found"},
    }


def test_values_by_path_rejects_invalid_xml():
    with pytest.raises(ET.ParseError):
        _values_by_path("<Root><Unclosed></Root>")


@pytest.mark.parametrize(
    "value",
    [
        "", "a", "123", "true", "FALSE", "None", "NULL", "YES", "no",
        "0000", "777777", "a" * 151,
    ],
)
def test_informative_filters_trivial_or_excessively_long_values(value):
    assert _informative(value) is False


@pytest.mark.parametrize("value", ["Gent", "A123", "0000000168", "a" * 150])
def test_informative_accepts_distinguishing_values(value):
    assert _informative(value) is True


def test_path_similarity_prefers_identical_names_with_underscore_ignored():
    assert _path_similarity("/Legacy/CITY_NAME", "/New/cityname") == 1.0


def test_path_similarity_rewards_suffixes():
    assert _path_similarity("/Legacy/DELIVERY_NUMBER", "/New/NUMBER") == 0.85


def test_path_similarity_handles_unrelated_names_without_crashing():
    score = _path_similarity("/Original/City", "/Converted/Country")
    assert 0.0 <= score < 0.85


def test_extract_returns_empty_if_max_per_target_is_not_positive():
    # The early return should not even try to parse invalid XML.
    pair = make_pair("invalid", "invalid")
    assert extract_reference_evidence([pair], ["/New/City"], max_per_target=0) == []
    assert extract_reference_evidence([pair], ["/New/City"], max_per_target=-1) == []


def test_extract_returns_empty_with_no_pairs_or_no_targets():
    pair = make_pair("<Old><City>Gent</City></Old>", "<New><City>Gent</City></New>")
    assert extract_reference_evidence([], ["/New/City"]) == []
    assert extract_reference_evidence([pair], []) == []


def test_extract_records_verified_matching_value_and_metadata():
    pair = make_pair(
        "<Old><City>Gent</City></Old>",
        "<New><CITY>Gent</CITY></New>",
        company="christeyns",
        pair_id="002",
    )
    rows = extract_reference_evidence([pair], ["/New/CITY"])

    assert len(rows) == 1
    row = rows[0]
    assert row["Reference pair"] == "christeyns / 002"
    assert row["Historical Original"] == "002_Original.xml"
    assert row["Historical Converted"] == "002_Converted.xml"
    assert row["Evidence type"] == "Exact value match (XML-checked)"
    assert row["Historical source path"] == "/Old/City"
    assert row["Historical target path"] == "/New/CITY"
    assert row["Example value"] == "Gent"
    assert row["Usefulness"] == "Candidate; expert review"
    assert "does not prove" in row["Evidence note"]


def test_extract_requires_same_nontrivial_literal_in_both_xml_files():
    pair = make_pair("<Old><City>Gent</City></Old>", "<New><City>Bonn</City></New>")
    assert extract_reference_evidence([pair], ["/New/City"]) == []


def test_extract_matches_are_case_sensitive_not_approximate():
    pair = make_pair("<Old><City>Gent</City></Old>", "<New><City>gent</City></New>")
    assert extract_reference_evidence([pair], ["/New/City"]) == []


def test_extract_does_not_report_short_flag_values():
    pair = make_pair("<Old><Flag>1</Flag></Old>", "<New><Flag>1</Flag></New>")
    assert extract_reference_evidence([pair], ["/New/Flag"]) == []


def test_extract_does_not_report_trivial_value_from_original_or_target():
    pair = make_pair(
        "<Old><A>0000</A><B>Gent</B></Old>",
        "<New><A>0000</A><B>TRUE</B></New>",
    )
    assert extract_reference_evidence([pair], ["/New/A", "/New/B"]) == []


def test_extract_reports_ambiguity_and_prefers_similar_field_name():
    pair = make_pair(
        "<Old><County>Gent</County><City>Gent</City></Old>",
        "<New><CITY>Gent</CITY></New>",
    )
    rows = extract_reference_evidence([pair], ["/New/CITY"])

    assert len(rows) == 1
    assert rows[0]["Historical source path"] == "/Old/City"
    assert rows[0]["Usefulness"] == "Ambiguous; expert review"
    assert "2 original XML paths" in rows[0]["Evidence note"]


def test_extract_supports_attribute_values():
    pair = make_pair(
        '<Old externalId="123456"/>',
        '<New externalId="123456"/>',
    )
    rows = extract_reference_evidence([pair], ["/New/@externalId"])
    assert len(rows) == 1
    assert rows[0]["Historical source path"] == "/Old/@externalId"
    assert rows[0]["Example value"] == "123456"


def test_extract_one_entry_per_pair_and_target_even_for_multiple_values():
    pair = make_pair(
        "<Old><City>Gent</City><City>Bonn</City></Old>",
        "<New><CITY>Gent</CITY><CITY>Bonn</CITY></New>",
    )
    rows = extract_reference_evidence([pair], ["/New/CITY"])
    assert len(rows) == 1
    assert rows[0]["Example value"] in {"Gent", "Bonn"}


def test_extract_limits_pairs_per_target_and_prefers_stronger_field_name():
    pairs = [
        make_pair(
            "<Old><Unrelated>Gent</Unrelated></Old>",
            "<New><CITY>Gent</CITY></New>",
            pair_id="less_similar",
        ),
        make_pair(
            "<Old><CITY>Gent</CITY></Old>",
            "<New><CITY>Gent</CITY></New>",
            pair_id="exact",
        ),
        make_pair(
            "<Old><CITY_NAME>Gent</CITY_NAME></Old>",
            "<New><CITY>Gent</CITY></New>",
            pair_id="suffix",
        ),
    ]
    rows = extract_reference_evidence(pairs, ["/New/CITY"], max_per_target=2)
    assert len(rows) == 2
    assert {r["Reference pair"] for r in rows} == {"example / exact", "example / suffix"}
    assert rows[0]["Reference pair"] == "example / exact"


def test_extract_preserves_target_order_and_deduplicates_requested_paths():
    pair = make_pair(
        "<Old><City>Gent</City><Zip>9000</Zip></Old>",
        "<New><CITY>Gent</CITY><ZIP>9000</ZIP></New>",
    )
    rows = extract_reference_evidence(
        [pair], ["/New/ZIP", "/New/CITY", "/New/ZIP"], max_per_target=2
    )
    assert [row["Historical target path"] for row in rows] == [
        "/New/ZIP", "/New/CITY"
    ]


def test_extract_does_not_return_values_for_paths_outside_selected_targets():
    pair = make_pair(
        "<Old><City>Gent</City><Zip>9000</Zip></Old>",
        "<New><CITY>Gent</CITY><ZIP>9000</ZIP></New>",
    )
    rows = extract_reference_evidence([pair], ["/New/CITY"])
    assert [r["Historical target path"] for r in rows] == ["/New/CITY"]
