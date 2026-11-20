"""Writing the discovery brief (requirements R6, prompt P4, design 5.7 and 10).

The model (Sonnet) writes only the free-text parts: snapshot facts, pain-point hypotheses, the
agenda, and the discovery questions. Everything that must be exact is built here in code: the
attendee list, case studies, size tier, news, source list, ids, and the section order.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any, Sequence
from urllib.parse import urlsplit

from ..lib import constants as c
from ..lib import models

P4_SYSTEM = (
    "Write a discovery call brief for a Royal Cyber sales engineer. Use only the research facts, "
    "attendee checks, and case studies provided. Every statement of fact must cite sourceUrls "
    "taken from the facts. Where information is unknown, say it is unknown. Never use an "
    "unverified attendee's claimed role as a fact. Write exactly 8 to 10 discovery questions and "
    "an agenda of time blocks that add up to exactly 30 minutes. Apply the user's rules where "
    "they fit. Write at most 5 company snapshot items, the most useful for the call; do not "
    "repeat news headlines there, they are added separately. Keep each item short. Do not add "
    "sections."
)

P4_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["companySnapshot", "painPointHypotheses", "agenda", "discoveryQuestions"],
    "additionalProperties": False,
    "properties": {
        "companySnapshot": {
            "type": "array", "maxItems": c.MAX_SNAPSHOT_ITEMS,
            "items": {"type": "object", "required": ["text", "sourceUrls"], "additionalProperties": False,
                      "properties": {"text": {"type": "string", "maxLength": 400},
                                     "sourceUrls": {"type": "array", "minItems": 1, "items": {"type": "string"}}}},
        },
        "painPointHypotheses": {
            "type": "array", "maxItems": 5,
            "items": {"type": "object", "required": ["text", "basedOnFactIds"], "additionalProperties": False,
                      "properties": {"text": {"type": "string", "maxLength": 400},
                                     "basedOnFactIds": {"type": "array", "minItems": 1, "items": {"type": "string"}}}},
        },
        "agenda": {
            "type": "array", "minItems": 3, "maxItems": 8,
            "items": {"type": "object", "required": ["minutes", "topic", "note"], "additionalProperties": False,
                      "properties": {"minutes": {"type": "integer", "minimum": 1, "maximum": c.AGENDA_TOTAL_MINUTES},
                                     "topic": {"type": "string", "maxLength": 120},
                                     "note": {"type": "string", "maxLength": 300}}},
        },
        "discoveryQuestions": {
            "type": "array", "minItems": c.QUESTIONS_MIN, "maxItems": c.QUESTIONS_MAX,
            "items": {"type": "object", "required": ["text"], "additionalProperties": False,
                      "properties": {"text": {"type": "string", "maxLength": 300}}},
        },
    },
}

SECTION_ORDER = ("companySnapshot", "attendees", "painPointHypotheses", "agenda",
                 "discoveryQuestions", "caseStudies", "sources")


class BriefWriteError(Exception):
    """The model could not produce a valid brief, even after one correction."""

    code = "WRITE_FAILED"


@dataclass
class WrittenBrief:
    content: dict[str, Any]
    rules_applied: list[dict[str, str]]
    model: str = c.DEFAULT_BRIEF_MODEL
    repairs: int = 0                      # check-failure corrections (0 or 1)
    repair_problems: list[str] | None = None  # which checks failed, for the logs


# --- helpers -------------------------------------------------------------------------------------
def _norm_url(url: str) -> str:
    return url.split("#")[0].rstrip("/")


def known_urls(research: dict[str, Any]) -> dict[str, str]:
    """normalized URL -> original URL, for every URL the research really fetched."""
    urls: list[str] = []
    for f in research.get("facts", []):
        urls += f["sourceUrls"]
    urls += [n["url"] for n in research.get("news", [])]
    urls += research.get("sizeTier", {}).get("basis", {}).get("sourceUrls", [])
    return {_norm_url(u): u for u in urls}


def _label(url: str, news_titles: dict[str, str]) -> str:
    if url in news_titles:
        return f"News: {news_titles[url]}"[:120]
    host = (urlsplit(url).hostname or url).removeprefix("www.")
    return {"en.wikipedia.org": "Wikipedia", "royalcyber.com": "Royal Cyber case study"}.get(host, host)


def _esc(text: str) -> str:
    return re.sub(r"</\s*(research|attendees|case_studies|rules|notes|meeting)\s*>", r"&lt;/\1&gt;", text, flags=re.IGNORECASE)


def build_user_message(research: dict[str, Any], attendee_checks: Sequence[dict[str, Any]],
                       case_matches: dict[str, Any], rules: Sequence[dict[str, Any]],
                       meeting: dict[str, Any]) -> str:
    lines = ["<research>"]
    lines.append(f"company: {_esc(research['company']['name'])} ({research['company']['domain']})")
    lines.append(f"industry: {_esc((research.get('industry') or {}).get('value') or 'unknown')}")
    lines.append(f"headquarters: {_esc((research.get('headquarters') or {}).get('value') or 'unknown')}")
    tier = research.get("sizeTier", {})
    lines.append(f"size tier: {tier.get('tier', 'Unknown')} ({_esc(tier.get('rule', ''))})")
    lines.append("facts:")
    for f in research.get("facts", []):
        lines.append(f"- {f['id']}: {_esc(f['text'])} [sources: {', '.join(f['sourceUrls'])}]")
    if not research.get("facts"):
        lines.append("- none found")
    lines.append("recent news:")
    for n in research.get("news", []):
        lines.append(f"- {_esc(n['title'])} ({n.get('date') or 'date unknown'}) [source: {n['url']}]")
    if not research.get("news"):
        lines.append("- none found")
    lines.append("pain point hypotheses:")
    for p in research.get("painPoints", []):
        lines.append(f"- {p['id']}: {_esc(p['hypothesis'])} (based on {', '.join(p['basedOnFactIds'])})")
    if not research.get("painPoints"):
        lines.append("- none found")
    lines.append("</research>")

    lines.append("<attendees>")
    for a in attendee_checks:
        if a["status"] == c.VERDICT_VERIFIED:
            lines.append(f"- {_esc(a['name'])}: verified, {_esc(a['invitedTitle'] or '')}")
        else:
            # the claimed title is deliberately NOT given to the model for unverified attendees
            lines.append(f"- {_esc(a['name'])}: unverified ({a['reason']}), role not confirmed")
    lines.append("</attendees>")

    lines.append("<case_studies>")
    for m in case_matches.get("matches", []):
        lines.append(f"- {m['caseStudyId']}: {_esc(m['title'])}. Why relevant: {_esc(m['reason'])}")
    if not case_matches.get("matches"):
        lines.append("- none matched")
    lines.append("</case_studies>")

    lines.append("<rules>")
    lines += [f"- {_esc(r['text'])}" for r in list(rules)[: c.MAX_RULES_APPLIED]] or ["- none"]
    lines.append("</rules>")

    subject = html.escape(meeting.get("subject") or "", quote=True)
    lines.append(f'<meeting subject="{subject}" date="{meeting.get("meetingDate") or "unknown"}"/>')
    lines.append("<notes>" + _esc(meeting.get("notes") or "none") + "</notes>")
    return "\n".join(lines)


# --- checks on the model's answer ------------------------------------------------------------------
def check_draft(draft: dict[str, Any], research: dict[str, Any], attendee_checks: Sequence[dict[str, Any]]) -> list[str]:
    """Problems the model must fix. An empty list means the draft is acceptable."""
    problems: list[str] = []
    total = sum(item["minutes"] for item in draft["agenda"])
    if total != c.AGENDA_TOTAL_MINUTES:
        problems.append(f"The agenda minutes add up to {total}. They must add up to exactly {c.AGENDA_TOTAL_MINUTES}.")
    n = len(draft["discoveryQuestions"])
    if not c.QUESTIONS_MIN <= n <= c.QUESTIONS_MAX:
        problems.append(f"There are {n} discovery questions. Write {c.QUESTIONS_MIN} to {c.QUESTIONS_MAX}.")

    texts = [i["text"] for i in draft["companySnapshot"]] + [i["text"] for i in draft["painPointHypotheses"]] \
        + [f"{i['topic']} {i['note']}" for i in draft["agenda"]] + [i["text"] for i in draft["discoveryQuestions"]]
    blob = " ".join(texts).lower()
    for a in attendee_checks:
        title = (a.get("invitedTitle") or "").strip()
        if a["status"] != c.VERDICT_VERIFIED and len(title) >= 4 and title.lower() in blob:
            problems.append(f"Do not use the unverified attendee's claimed title \"{title}\". Their role is not confirmed.")
    return problems


def _assemble(draft: dict[str, Any], research: dict[str, Any], attendee_checks: Sequence[dict[str, Any]],
              case_matches: dict[str, Any]) -> dict[str, Any]:
    allowed = known_urls(research)
    fact_urls = {f["id"]: f["sourceUrls"] for f in research.get("facts", [])}
    news_titles = {n["url"]: n["title"] for n in research.get("news", [])}

    # 1. Company snapshot: size tier first, then the model's sourced items, then news, then unknowns.
    snapshot: list[dict[str, Any]] = []
    tier = research.get("sizeTier", {})
    tier_urls = [allowed[_norm_url(u)] for u in tier.get("basis", {}).get("sourceUrls", []) if _norm_url(u) in allowed]
    snapshot.append({"text": f"Size tier: {tier.get('tier', 'Unknown')}. Rule used: {tier.get('rule', 'not available')}",
                     "sourceUrls": tier_urls})
    for item in draft["companySnapshot"]:
        urls = list(dict.fromkeys(allowed[_norm_url(u)] for u in item["sourceUrls"] if _norm_url(u) in allowed))
        if urls:                                   # an invented or unsourced statement is dropped
            snapshot.append({"text": item["text"], "sourceUrls": urls})
    for n in research.get("news", []):
        when = f" ({n['date']})" if n.get("date") else ""
        snapshot.append({"text": f"Recent news: {n['title']}{when}", "sourceUrls": [n["url"]]})
    missing = [name for name, key in (("industry", "industry"), ("headquarters", "headquarters"),
                                      ("employee count", "employees")) if not research.get(key)]
    if missing:
        snapshot.append({"text": f"Unknown (not found in public sources): {', '.join(missing)}.", "sourceUrls": []})
    for i, item in enumerate(snapshot, 1):
        item["id"] = f"b{i}"

    # 2. Attendees: straight from the attendee check, never from the model.
    attendees = [{"email": a["email"], "name": a["name"], "title": a["invitedTitle"],
                  "status": a["status"], "reason": a["reason"]} for a in attendee_checks]

    # 3. Pain-point hypotheses: keep only those tied to real facts; sources come from those facts.
    hypotheses: list[dict[str, Any]] = []
    for item in draft["painPointHypotheses"]:
        based_on = [fid for fid in item["basedOnFactIds"] if fid in fact_urls]
        if not based_on:
            continue
        urls = list(dict.fromkeys(u for fid in based_on for u in fact_urls[fid]))
        hypotheses.append({"text": item["text"], "basedOnFactIds": based_on, "sourceUrls": urls})
    if not hypotheses:
        hypotheses.append({"text": "No pain-point hypotheses could be sourced from public information.",
                           "basedOnFactIds": [], "sourceUrls": []})
    for i, item in enumerate(hypotheses, 1):
        item["id"] = f"h{i}"

    agenda = [{"id": f"a{i}", "minutes": a["minutes"], "topic": a["topic"], "note": a["note"]}
              for i, a in enumerate(draft["agenda"], 1)]
    questions = [{"id": f"q{i}", "text": q["text"]} for i, q in enumerate(draft["discoveryQuestions"], 1)]

    # 4. Case studies: straight from the matcher (titles and URLs come from the library file).
    case_studies = [{"caseStudyId": m["caseStudyId"], "title": m["title"], "url": m["url"], "reason": m["reason"]}
                    for m in case_matches.get("matches", [])]

    # 5. Sources: every URL cited anywhere in the brief, once.
    cited: list[str] = []
    for item in snapshot + hypotheses:
        cited += item["sourceUrls"]
    cited += [m["url"] for m in case_studies]
    sources = [{"url": u, "label": _label(u, news_titles)} for u in dict.fromkeys(cited)]

    content: dict[str, Any] = {
        "companySnapshot": [_ordered(i, ("id", "text", "sourceUrls")) for i in snapshot],
        "attendees": attendees,
        "painPointHypotheses": [_ordered(i, ("id", "text", "basedOnFactIds", "sourceUrls")) for i in hypotheses],
        "agenda": agenda,
        "discoveryQuestions": questions,
        "caseStudies": case_studies,
        "sources": sources,
    }
    if case_matches.get("message"):
        content["caseStudiesNote"] = case_matches["message"]
    return content


def _ordered(item: dict[str, Any], keys: Sequence[str]) -> dict[str, Any]:
    return {k: item[k] for k in keys}


# --- main entry ------------------------------------------------------------------------------------
def brief_model_from_env(env: dict[str, str] | None = None) -> str:
    """haiku or sonnet, from BRIEF_MODEL. Anything else falls back to the default."""
    import os

    value = (env if env is not None else os.environ).get(c.ENV_BRIEF_MODEL, "").strip().lower()
    return value if value in c.BRIEF_MODELS else c.DEFAULT_BRIEF_MODEL


def write_brief(bedrock, *, research: dict[str, Any], attendee_checks: Sequence[dict[str, Any]],
                case_matches: dict[str, Any], rules: Sequence[dict[str, Any]],
                meeting: dict[str, Any], model: str = c.DEFAULT_BRIEF_MODEL,
                log=None) -> WrittenBrief:
    """Run prompt P4 (Haiku or Sonnet), check the answer, correct it once if needed, assemble."""
    if model not in c.BRIEF_MODELS:
        raise ValueError(f"unknown brief model {model!r}")
    applied = [{"ruleId": r.get("ruleId", ""), "text": r["text"]} for r in list(rules)[: c.MAX_RULES_APPLIED]]
    user = build_user_message(research, attendee_checks, case_matches, applied, meeting)

    def ask(message: str) -> dict[str, Any]:
        return bedrock.converse_json(model=model, system=P4_SYSTEM, user=message,
                                     max_tokens=c.MAX_TOKENS["write"], schema=P4_SCHEMA)

    draft = ask(user)
    problems = check_draft(draft, research, attendee_checks)
    first_problems = list(problems)
    if problems:  # one correction, no more (R6.9)
        if log:
            log("brief_check_failed", {"model": model, "checks": [_check_name(p) for p in problems]})
        draft = ask(user + "\n\nYour previous answer had these problems. Fix them and return the full JSON again:\n"
                    + "\n".join(f"- {p}" for p in problems))
        problems = check_draft(draft, research, attendee_checks)
        if problems:
            raise BriefWriteError("the brief did not pass the checks: " + " ".join(problems))

    content = _assemble(draft, research, attendee_checks, case_matches)
    models.validate("brief_content", content)
    return WrittenBrief(content=content, rules_applied=applied, model=model,
                        repairs=1 if first_problems else 0,
                        repair_problems=[_check_name(p) for p in first_problems])


def _check_name(problem: str) -> str:
    """A short, data-free name for a failed check (safe to log)."""
    if problem.startswith("The agenda"):
        return "agenda_minutes"
    if problem.startswith("There are"):
        return "question_count"
    if "unverified attendee" in problem:
        return "unverified_title_used"
    return "other"
