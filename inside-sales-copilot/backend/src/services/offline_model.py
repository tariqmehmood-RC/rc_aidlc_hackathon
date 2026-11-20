"""A deterministic stand-in for the Bedrock client, used for tests and `--fake-bedrock` runs.

It answers every prompt (P1 to P5) with simple rules instead of a language model, so the whole
pipeline can run with no AWS access. Its answers are checked against the same JSON schemas as
the real model's. It is NOT used in the deployed system.
"""
from __future__ import annotations

import datetime
import html
import json
import re
from typing import Any

from jsonschema import Draft202012Validator

from ..lib import constants as c
from . import brief_writer, case_study_matcher, invite_parser, research as research_mod, rules as rules_mod

_EMAIL = re.compile(r"[\w.+\-']+@[\w.\-]+\.[A-Za-z]{2,}")
_INDUSTRY_WORDS = {
    "insurance": "Insurance", "airline": "Airline", "bank": "Banking", "retail": "Retail",
    "hotel": "Hospitality", "hospitality": "Hospitality", "language": "Education technology",
    "software": "Software", "logistics": "Logistics", "manufactur": "Manufacturing",
    "health": "Healthcare", "energy": "Energy",
}
_PAIN_TEMPLATES = {
    "Insurance": "Claims and policy systems on legacy IT may slow incident resolution and change.",
    "Airline": "Complex operations make IT incidents and requests costly when they are slow.",
    "Hospitality": "Guest-facing digital services depend on many connected systems that are hard to see end to end.",
    "Education technology": "Fast product growth puts pressure on data pipelines and cloud cost control.",
}
_WORD = re.compile(r"[a-z0-9]{3,}")


def _unwrap(user: str, tag: str) -> str:
    m = re.search(rf"<{tag}>(.*)</{tag}>", user, re.DOTALL)
    return html.unescape(m.group(1)) if m else user


class OfflineModel:
    """Same `converse_json` signature as BedrockClient."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.usage: dict[str, dict[str, int]] = {}

    def converse_json(self, *, model: str, system: str, user: str, max_tokens: int,
                      schema: dict[str, Any], temperature: float | None = None) -> dict[str, Any]:
        self.calls.append({"model": model, "max_tokens": max_tokens})
        totals = self.usage.setdefault(model, {"calls": 0, "inputTokens": 0, "outputTokens": 0})
        totals["calls"] += 1
        handlers = {
            id(invite_parser.P1_SCHEMA): self._parse,
            id(research_mod.P2_SCHEMA): self._research,
            id(case_study_matcher.P3_SCHEMA): self._score,
            id(brief_writer.P4_SCHEMA): self._write,
            id(rules_mod.P5_SCHEMA): self._rules,
        }
        handler = handlers.get(id(schema))
        if handler is None:
            raise AssertionError("OfflineModel does not know this prompt")
        out = handler(user)
        Draft202012Validator(schema).validate(out)  # stay as strict as the real model's contract
        return out

    # -- P1: invite -------------------------------------------------------------------------------
    def _parse(self, user: str) -> dict[str, Any]:
        text = _unwrap(user, "invite")
        subject = notes = date = name = domain = None
        attendees: list[dict[str, Any]] = []
        for raw in text.splitlines():
            line = raw.strip()
            low = line.lower()
            if low.startswith("subject:"):
                subject = line.split(":", 1)[1].strip()
            elif low.startswith("notes:"):
                notes = line.split(":", 1)[1].strip()
            elif low.startswith("date:"):
                date = date or self._date(line.split(":", 1)[1])
            elif low.startswith(("company:", "prospect:")):
                name, domain = self._company(line.split(":", 1)[1])
            elif _EMAIL.search(line) and not low.startswith(("organizer", "who is")):
                attendees.append(self._attendee(line))
        if date is None:
            date = self._date(text) if re.search(r"\d{4}-\d{2}-\d{2}", text) else None
        return {"subject": subject, "company": {"name": name, "domain": domain}, "attendees": attendees,
                "meetingDate": date, "notes": notes}

    @staticmethod
    def _date(text: str) -> str | None:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
        if m:
            return m.group(1)
        m = re.search(r"([A-Z][a-z]+) (\d{1,2}), (\d{4})", text)
        if m:
            try:
                return datetime.datetime.strptime(" ".join(m.groups()), "%B %d %Y").date().isoformat()
            except ValueError:
                return None
        return None

    @staticmethod
    def _company(text: str) -> tuple[str | None, str | None]:
        text = text.strip()
        domain = None
        m = re.search(r"\(([^)]*\.[a-z]{2,})\)", text) or re.search(r",?\s*domain\s+(\S+)", text)
        if m:
            domain = m.group(1).strip().lower()
            text = text[: m.start()].strip(" ,")
        return (text or None), domain

    @staticmethod
    def _attendee(line: str) -> dict[str, Any]:
        email = _EMAIL.search(line).group(0)
        rest = line.replace(email, "")
        rest = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", rest.strip())
        if "|" in rest:
            parts = [p.strip() for p in rest.split("|")]
            name, title = parts[0], (parts[1] if len(parts) > 1 and parts[1] else None)
        elif " - " in rest:
            name, _, title = rest.partition(" - ")
            title = title.strip(" -,") or None
        else:
            name, _, title = rest.partition(",")
            title = title.strip(" ,") or None
        return {"name": name.strip(" ,-"), "title": title, "email": email}

    # -- P2: research -------------------------------------------------------------------------------
    def _research(self, user: str) -> dict[str, Any]:
        docs = re.findall(r'<document id="d\d+" url="([^"]*)" kind="([^"]*)">(.*?)</document>', user, re.DOTALL)
        facts: list[dict[str, Any]] = []

        def add(text: str, url: str) -> str:
            fid = f"f{len(facts) + 1}"
            facts.append({"id": fid, "text": text.strip()[:380], "sourceUrls": [html.unescape(url)]})
            return fid

        industry = headquarters = employees = revenue = None
        for url, kind, text in docs:
            text = html.unescape(text)
            if len(facts) >= 20:
                break
            if kind == "news":
                add(f"In the news: {text.strip()}", url)
                continue
            first = re.split(r"(?<=[.!?])\s+", text.strip())[0]
            fid = add(first, url) if first else None
            if industry is None and fid:
                low = text.lower()
                for word, label in _INDUSTRY_WORDS.items():
                    if word in low:
                        industry = {"value": label, "factId": fid}
                        break
            hq = re.search(r"headquartered in ([A-Z][\w.\- ]+(?:, [A-Z][\w. ]+){0,2})", text)
            if hq and headquarters is None:
                headquarters = {"value": hq.group(1).strip()[:100], "factId": add(f"Headquartered in {hq.group(1).strip()[:100]}.", url)}
            emp = re.search(r"(\d{1,3}(?:,\d{3})+|\d{3,})\s+(?:employees|people|team members)", text)
            if emp and employees is None:
                value = int(emp.group(1).replace(",", ""))
                employees = {"value": value, "factId": add(f"Employs about {value:,} people.", url)}
            rev = re.search(r"\$\s?(\d+(?:\.\d+)?)\s?(billion|million)\s+(?:in\s+)?(?:annual\s+)?revenue", text, re.IGNORECASE)
            if rev and revenue is None:
                amount = float(rev.group(1)) * (1e9 if rev.group(2).lower() == "billion" else 1e6)
                revenue = {"value": amount, "factId": add(f"Annual revenue of about ${rev.group(1)} {rev.group(2).lower()}.", url)}
        pain_points = []
        label = industry["value"] if industry else None
        if facts and label in _PAIN_TEMPLATES:
            pain_points.append({"id": "p1", "hypothesis": _PAIN_TEMPLATES[label], "basedOnFactIds": [industry["factId"]]})
        if facts:
            pain_points.append({"id": f"p{len(pain_points) + 1}",
                                "hypothesis": "Growth and change put pressure on operations and visibility across IT systems.",
                                "basedOnFactIds": [facts[0]["id"]]})
        return {"facts": facts, "industry": industry, "headquarters": headquarters,
                "employees": employees, "revenueUsd": revenue, "painPoints": pain_points[:5]}

    # -- P3: case study scores -------------------------------------------------------------------------
    def _score(self, user: str) -> dict[str, Any]:
        industry = (re.search(r"^industry: (.*)$", user, re.MULTILINE) or [None, ""])[1].strip().lower()
        pain = " ".join(re.findall(r"^- p\d+: (.*)$", user, re.MULTILINE)).lower()
        needs_m = re.search(r"<stated_needs>\n(.*?)\n</stated_needs>", user, re.DOTALL)
        needs = html.unescape(needs_m.group(1)).lower() if needs_m else ""
        prospect_words = set(_WORD.findall(pain + " " + industry + " " + needs))
        scores = []
        for cid, body in re.findall(r'<case_study id="([^"]+)">(.*?)</case_study>', user, re.DOTALL):
            body = html.unescape(body)
            cs_industry = (re.search(r"^industry: (.*)$", body, re.MULTILINE) or [None, ""])[1].strip().lower()
            tags = [t.strip() for t in (re.search(r"^tags: (.*)$", body, re.MULTILINE) or [None, ""])[1].split(",") if t.strip()]
            matched = [t for t in tags if set(_WORD.findall(t.lower())) & prospect_words]
            same_industry = bool(industry) and industry == cs_industry
            score = min(95, 50 + (16 if same_industry else 0) + 8 * len(matched))
            why = []
            if same_industry:
                why.append(f"the same {cs_industry} industry")
            if matched:
                why.append("topics such as " + ", ".join(matched[:2]))
            reason = ("Relevant because it covers " + " and ".join(why) + ".") if why else "Little overlap with the prospect's context."
            scores.append({"caseStudyId": cid, "score": score, "reason": reason})
        first_pain = re.search(r"^- p\d+: (.*)$", user, re.MULTILINE)
        label = " ".join(first_pain.group(1).split()[:5]).strip(".,") if first_pain else None
        return {"scores": scores[: c.CASE_STUDY_CANDIDATES], "uncoveredNeed": label}

    # -- P4: the brief -------------------------------------------------------------------------------------
    def _write(self, user: str) -> dict[str, Any]:
        facts = re.findall(r"^- (f\d+): (.*?) \[sources: (.*?)\]$", user, re.MULTILINE)
        pains = re.findall(r"^- (p\d+): (.*?) \(based on ([^)]*)\)$", user, re.MULTILINE)
        rules = re.search(r"<rules>\n(.*?)\n</rules>", user, re.DOTALL)
        rule_text = (rules.group(1) if rules else "").lower()
        company = (re.search(r"^company: (.*?) \(", user, re.MULTILINE) or [None, "the company"])[1]
        snapshot = [{"text": text, "sourceUrls": [u.strip() for u in urls.split(",")][:2]} for _, text, urls in facts[:4]]
        hypotheses = [{"text": text, "basedOnFactIds": [f.strip() for f in based.split(",")]} for _, text, based in pains[:3]]
        questions = [
            f"What are the biggest priorities for {company}'s IT organization this year?",
            "How do incidents and service requests get handled today, and where does it hurt?",
            "Which systems or tools are hardest to see end to end?",
            "What has been tried before, and what happened?",
            "Who else needs to be involved in a decision like this?",
            "What does success look like in 12 months?",
            "How do you measure the current process today?",
            "What are the main risks or compliance constraints we should plan for?",
            "What timeline are you working to?",
        ]
        if "budget" in rule_text:
            questions[8] = "What is your budget cycle, and when are funds decided?"
        return {
            "companySnapshot": snapshot,
            "painPointHypotheses": hypotheses,
            "agenda": [
                {"minutes": 5, "topic": "Introductions", "note": "Roles and goals for the call"},
                {"minutes": 10, "topic": "Current IT landscape", "note": "Tools, teams, and pain points"},
                {"minutes": 10, "topic": "Priorities and constraints", "note": "Timeline, budget, and decision makers"},
                {"minutes": 5, "topic": "Next steps", "note": "Agree owners and a follow-up date"},
            ],
            "discoveryQuestions": [{"text": q} for q in questions],
        }

    # -- P5: rules ----------------------------------------------------------------------------------------------
    def _rules(self, user: str) -> dict[str, Any]:
        m = re.search(r"<changes>\n(.*?)\n</changes>", user, re.DOTALL)
        changes = json.loads(html.unescape(m.group(1))) if m else []
        text = json.dumps(changes).lower()
        if "budget" in text:
            return {"rules": [{"text": "Always ask about the budget cycle.", "rationale": "You added or changed a budget question."}]}
        if any(ch.get("change") == "edited" and ch.get("section") == "discoveryQuestions" for ch in changes):
            return {"rules": [{"text": "Keep discovery questions short and specific.", "rationale": "You rewrote a discovery question."}]}
        return {"rules": []}
