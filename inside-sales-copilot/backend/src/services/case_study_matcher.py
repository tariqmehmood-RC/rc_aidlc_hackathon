"""Case study matching (requirements R5, design 8.5 and prompt P3).

The BU is an argument. The caller passes the BU stored on the brief, which was taken from the
user's verified token, so nothing a client sends can change which library is searched.
Steps: filter to the BU, rank by industry and tag overlap, let Haiku score the top 8, keep
scores of 60 or more, return at most 3. Titles and URLs always come from the JSON file.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Sequence

from ..lib import constants as c
from ..lib.models import CaseStudy

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "case_studies.json"

MSG_NO_BU = "No case studies are available because your account has no business unit."
MSG_NONE = "No strong match in your BU's library"
MSG_FEWER = "No strong match for {need}"
FALLBACK_NEED = "the remaining needs"
MAX_NEED_WORDS = 6

P3_SYSTEM = (
    "Score how relevant each case study is to this prospect from 0 to 100, using only the "
    "stated needs, the company facts, and the case study record. The stated needs come from the "
    "meeting invite and say what the prospect wants to discuss: weigh them above the researched "
    "pain points, which are only guesses. Give a one-sentence reason that names the specific "
    "need or fact and the specific case study detail it connects. Do not claim anything about "
    "the case study that is not in its record. Return a score for every case study you are "
    "given. Also give uncoveredNeed: a short label of at most 6 words (for example 'vendor risk "
    "assessment') for the most important need that none of the high-scoring case studies cover, "
    "or null."
)
P3_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["scores", "uncoveredNeed"],
    "additionalProperties": False,
    "properties": {
        "scores": {
            "type": "array", "maxItems": c.CASE_STUDY_CANDIDATES,
            "items": {
                "type": "object", "required": ["caseStudyId", "score", "reason"], "additionalProperties": False,
                "properties": {
                    "caseStudyId": {"type": "string"},
                    "score": {"type": "integer", "minimum": 0, "maximum": 100},
                    "reason": {"type": "string", "maxLength": 300},
                },
            },
        },
        "uncoveredNeed": {"type": ["string", "null"], "maxLength": 80},
    },
}

_WORD_RE = re.compile(r"[a-z0-9]{3,}")
_STOP = {"and", "the", "for", "with", "from", "that", "this", "are", "was", "has", "have", "its",
         "into", "their", "our", "not", "all", "can", "will", "about", "more", "than", "using"}
_CLOSE_RE = re.compile(r"</\s*(case_study|company_facts|stated_needs)\s*>", re.IGNORECASE)


def load_case_studies(path: Path | str | None = None) -> list[CaseStudy]:
    raw = json.loads(Path(path or DEFAULT_PATH).read_text(encoding="utf-8"))
    return [CaseStudy.from_dict(item) for item in raw]


def _words(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOP}


def _research_corpus(research: dict[str, Any]) -> tuple[set[str], set[str]]:
    """(words about the industry, words about everything else)."""
    industry = (research.get("industry") or {}).get("value") or ""
    other = " ".join(
        [f["text"] for f in research.get("facts", [])]
        + [p["hypothesis"] for p in research.get("painPoints", [])]
    )
    return _words(industry), _words(other) | _words(industry)


def prefilter(bu: str, research: dict[str, Any], studies: Sequence[CaseStudy],
              limit: int = c.CASE_STUDY_CANDIDATES, stated_needs: str | None = None) -> list[CaseStudy]:
    """Case studies of this BU only, best overlap first, ties in file order. Words from the
    invite's stated needs count more than words from research."""
    own = [s for s in studies if s.bu == bu]
    industry_words, all_words = _research_corpus(research)
    need_words = _words(stated_needs or "")

    def score(s: CaseStudy) -> int:
        points = 3 if _words(s.client_industry) & industry_words else 0
        for tag in s.tags:
            tag_words = _words(tag)
            if tag_words & need_words:
                points += 4
            elif tag_words & all_words:
                points += 2
        title_words = _words(s.title)
        points += 2 * len(title_words & need_words) + len(title_words & all_words)
        return points

    ranked = sorted(enumerate(own), key=lambda pair: (-score(pair[1]), pair[0]))
    return [s for _, s in ranked[:limit]]


def short_need(text: str | None) -> str:
    """At most 6 words, no trailing punctuation. Falls back when empty."""
    words = re.sub(r"[\s]+", " ", (text or "")).strip().strip(".!?;:,").split(" ")
    words = [w for w in words if w]
    return " ".join(words[:MAX_NEED_WORDS]).strip(".,;:") or FALLBACK_NEED


def _prompt(research: dict[str, Any], candidates: Sequence[CaseStudy], stated_needs: str | None = None) -> str:
    esc = lambda t: _CLOSE_RE.sub("&lt;/\\1&gt;", t)  # noqa: E731
    industry = (research.get("industry") or {}).get("value") or "unknown"
    tier = research.get("sizeTier", {}).get("tier", "Unknown")
    lines = ["<stated_needs>", esc(stated_needs.strip()) if stated_needs and stated_needs.strip() else "none given",
             "</stated_needs>", "<company_facts>", f"industry: {esc(industry)}", f"size tier: {tier}", "pain points:"]
    lines += [f"- {p['id']}: {esc(p['hypothesis'])}" for p in research.get("painPoints", [])] or ["- none known"]
    lines.append("</company_facts>")
    for s in candidates:
        lines.append(
            f'<case_study id="{html.escape(s.id, quote=True)}">title: {esc(s.title)}\n'
            f"summary: {esc(s.summary)}\nindustry: {esc(s.client_industry)}\n"
            f"tags: {esc(', '.join(s.tags))}</case_study>"
        )
    return "\n".join(lines)


def stated_needs_from_invite(invite: dict[str, Any] | None) -> str | None:
    """The invite's subject and notes: what the prospect said they want to discuss."""
    if not invite:
        return None
    parts = [invite.get("subject") or "", invite.get("notes") or ""]
    text = "\n".join(p.strip() for p in parts if p and p.strip())
    return text[:1500] or None


def match_case_studies(bedrock, bu: str | None, research: dict[str, Any],
                       studies: Sequence[CaseStudy], stated_needs: str | None = None) -> dict[str, Any]:
    """Return a `case_study_matches` object (design 5.6)."""
    if not bu or bu not in c.BUSINESS_UNITS:
        return {"matches": [], "message": MSG_NO_BU}
    candidates = prefilter(bu, research, studies, stated_needs=stated_needs)
    if not candidates:
        return {"matches": [], "message": MSG_NONE}

    out = bedrock.converse_json(
        model=c.MODEL_HAIKU,
        system=P3_SYSTEM,
        user=_prompt(research, candidates, stated_needs),
        max_tokens=c.MAX_TOKENS["score"],
        schema=P3_SCHEMA,
    )

    by_id = {s.id: s for s in candidates}
    order = {s.id: i for i, s in enumerate(candidates)}
    scored: dict[str, dict[str, Any]] = {}
    for item in out["scores"]:
        cid = item["caseStudyId"]
        if cid not in by_id or cid in scored:
            continue  # an id we did not send, or a repeat
        scored[cid] = item

    qualifying = [
        (cid, item) for cid, item in scored.items()
        if item["score"] >= c.CASE_STUDY_MIN_SCORE and item["reason"].strip()
    ]
    qualifying.sort(key=lambda pair: (-pair[1]["score"], order[pair[0]]))
    top = qualifying[: c.MAX_CASE_STUDIES]

    matches = [
        {"caseStudyId": cid, "title": by_id[cid].title, "url": by_id[cid].url,
         "score": item["score"], "reason": item["reason"].strip()}
        for cid, item in top
    ]
    if not matches:
        message: str | None = MSG_NONE
    elif len(matches) < c.MAX_CASE_STUDIES:
        message = MSG_FEWER.format(need=short_need(out.get("uncoveredNeed")))
    else:
        message = None
    return {"matches": matches, "message": message}
