#!/usr/bin/env python3
"""Warm the research cache before the demo (research only, no brief).

    backend/.venv/bin/python scripts/warm_cache.py --table <ResearchCache table name>
    backend/.venv/bin/python scripts/warm_cache.py data/sample_invites/04-allstate.txt --table ... --refresh

For each invite: read the company with the parse prompt (1 Haiku call), then run research
(public pages plus 1 Haiku call) and store the result in the ResearchCache table, where it stays
for 7 days. On demo day the pipeline then skips research for these companies.

All Bedrock calls go through the shared client, so the 1 request per second limit applies.
Run this from one shell at a time. Region is us-east-1. No secrets are needed beyond the
normal AWS credentials of the person running it.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEMO_INVITES = ("data/sample_invites/04-allstate.txt", "data/sample_invites/01-delta-air-lines.txt")


def warm(invite_paths: Sequence[str | Path], bedrock: Any, research_service: Any, *,
         refresh: bool = False, out=sys.stdout) -> list[dict[str, Any]]:
    from backend.src.services import invite_parser
    from backend.src.services.research import NoPublicInfo, cache_key

    results: list[dict[str, Any]] = []
    for path in invite_paths:
        text = Path(path).read_text(encoding="utf-8")
        parsed = invite_parser.parse_invite(bedrock, text)
        name, domain = parsed["company"]["name"], parsed["company"]["domain"]
        if not invite_parser.names_a_company(parsed):
            print(f"{Path(path).name}: skipped, no company found in the invite", file=out)
            results.append({"invite": str(path), "status": "no_company"})
            continue
        key = cache_key(name, domain)
        if refresh:
            research_service.table.delete_item(Key={"companyDomain": key})
        started = time.monotonic()
        try:
            research, hit = research_service.get_research(name, domain)
        except NoPublicInfo:
            print(f"{Path(path).name}: {name or domain}: no public information found", file=out)
            results.append({"invite": str(path), "company": name, "status": "no_public_info"})
            continue
        seconds = round(time.monotonic() - started, 1)
        state = "already cached" if hit else f"researched in {seconds} s"
        print(f"{Path(path).name}: {name} ({key}) {state}: {len(research['facts'])} facts, "
              f"{len(research['news'])} news, tier {research['sizeTier']['tier']}", file=out)
        results.append({"invite": str(path), "company": name, "key": key, "status": "cached" if hit else "warmed",
                        "facts": len(research["facts"]), "seconds": seconds})
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Warm the research cache for the demo invites.")
    parser.add_argument("invites", nargs="*", default=list(DEMO_INVITES), help="invite files (default: the demo invites)")
    parser.add_argument("--table", default=os.environ.get("RESEARCH_CACHE_TABLE"),
                        help="ResearchCache table name (default: RESEARCH_CACHE_TABLE)")
    parser.add_argument("--refresh", action="store_true", help="research again even if a fresh entry exists")
    args = parser.parse_args(argv)
    if not args.table:
        parser.error("set --table or RESEARCH_CACHE_TABLE")

    import boto3

    from backend.local_run import _configure_env
    from backend.src.lib.bedrock_client import BedrockClient
    from backend.src.services.research import ResearchService
    from backend.src.services.research_provider import PublicWebProvider

    _configure_env(fake=False)  # model IDs and the research User-Agent from infra/cdk.json
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(args.table)
    bedrock = BedrockClient()
    results = warm([ROOT / p if not Path(p).is_absolute() else p for p in args.invites], bedrock,
                   ResearchService(bedrock, PublicWebProvider(), table), refresh=args.refresh)
    return 0 if all(r["status"] in ("warmed", "cached") for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
