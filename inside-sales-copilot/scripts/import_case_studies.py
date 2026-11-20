#!/usr/bin/env python3
"""Turn the CSV of Royal Cyber case studies into data/case_studies.json.

CSV columns (header row required): title,url,bu,industry,summary,tags
- `tags` are separated by semicolons, for example "ServiceNow;ITSM;automation".
- `summary` is 1 to 2 sentences in our own words. Do not paste page text.
- `url` is the public case study page on royalcyber.com.
- Blank lines are ignored.

Usage:
    python scripts/import_case_studies.py data/royal_cyber_case_studies.csv [--output data/case_studies.json]

Standard library only. Exits with a non-zero code and prints every problem if the
CSV or the resulting JSON fails validation. Nothing is written in that case.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ALLOWED_BUS = ("AWS", "ServiceNow", "Salesforce", "Data & AI")
REQUIRED_FIELDS = ("id", "title", "summary", "bu", "client_industry", "tags", "url")
CSV_COLUMNS = ("title", "url", "bu", "industry", "summary", "tags")
MAX_TITLE = 200
MAX_SUMMARY = 300
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "data" / "case_studies.json"


def make_id(url: str) -> str:
    """Stable id from the URL, so reordering the CSV does not change ids."""
    return "cs-" + hashlib.sha1(url.strip().encode("utf-8")).hexdigest()[:8]


def _valid_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (host == "royalcyber.com" or host.endswith(".royalcyber.com"))


def validate_items(items: object) -> list[str]:
    """Return a list of problems. An empty list means the data is valid."""
    problems: list[str] = []
    if not isinstance(items, list) or not items:
        return ["top level must be a non-empty list"]
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    for n, item in enumerate(items, 1):
        where = f"item {n}"
        if not isinstance(item, dict):
            problems.append(f"{where}: must be an object")
            continue
        missing = [f for f in REQUIRED_FIELDS if f not in item]
        extra = [k for k in item if k not in REQUIRED_FIELDS]
        if missing:
            problems.append(f"{where}: missing fields {missing}")
        if extra:
            problems.append(f"{where}: unexpected fields {extra}")
        if missing:
            continue
        where = f"item {n} ({item['id']})"
        bad_strings = [
            f for f in ("id", "title", "summary", "bu", "client_industry", "url")
            if not isinstance(item[f], str) or not item[f].strip()
        ]
        for f in bad_strings:
            problems.append(f"{where}: '{f}' must be a non-empty string")
        if bad_strings:
            continue
        if len(item["title"]) > MAX_TITLE:
            problems.append(f"{where}: title is longer than {MAX_TITLE} characters")
        if len(item["summary"]) > MAX_SUMMARY:
            problems.append(f"{where}: summary is longer than {MAX_SUMMARY} characters")
        if item["bu"] not in ALLOWED_BUS:
            problems.append(f"{where}: bu '{item['bu']}' is not one of {list(ALLOWED_BUS)}")
        tags = item["tags"]
        if not isinstance(tags, list) or not tags or not all(isinstance(t, str) and t.strip() for t in tags):
            problems.append(f"{where}: tags must be a non-empty list of non-empty strings")
        if not _valid_url(item["url"]):
            problems.append(f"{where}: url must be an https URL on royalcyber.com")
        if item["id"] in seen_ids:
            problems.append(f"{where}: duplicate id")
        seen_ids.add(item["id"])
        if item["url"] in seen_urls:
            problems.append(f"{where}: duplicate url")
        seen_urls.add(item["url"])
    return problems


def read_csv(path: Path) -> tuple[list[dict], list[str]]:
    """Read the CSV. Blank lines (before the header or between rows) are ignored."""
    problems: list[str] = []
    items: list[dict] = []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        header: list[str] | None = None
        for row in reader:
            if not any(cell.strip() for cell in row):
                continue  # blank line
            if header is None:
                header = [c.strip() for c in row]
                if header != list(CSV_COLUMNS):
                    return [], [f"CSV header must be exactly: {','.join(CSV_COLUMNS)}"]
                continue
            if len(row) != len(CSV_COLUMNS):
                problems.append(f"line {reader.line_num}: expected {len(CSV_COLUMNS)} columns, found {len(row)}")
                continue
            rec = dict(zip(CSV_COLUMNS, row))
            url = rec["url"].strip()
            items.append({
                "id": make_id(url),
                "title": rec["title"].strip(),
                "summary": rec["summary"].strip(),
                "bu": rec["bu"].strip(),
                "client_industry": rec["industry"].strip(),
                "tags": [t.strip() for t in rec["tags"].split(";") if t.strip()],
                "url": url,
            })
        if header is None:
            return [], ["CSV is empty"]
    return items, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    items, problems = read_csv(args.csv_path)
    if not problems:
        problems = validate_items(items)
    if problems:
        print(f"Not written. {len(problems)} problem(s):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(items)} case studies to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
