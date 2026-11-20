"""Company research (requirements R3, design 8.2 and prompt P2).

Order of work: cache lookup, fetch public pages through a ResearchProvider, one Haiku call to
extract facts, then plain code that removes anything not backed by a fetched page, computes the
size tier, and caches the result for 7 days.
"""
from __future__ import annotations

import html
import json
import re
import time
from typing import Any, Callable

from ..lib import constants as c
from ..lib import models
from .research_provider import RawResearch, ResearchProvider
from .size_tier import compute_size_tier

MAX_PROMPT_DOC_CHARS = 4000
MAX_PROMPT_TOTAL_CHARS = 24_000
CACHE_SECONDS = c.RESEARCH_CACHE_DAYS * 24 * 3600


class NoPublicInfo(Exception):
    """No source returned anything usable. The brief fails with code NO_PUBLIC_INFO."""

    code = "NO_PUBLIC_INFO"


P2_SYSTEM = (
    "You are given numbered documents about one company, each with its URL. Extract only facts "
    "stated in the documents. Every fact must list the URLs of the documents that state it, "
    "using only the URLs provided. Return industry and headquarters as a short value (for "
    "example 'Airline' or 'Atlanta, Georgia, United States') with the id of the fact that "
    "states it, or null. Return employees and revenueUsd as plain numbers (revenue in US "
    "dollars) with the id of the fact that states them, only if a document states them, "
    "otherwise null. Write pain points as hypotheses about what this kind of company in this "
    "situation likely struggles with. Each hypothesis must cite the ids of the facts it is based "
    "on. Do not write a hypothesis you cannot tie to a fact."
)

_VALUE_REF = {
    "type": ["object", "null"],
    "required": ["value", "factId"],
    "additionalProperties": False,
    "properties": {"value": {"type": "string", "maxLength": 200}, "factId": {"type": "string"}},
}
_NUMBER_REF = {
    "type": ["object", "null"],
    "required": ["value", "factId"],
    "additionalProperties": False,
    "properties": {"value": {"type": "number"}, "factId": {"type": "string"}},
}
P2_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["facts", "industry", "headquarters", "employees", "revenueUsd", "painPoints"],
    "additionalProperties": False,
    "properties": {
        "facts": {
            "type": "array", "maxItems": 25,
            "items": {
                "type": "object", "required": ["id", "text", "sourceUrls"], "additionalProperties": False,
                "properties": {
                    "id": {"type": "string", "pattern": r"^f\d+$"},
                    "text": {"type": "string", "maxLength": 400},
                    "sourceUrls": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                },
            },
        },
        "industry": _VALUE_REF,
        "headquarters": _VALUE_REF,
        "employees": _NUMBER_REF,
        "revenueUsd": _NUMBER_REF,
        "painPoints": {
            "type": "array", "maxItems": 5,
            "items": {
                "type": "object", "required": ["id", "hypothesis", "basedOnFactIds"], "additionalProperties": False,
                "properties": {
                    "id": {"type": "string", "pattern": r"^p\d+$"},
                    "hypothesis": {"type": "string", "maxLength": 400},
                    "basedOnFactIds": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                },
            },
        },
    },
}

_CLOSING_DOC_RE = re.compile(r"</\s*document\s*>", re.IGNORECASE)


def cache_key(company_name: str | None, domain: str | None) -> str:
    if domain:
        return domain.strip().lower()
    return "name:" + re.sub(r"[^a-z0-9]", "", (company_name or "").lower())


def _norm_url(url: str) -> str:
    return url.split("#")[0].rstrip("/")


def build_user_message(company_name: str | None, domain: str | None, raw: RawResearch) -> str:
    esc = lambda s: html.escape(s or "", quote=True)  # noqa: E731
    parts = [f'<company name="{esc(company_name)}" domain="{esc(domain)}"/>']
    used = 0
    for i, doc in enumerate(raw.documents, 1):
        text = _CLOSING_DOC_RE.sub("&lt;/document&gt;", doc.text[:MAX_PROMPT_DOC_CHARS])
        if used + len(text) > MAX_PROMPT_TOTAL_CHARS:
            break
        used += len(text)
        parts.append(f'<document id="d{i}" url="{esc(doc.url)}" kind="{esc(doc.kind)}">{text}</document>')
    return "\n".join(parts)


class ResearchService:
    def __init__(self, bedrock, provider: ResearchProvider, table, clock: Callable[[], float] = time.time):
        self.bedrock = bedrock
        self.provider = provider
        self.table = table  # DynamoDB Table resource for ResearchCache
        self.clock = clock

    # -- cache ------------------------------------------------------------------------------------
    def _cache_get(self, key: str) -> dict[str, Any] | None:
        item = self.table.get_item(Key={"companyDomain": key}).get("Item")
        if not item:
            return None
        # DynamoDB TTL deletes late, so the age is checked here too (R3.12).
        age_ms = self.clock() * 1000 - int(item.get("retrievedAt", 0))
        if age_ms >= CACHE_SECONDS * 1000:
            return None
        try:
            research = json.loads(item["researchJson"])
            models.validate("research_result", research)
        except (KeyError, ValueError, TypeError):
            return None
        return research

    def _cache_put(self, key: str, research: dict[str, Any]) -> None:
        retrieved_ms = int(research["retrievedAt"])
        self.table.put_item(Item={
            "companyDomain": key,
            "researchJson": json.dumps(research, separators=(",", ":")),
            "retrievedAt": retrieved_ms,
            "expiresAt": retrieved_ms // 1000 + CACHE_SECONDS,
        })

    # -- main entry -------------------------------------------------------------------------------
    def get_research(self, company_name: str | None, domain: str | None) -> tuple[dict[str, Any], bool]:
        """Return (research result, cache_hit). Raises NoPublicInfo or a Bedrock error."""
        key = cache_key(company_name, domain)
        cached = self._cache_get(key)
        if cached is not None:
            return cached, True

        raw = self.provider.research(company_name, domain)
        if not raw.documents:
            raise NoPublicInfo("no public information was found for this company")

        extracted = self.bedrock.converse_json(
            model=c.MODEL_HAIKU,
            system=P2_SYSTEM,
            user=build_user_message(company_name, domain, raw),
            max_tokens=c.MAX_TOKENS["research"],
            schema=P2_SCHEMA,
        )
        research = self._assemble(company_name, domain, raw, extracted)
        if not research["facts"] and not research["news"]:
            raise NoPublicInfo("no usable facts could be sourced for this company")
        self._cache_put(key, research)
        return research, False

    # -- source integrity (design 8.2) ---------------------------------------------------------------
    def _assemble(self, company_name, domain, raw: RawResearch, out: dict[str, Any]) -> dict[str, Any]:
        allowed = {_norm_url(u): u for u in raw.usable_urls}

        facts: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for f in out["facts"]:
            urls = list(dict.fromkeys(allowed[_norm_url(u)] for u in f["sourceUrls"] if _norm_url(u) in allowed))
            if not urls or f["id"] in seen_ids:
                continue  # a fact without a fetched source is dropped (R3.3)
            seen_ids.add(f["id"])
            facts.append({"id": f["id"], "text": f["text"], "sourceUrls": urls})
        by_id = {f["id"]: f for f in facts}

        def ref(obj: dict[str, Any] | None, kind: str) -> dict[str, Any] | None:
            if not obj or obj["factId"] not in by_id:
                return None  # a claim without a surviving fact is rejected (R3.4)
            value = obj["value"]
            if kind == "text":
                return {"value": value.strip(), "factId": obj["factId"]} if value.strip() else None
            if isinstance(value, bool) or value < 0:
                return None
            return {"value": value, "factId": obj["factId"]}

        industry = ref(out.get("industry"), "text")
        headquarters = ref(out.get("headquarters"), "text")
        employees = ref(out.get("employees"), "number")
        revenue = ref(out.get("revenueUsd"), "number")

        basis_urls: list[str] = []
        for r in (employees, revenue):
            if r:
                basis_urls += by_id[r["factId"]]["sourceUrls"]
        size_tier = compute_size_tier(
            employees["value"] if employees else None,
            revenue["value"] if revenue else None,
            basis_urls,
        )

        pain_points: list[dict[str, Any]] = []
        used_ids: set[str] = set()
        for p in out["painPoints"]:
            based_on = [fid for fid in p["basedOnFactIds"] if fid in by_id]
            if not based_on or p["id"] in used_ids:
                continue  # a hypothesis with no supporting fact is dropped (R3.10)
            used_ids.add(p["id"])
            pain_points.append({"id": p["id"], "hypothesis": p["hypothesis"], "basedOnFactIds": based_on})

        result = {
            "company": {
                "name": company_name or domain or "",
                "domain": domain or "",
                "matchConfidence": raw.match_confidence,
            },
            "retrievedAt": int(self.clock() * 1000),
            "facts": facts,
            "industry": industry,
            "headquarters": headquarters,
            "employees": employees,
            "revenueUsd": revenue,
            "sizeTier": size_tier,
            "news": [n.__dict__.copy() for n in raw.news[: c.MAX_NEWS_ITEMS]],
            "painPoints": pain_points,
            "sourcesFetched": [s.__dict__.copy() for s in raw.sources],
        }
        models.validate("research_result", result)
        return result
