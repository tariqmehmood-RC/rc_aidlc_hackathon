#!/usr/bin/env python3
"""Create the frontend's mock API data from one real local run (task 4.1).

    backend/.venv/bin/python scripts/make_mock_fixture.py [--fake-bedrock]

Runs the Allstate sample invite through the local runner (live research, real Bedrock unless
--fake-bedrock) and writes frontend/src/mocks/fixtures/allstate.json in the shape the API
returns (design 6, brief view). Attendees are synthetic. No secrets are written.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import local_run  # noqa: E402

VIEW_KEYS = ("parsedInvite", "confirmedInvite", "research", "caseStudyMatches", "content", "rulesApplied")
OUT = ROOT / "frontend" / "src" / "mocks" / "fixtures" / "allstate.json"


def main() -> int:
    fake = "--fake-bedrock" in sys.argv
    invite = ROOT / "data" / "sample_invites" / "04-allstate.txt"
    result = local_run.run(str(invite), "ServiceNow", fake=fake, fixtures=fake, out=io.StringIO(), brief_model="haiku")
    if result.get("status") != "ready":
        print("run failed:", result.get("error"), file=sys.stderr)
        return 1
    brief = result["brief"]
    fixture = {
        "inviteText": invite.read_text(encoding="utf-8"),
        "brief": {k: brief[k] for k in VIEW_KEYS if k in brief},
        "generated": {"briefModel": result["briefModel"], "totalSeconds": result["timing"]["totalSeconds"],
                      "steps": result["steps"]},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({result['timing']['totalSeconds']} s, "
          f"{len(brief['content']['caseStudies'])} case studies)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
