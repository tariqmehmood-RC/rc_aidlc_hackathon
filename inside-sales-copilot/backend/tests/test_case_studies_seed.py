"""Tests for data/case_studies.json and scripts/import_case_studies.py."""
import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "data" / "case_studies.json"

_spec = importlib.util.spec_from_file_location("import_case_studies", ROOT / "scripts" / "import_case_studies.py")
importer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(importer)

HEADER = "title,url,bu,industry,summary,tags\n"
GOOD_ROW = 'Example title,https://www.royalcyber.com/case-studies/example/,AWS,Retail,A short summary in our own words.,aws;retail\n'


def load_seed():
    return json.loads(SEED.read_text(encoding="utf-8"))


# --- the seed file -------------------------------------------------------------

def test_seed_file_is_valid():
    assert importer.validate_items(load_seed()) == []


def test_seed_has_all_four_bus():
    assert {i["bu"] for i in load_seed()} == set(importer.ALLOWED_BUS)


def test_seed_has_15_placeholders_until_replaced():
    items = load_seed()
    placeholders = importer.find_placeholders(items)
    if placeholders:  # once the real seed replaces the placeholders this check no longer applies
        assert len(placeholders) == 15
        assert all(i["title"].startswith("[PLACEHOLDER]") for i in items if i["id"] in placeholders)


def test_find_placeholders_detects_by_id_and_title():
    items = [
        {"id": "placeholder-01", "title": "x"},
        {"id": "cs-1", "title": "[PLACEHOLDER] y"},
        {"id": "cs-2", "title": "Real"},
    ]
    assert importer.find_placeholders(items) == ["placeholder-01", "cs-1"]


@pytest.mark.skipif(os.environ.get("DEMO_MODE") != "true", reason="only enforced when DEMO_MODE=true")
def test_no_placeholders_in_demo_mode():
    left = importer.find_placeholders(load_seed())
    assert left == [], f"DEMO_MODE=true but {len(left)} placeholder case studies remain: {left}"


# --- the validator -------------------------------------------------------------

def good_item(**changes):
    item = {
        "id": "cs-1", "title": "T", "summary": "S", "bu": "AWS", "client_industry": "Retail",
        "tags": ["a"], "url": "https://www.royalcyber.com/case-studies/x/",
    }
    item.update(changes)
    return item


def test_validator_accepts_good_item():
    assert importer.validate_items([good_item()]) == []


@pytest.mark.parametrize("changes", [
    {"bu": "Oracle"},
    {"url": "http://www.royalcyber.com/x"},
    {"url": "https://example.com/x"},
    {"url": "https://royalcyber.com.evil.com/x"},
    {"tags": []},
    {"title": ""},
    {"summary": "x" * 301},
    {"title": "x" * 201},
])
def test_validator_rejects_bad_item(changes):
    assert importer.validate_items([good_item(**changes)]) != []


def test_validator_rejects_missing_and_extra_fields():
    item = good_item()
    del item["summary"]
    assert importer.validate_items([item]) != []
    assert importer.validate_items([good_item(extra="x")]) != []


def test_validator_rejects_duplicates_and_empty_list():
    assert importer.validate_items([]) != []
    assert importer.validate_items([good_item(), good_item()]) != []
    assert importer.validate_items([good_item(id="a"), good_item(id="b")]) != []  # same real url twice


# --- the CSV importer ----------------------------------------------------------

def run(tmp_path, csv_text):
    src = tmp_path / "in.csv"
    out = tmp_path / "out.json"
    src.write_text(csv_text, encoding="utf-8")
    code = importer.main([str(src), "--output", str(out)])
    return code, out


def test_import_good_csv(tmp_path):
    code, out = run(tmp_path, HEADER + GOOD_ROW)
    assert code == 0
    items = json.loads(out.read_text())
    assert len(items) == 1
    assert items[0]["client_industry"] == "Retail"
    assert items[0]["tags"] == ["aws", "retail"]
    assert items[0]["id"] == importer.make_id("https://www.royalcyber.com/case-studies/example/")
    assert importer.validate_items(items) == []


def test_import_is_stable_when_rows_reorder(tmp_path):
    row2 = GOOD_ROW.replace("example", "other")
    _, out1 = run(tmp_path, HEADER + GOOD_ROW + row2)
    ids1 = {i["url"]: i["id"] for i in json.loads(out1.read_text())}
    _, out2 = run(tmp_path, HEADER + row2 + GOOD_ROW)
    ids2 = {i["url"]: i["id"] for i in json.loads(out2.read_text())}
    assert ids1 == ids2


def test_import_rejects_bad_bu_and_writes_nothing(tmp_path):
    code, out = run(tmp_path, HEADER + GOOD_ROW.replace(",AWS,", ",Oracle,"))
    assert code == 1
    assert not out.exists()


def test_import_rejects_wrong_header(tmp_path):
    code, out = run(tmp_path, "title,url\nx,y\n")
    assert code == 1 and not out.exists()


def test_import_rejects_wrong_column_count(tmp_path):
    code, out = run(tmp_path, HEADER + "only,two\n")
    assert code == 1 and not out.exists()


def test_import_rejects_placeholder_rows(tmp_path):
    code, out = run(tmp_path, HEADER + GOOD_ROW.replace("Example title", "[PLACEHOLDER] x"))
    assert code == 1 and not out.exists()
