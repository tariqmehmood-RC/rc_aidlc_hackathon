"""Invite parsing (prompt P1) and confirmation checks (requirements R2).

The model only extracts text that is in the invite. Everything else here is plain code:
cleaning, merging duplicate emails, warnings, and the rules the SE's confirmation must meet.
"""
from __future__ import annotations

import copy
import datetime
import re
from dataclasses import dataclass, field
from typing import Any

from ..lib import constants as c
from ..lib import models

P1_SYSTEM = (
    "Extract meeting details from the invite text. Copy values exactly as written. "
    "Do not infer an attendee's title or employer from anything but the invite. "
    "If the company name is not stated, return null for it. Put an email's domain in "
    "company.domain only if it is a company domain, not a free mail domain, and it is used by "
    "most attendees from the prospect. Use the date format YYYY-MM-DD, or null when no date "
    "is given. Do not return a warnings field."
)

# The model's reply has no "warnings": code adds those.
P1_SCHEMA: dict[str, Any] = copy.deepcopy(models.SCHEMAS["parsed_invite"])
P1_SCHEMA["properties"].pop("warnings")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")
_GENERIC_LABELS = {"co", "com", "org", "net", "ac", "gov", "edu", "www"}
_CLOSING_TAG_RE = re.compile(r"</\s*invite\s*>", re.IGNORECASE)


# --- helpers ---------------------------------------------------------------------------------
def wrap_invite(text: str) -> str:
    """Put the invite inside <invite> tags. A closing tag inside the text is neutralized so the
    text cannot end the data block early and pose as instructions."""
    safe = _CLOSING_TAG_RE.sub("&lt;/invite&gt;", text)
    return f"<invite>{safe}</invite>"


def clean_domain(value: str | None) -> str | None:
    if value is None:
        return None
    d = value.strip().lower()
    d = re.sub(r"^[a-z]+://", "", d)
    d = d.split("/")[0].split("?")[0].split("#")[0]
    d = d.rstrip(".")
    if d.startswith("www."):
        d = d[4:]
    return d or None


def email_domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].lower()


def is_free_mail(domain: str | None) -> bool:
    return bool(domain) and domain in c.FREE_MAIL_DOMAINS


def same_domain(a: str, b: str) -> bool:
    return a == b or a.endswith("." + b) or b.endswith("." + a)


def _name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _domain_labels(domain: str) -> list[str]:
    return [lbl for lbl in domain.split(".")[:-1] if lbl not in _GENERIC_LABELS]


def _name_matches_domain(name: str, domain: str) -> bool:
    key = _name_key(name)
    return any(len(lbl) >= 2 and (lbl in key or (len(key) >= 3 and key in lbl))
               for lbl in _domain_labels(domain))


def _valid_date(value: str) -> bool:
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _strip_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


# --- normalizing and warnings ----------------------------------------------------------------
def normalize_invite(parsed: dict[str, Any], drop_invalid_domain: bool = False) -> tuple[dict[str, Any], int]:
    """Clean a parsed invite. Returns (cleaned copy, number of duplicate attendees merged)."""
    out = copy.deepcopy(parsed)
    out.pop("warnings", None)
    out["subject"] = _strip_or_none(out.get("subject"))
    out["notes"] = _strip_or_none(out.get("notes"))
    company = out.get("company") or {}
    name = _strip_or_none(company.get("name"))
    domain = clean_domain(company.get("domain"))
    if drop_invalid_domain and domain and (not _DOMAIN_RE.match(domain) or is_free_mail(domain)):
        domain = None
    out["company"] = {"name": name, "domain": domain}

    merged = 0
    by_email: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for a in out.get("attendees") or []:
        email = (a.get("email") or "").strip().lower()
        entry = {"name": (a.get("name") or "").strip(), "title": _strip_or_none(a.get("title")), "email": email}
        if email in by_email:
            merged += 1
            kept = by_email[email]
            if not kept["title"] and entry["title"]:
                kept["title"] = entry["title"]
            if not kept["name"] and entry["name"]:
                kept["name"] = entry["name"]
            continue
        by_email[email] = entry
        order.append(email)
    out["attendees"] = [by_email[e] for e in order]
    return out, merged


def compute_warnings(parsed: dict[str, Any]) -> list[str]:
    """Warnings are always recomputed from the data. A client-sent `warnings` list is ignored."""
    warnings: list[str] = []
    domains = [email_domain(a["email"]) for a in parsed["attendees"] if _EMAIL_RE.match(a["email"])]
    non_free = sorted({d for d in domains if not is_free_mail(d)})
    if domains and not non_free:
        warnings.append("only_free_email_domains")

    name, domain = parsed["company"]["name"], parsed["company"]["domain"]
    if non_free:
        if domain and not is_free_mail(domain):
            mismatch = not any(same_domain(domain, d) for d in non_free)
        elif name:
            mismatch = not any(_name_matches_domain(name, d) for d in non_free)
        else:
            mismatch = False
        if mismatch:
            warnings.append("company_domain_mismatch")
    return warnings


def names_a_company(parsed: dict[str, Any]) -> bool:
    name, domain = parsed["company"]["name"], parsed["company"]["domain"]
    return bool(name) or bool(domain and not is_free_mail(domain))


# --- parsing ---------------------------------------------------------------------------------
def parse_invite(bedrock, invite_text: str) -> dict[str, Any]:
    """Run prompt P1 (Haiku) and return a cleaned parsed invite with warnings."""
    raw = bedrock.converse_json(
        model=c.MODEL_HAIKU,
        system=P1_SYSTEM,
        user=wrap_invite(invite_text),
        max_tokens=c.MAX_TOKENS["parse"],
        schema=P1_SCHEMA,
    )
    parsed, _merged = normalize_invite(raw, drop_invalid_domain=True)
    parsed["warnings"] = compute_warnings(parsed)
    models.validate("parsed_invite", parsed)
    return parsed


# --- confirmation ----------------------------------------------------------------------------
@dataclass
class ConfirmationResult:
    ok: bool
    errors: list[dict[str, str]] = field(default_factory=list)
    normalized: dict[str, Any] | None = None


def _error(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def validate_confirmation(parsed: Any, company_confirmed: bool) -> ConfirmationResult:
    """Check what the SE confirmed (R2.7 to R2.13). Never calls Bedrock."""
    if not isinstance(parsed, dict) or not isinstance(parsed.get("attendees"), list):
        return ConfirmationResult(False, [_error("INVALID_BODY", "The parsed invite is not valid.")])

    # Count before the schema check, so 21 to 40 attendees get the specific message.
    try:
        probe, _ = normalize_invite({**parsed, "attendees": [a for a in parsed["attendees"] if isinstance(a, dict)]})
    except (AttributeError, TypeError):
        return ConfirmationResult(False, [_error("INVALID_BODY", "The parsed invite is not valid.")])
    if len(probe["attendees"]) > c.MAX_ATTENDEES:
        return ConfirmationResult(False, [_error(
            "TOO_MANY_ATTENDEES", f"An invite can list at most {c.MAX_ATTENDEES} attendees.")])

    candidate = {k: v for k, v in parsed.items() if k != "warnings"}
    try:
        models.validate("parsed_invite", candidate)
    except models.ModelValidationError:
        return ConfirmationResult(False, [_error("INVALID_BODY", "The parsed invite is not valid.")])

    normalized, _ = normalize_invite(parsed)
    errors: list[dict[str, str]] = []

    domain = normalized["company"]["domain"]
    if domain and not _DOMAIN_RE.match(domain):
        errors.append(_error("INVALID_DOMAIN", "The company domain is not a valid domain name."))
    for a in normalized["attendees"]:
        if not _EMAIL_RE.match(a["email"]):
            errors.append(_error("INVALID_EMAIL", "An attendee email address is not valid."))
            break
    if normalized["meetingDate"] is not None and not _valid_date(normalized["meetingDate"]):
        errors.append(_error("INVALID_DATE", "The meeting date must be a real date (YYYY-MM-DD)."))
    if not names_a_company(normalized):
        errors.append(_error("COMPANY_REQUIRED",
                             "Add a company name or a company email domain (a free mail domain does not count)."))

    warnings = compute_warnings(normalized)
    normalized["warnings"] = warnings
    if "company_domain_mismatch" in warnings and not company_confirmed and names_a_company(normalized):
        errors.append(_error("COMPANY_DOMAIN_MISMATCH",
                             "The company name and the attendees' email domains do not match. "
                             "Confirm which company is correct."))
    if errors:
        return ConfirmationResult(False, errors)
    return ConfirmationResult(True, [], normalized)
