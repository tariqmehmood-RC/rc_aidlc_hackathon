"""Tests for data/case_studies.json and scripts/import_case_studies.py."""
import collections
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "data" / "case_studies.json"
CSV = ROOT / "data" / "royal_cyber_case_studies.csv"

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


def test_seed_has_27_real_entries():
    assert len(load_seed()) == 27


def test_seed_has_at_least_5_entries_for_aws_and_servicenow():
    counts = collections.Counter(i["bu"] for i in load_seed())
    assert counts["AWS"] >= 5
    assert counts["ServiceNow"] >= 5


def test_seed_covers_all_four_bus():
    assert {i["bu"] for i in load_seed()} == set(importer.ALLOWED_BUS)


def test_every_url_is_on_royalcyber_com():
    for item in load_seed():
        assert item["url"].startswith(("https://royalcyber.com/", "https://www.royalcyber.com/")), item["url"]
        assert urlparse(item["url"]).hostname in {"royalcyber.com", "www.royalcyber.com"}


def test_no_placeholder_entries_remain():
    for item in load_seed():
        assert not item["id"].startswith("placeholder")
        assert "placeholder" not in item["title"].lower()
        assert "placeholder" not in item["summary"].lower()


def test_seed_json_is_in_sync_with_the_csv(tmp_path):
    """If someone edits the CSV, they must run the importer. The JSON must equal a fresh import."""
    out = tmp_path / "fresh.json"
    assert importer.main([str(CSV), "--output", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == load_seed()


def test_the_real_csv_has_the_expected_columns_and_rows():
    items, problems = importer.read_csv(CSV)
    assert problems == []
    assert len(items) == 27


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
    assert importer.validate_items([good_item(id="a"), good_item(id="b")]) != []  # same url twice


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


def test_import_ignores_blank_lines_before_the_header_and_between_rows(tmp_path):
    row2 = GOOD_ROW.replace("example", "other")
    code, out = run(tmp_path, "\n" + HEADER + "\n" + GOOD_ROW + "\n" + row2 + "\n")
    assert code == 0
    assert len(json.loads(out.read_text())) == 2


def test_import_handles_quoted_fields_with_commas(tmp_path):
    row = '"A title, with a comma",https://royalcyber.com/x,AWS,Retail,"Summary, with a comma.",a;b\n'
    code, out = run(tmp_path, HEADER + row)
    assert code == 0
    item = json.loads(out.read_text())[0]
    assert item["title"] == "A title, with a comma"
    assert item["summary"] == "Summary, with a comma."


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


def test_import_rejects_non_royalcyber_url(tmp_path):
    code, out = run(tmp_path, HEADER + GOOD_ROW.replace("https://www.royalcyber.com", "https://example.com"))
    assert code == 1 and not out.exists()


def test_import_rejects_duplicate_urls(tmp_path):
    code, out = run(tmp_path, HEADER + GOOD_ROW + GOOD_ROW)
    assert code == 1 and not out.exists()


def test_import_rejects_wrong_header(tmp_path):
    code, out = run(tmp_path, "title,url\nx,y\n")
    assert code == 1 and not out.exists()


def test_import_rejects_empty_file(tmp_path):
    code, out = run(tmp_path, "\n\n")
    assert code == 1 and not out.exists()


def test_import_rejects_wrong_column_count(tmp_path):
    code, out = run(tmp_path, HEADER + "only,two\n")
    assert code == 1 and not out.exists()
