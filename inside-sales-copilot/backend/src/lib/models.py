"""Shared data types and JSON schemas (design section 5).

Wire format is camelCase JSON. Dataclasses use snake_case and convert with `to_dict` and
`from_dict`. Everything that crosses a trust boundary (model output, API bodies, stored
items) is checked with `validate`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jsonschema import Draft202012Validator

from . import constants as c

_STR = {"type": "string"}
_NULL_STR = {"type": ["string", "null"]}
_URL_LIST = {"type": "array", "items": _STR, "minItems": 1}


class ModelValidationError(ValueError):
    """Data does not match its schema. The message lists paths only, never the values."""

    def __init__(self, schema_name: str, problems: list[str]):
        super().__init__(f"{schema_name} is invalid: " + "; ".join(problems[:10]))
        self.schema_name = schema_name
        self.problems = problems


# --- JSON schemas ------------------------------------------------------------------------
SCHEMAS: dict[str, dict[str, Any]] = {}

SCHEMAS["parsed_invite"] = {
    "type": "object",
    "required": ["subject", "company", "attendees", "meetingDate", "notes"],
    "additionalProperties": False,
    "properties": {
        "subject": {"type": ["string", "null"], "maxLength": 300},
        "company": {
            "type": "object",
            "required": ["name", "domain"],
            "additionalProperties": False,
            "properties": {
                "name": {"type": ["string", "null"], "maxLength": 200},
                "domain": {"type": ["string", "null"], "maxLength": 253},
            },
        },
        "attendees": {
            "type": "array",
            "maxItems": 40,
            "items": {
                "type": "object",
                "required": ["name", "title", "email"],
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "maxLength": 200},
                    "title": {"type": ["string", "null"], "maxLength": 200},
                    "email": {"type": "string", "maxLength": 254},
                },
            },
        },
        "meetingDate": {"type": ["string", "null"], "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "notes": {"type": ["string", "null"], "maxLength": 3000},
        "warnings": {"type": "array", "items": {"enum": list(c.INVITE_WARNINGS)}},
    },
}

_FACT = {
    "type": "object",
    "required": ["id", "text", "sourceUrls"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "pattern": r"^f\d+$"},
        "text": {"type": "string", "maxLength": 400},
        "sourceUrls": _URL_LIST,
    },
}
_FACT_REF = {
    "type": "object",
    "required": ["value", "factId"],
    "additionalProperties": False,
    "properties": {"value": {"type": ["string", "number", "null"]}, "factId": {"type": ["string", "null"]}},
}

SCHEMAS["research_result"] = {
    "type": "object",
    "required": ["company", "retrievedAt", "facts", "industry", "headquarters", "employees",
                 "revenueUsd", "sizeTier", "news", "painPoints", "sourcesFetched"],
    "additionalProperties": False,
    "properties": {
        "company": {
            "type": "object",
            "required": ["name", "domain", "matchConfidence"],
            "additionalProperties": False,
            "properties": {
                "name": _STR,
                "domain": _STR,
                "matchConfidence": {"enum": ["confirmed", "unverified_match"]},
            },
        },
        "retrievedAt": {"type": "integer", "minimum": 0},
        "facts": {"type": "array", "items": _FACT},
        "industry": {"anyOf": [{"type": "null"}, _FACT_REF]},
        "headquarters": {"anyOf": [{"type": "null"}, _FACT_REF]},
        "employees": {"anyOf": [{"type": "null"}, _FACT_REF]},
        "revenueUsd": {"anyOf": [{"type": "null"}, _FACT_REF]},
        "sizeTier": {
            "type": "object",
            "required": ["tier", "rule", "basis"],
            "additionalProperties": False,
            "properties": {
                "tier": {"enum": list(c.SIZE_TIERS)},
                "rule": _STR,
                "basis": {
                    "type": "object",
                    "required": ["employees", "revenueUsd", "sourceUrls"],
                    "additionalProperties": False,
                    "properties": {
                        "employees": {"type": ["number", "null"]},
                        "revenueUsd": {"type": ["number", "null"]},
                        "sourceUrls": {"type": "array", "items": _STR},
                    },
                },
            },
        },
        "news": {
            "type": "array",
            "maxItems": c.MAX_NEWS_ITEMS,
            "items": {
                "type": "object",
                "required": ["title", "date", "url"],
                "additionalProperties": False,
                "properties": {"title": _STR, "date": _NULL_STR, "url": _STR},
            },
        },
        "painPoints": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "hypothesis", "basedOnFactIds"],
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string", "pattern": r"^p\d+$"},
                    "hypothesis": {"type": "string", "maxLength": 400},
                    "basedOnFactIds": {"type": "array", "minItems": 1, "items": _STR},
                },
            },
        },
        "sourcesFetched": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["url", "status"],
                "additionalProperties": False,
                "properties": {"url": _STR, "status": {"enum": ["ok", "failed", "skipped"]}},
            },
        },
    },
}

SCHEMAS["case_study_matches"] = {
    "type": "object",
    "required": ["matches", "message"],
    "additionalProperties": False,
    "properties": {
        "matches": {
            "type": "array",
            "maxItems": c.MAX_CASE_STUDIES,
            "items": {
                "type": "object",
                "required": ["caseStudyId", "title", "url", "score", "reason"],
                "additionalProperties": False,
                "properties": {
                    "caseStudyId": _STR,
                    "title": _STR,
                    "url": _STR,
                    "score": {"type": "integer", "minimum": c.CASE_STUDY_MIN_SCORE, "maximum": 100},
                    "reason": {"type": "string", "maxLength": 300},
                },
            },
        },
        "message": _NULL_STR,
    },
}

# A block states a sourced fact (at least one URL) or says something is unknown (no URL).
_BLOCK = {
    "type": "object",
    "required": ["id", "text", "sourceUrls"],
    "additionalProperties": False,
    "properties": {"id": _STR, "text": {"type": "string", "maxLength": 400},
                   "sourceUrls": {"type": "array", "items": _STR}},
}

SCHEMAS["brief_content"] = {
    "type": "object",
    "required": ["companySnapshot", "attendees", "painPointHypotheses", "agenda",
                 "discoveryQuestions", "caseStudies", "sources"],  # caseStudiesNote is optional
    "additionalProperties": False,
    "properties": {
        "companySnapshot": {"type": "array", "items": _BLOCK},
        "attendees": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["email", "name", "title"],
                "additionalProperties": False,
                "properties": {"email": _STR, "name": _STR, "title": _NULL_STR},  # as written in the invite
            },
        },
        "painPointHypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "text", "basedOnFactIds", "sourceUrls"],
                "additionalProperties": False,
                "properties": {
                    "id": _STR,
                    "text": {"type": "string", "maxLength": 400},
                    "basedOnFactIds": {"type": "array", "items": _STR},   # empty for the "none found" note
                    "sourceUrls": {"type": "array", "items": _STR},
                },
            },
        },
        "agenda": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "minutes", "topic", "note"],
                "additionalProperties": False,
                "properties": {
                    "id": _STR,
                    "minutes": {"type": "integer", "minimum": 1, "maximum": c.AGENDA_TOTAL_MINUTES},
                    "topic": {"type": "string", "maxLength": 120},
                    "note": {"type": "string", "maxLength": 300},
                },
            },
        },
        "discoveryQuestions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "text"],
                "additionalProperties": False,
                "properties": {"id": _STR, "text": {"type": "string", "maxLength": 300}},
            },
        },
        "caseStudies": {
            "type": "array",
            "maxItems": c.MAX_CASE_STUDIES,
            "items": {
                "type": "object",
                "required": ["caseStudyId", "title", "url", "reason"],
                "additionalProperties": False,
                "properties": {"caseStudyId": _STR, "title": _STR, "url": _STR, "reason": _STR},
            },
        },
        "caseStudiesNote": {"type": ["string", "null"], "maxLength": 300},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["url", "label"],
                "additionalProperties": False,
                "properties": {"url": _STR, "label": _STR},
            },
        },
    },
}

SCHEMAS["case_study"] = {
    "type": "object",
    "required": ["id", "title", "summary", "bu", "client_industry", "tags", "url"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "title": {"type": "string", "minLength": 1, "maxLength": 200},
        "summary": {"type": "string", "minLength": 1, "maxLength": 300},
        "bu": {"enum": list(c.BUSINESS_UNITS)},
        "client_industry": {"type": "string", "minLength": 1},
        "tags": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
        "url": {"type": "string", "pattern": r"^https://"},
    },
}

SCHEMAS["queue_message"] = {
    "type": "object",
    "required": ["type", "briefId", "jobId"],
    "additionalProperties": False,
    "properties": {"type": {"enum": list(c.JOB_TYPES)}, "briefId": _STR, "jobId": _STR},
}

_VALIDATORS = {name: Draft202012Validator(schema) for name, schema in SCHEMAS.items()}
for _name, _schema in SCHEMAS.items():
    Draft202012Validator.check_schema(_schema)


def validate(schema_name: str, data: Any) -> None:
    """Raise ModelValidationError if `data` does not match the named schema."""
    validator = _VALIDATORS[schema_name]
    problems = sorted(
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.validator}"
        for e in validator.iter_errors(data)
    )
    if problems:
        raise ModelValidationError(schema_name, problems)


def is_valid(schema_name: str, data: Any) -> bool:
    return _VALIDATORS[schema_name].is_valid(data)


# --- Dataclasses ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Attendee:
    name: str
    title: str | None
    email: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "title": self.title, "email": self.email}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Attendee":
        return cls(name=d["name"], title=d.get("title"), email=d["email"])


@dataclass(frozen=True)
class ParsedInvite:
    subject: str | None
    company_name: str | None
    company_domain: str | None
    attendees: tuple[Attendee, ...]
    meeting_date: str | None
    notes: str | None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "company": {"name": self.company_name, "domain": self.company_domain},
            "attendees": [a.to_dict() for a in self.attendees],
            "meetingDate": self.meeting_date,
            "notes": self.notes,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ParsedInvite":
        validate("parsed_invite", d)
        return cls(
            subject=d["subject"],
            company_name=d["company"]["name"],
            company_domain=d["company"]["domain"],
            attendees=tuple(Attendee.from_dict(a) for a in d["attendees"]),
            meeting_date=d["meetingDate"],
            notes=d["notes"],
            warnings=tuple(d.get("warnings", [])),
        )


@dataclass(frozen=True)
class CaseStudy:
    id: str
    title: str
    summary: str
    bu: str
    client_industry: str
    tags: tuple[str, ...]
    url: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CaseStudy":
        validate("case_study", d)
        return cls(
            id=d["id"], title=d["title"], summary=d["summary"], bu=d["bu"],
            client_industry=d["client_industry"], tags=tuple(d["tags"]), url=d["url"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "title": self.title, "summary": self.summary, "bu": self.bu,
            "client_industry": self.client_industry, "tags": list(self.tags), "url": self.url,
        }
