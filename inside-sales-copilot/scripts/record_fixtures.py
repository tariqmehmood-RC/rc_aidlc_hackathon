#!/usr/bin/env python3
"""Record live research results for the sample invite companies, for tests and the local runner.

Run once with network access:  backend/.venv/bin/python scripts/record_fixtures.py [domain ...]
With no arguments all sample companies are recorded; pass domains to re-record only those.
Writes backend/tests/fixtures/research/<domain>.json. Each document is trimmed to 2,000
characters. Only public pages are read, with an honest User-Agent, and a blocked site is
simply recorded as failed.
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.src.services.research_provider import PublicWebProvider, RawResearch  # noqa: E402

OUT = ROOT / "backend" / "tests" / "fixtures" / "research"
SAMPLES = ROOT / "data" / "sample_invites" / "expected.json"
MAX_CHARS = 2000


def trimmed(raw: RawResearch) -> RawResearch:
    docs = [replace(d, text=d.text[:MAX_CHARS]) for d in raw.documents]
    return RawResearch(documents=docs, news=raw.news, sources=raw.sources, match_confidence=raw.match_confidence)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    expected = json.loads(SAMPLES.read_text(encoding="utf-8"))
    provider = PublicWebProvider()
    only = set(sys.argv[1:])
    for invite, data in expected.items():
        name, domain = data["company"]["name"], data["company"]["domain"]
        if only and domain not in only:
            continue
        time.sleep(5)  # Wikipedia rate-limits quick bursts
        raw = trimmed(provider.research(name, domain))
        path = OUT / f"{domain}.json"
        path.write_text(json.dumps(raw.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        ok = [s for s in raw.sources if s.status == "ok"]
        failed = [s.url for s in raw.sources if s.status == "failed"]
        print(f"{invite}: {len(raw.documents)} documents, {len(raw.news)} news, "
              f"{len(ok)} sources ok, confidence={raw.match_confidence}")
        for url in failed:
            print(f"    failed: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
