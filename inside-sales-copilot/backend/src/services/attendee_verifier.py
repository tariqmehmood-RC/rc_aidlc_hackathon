"""Attendee verification (requirements R4, design 8.4). Deterministic: no model, no fuzzy match.

An attendee is "verified" only when a synthetic profile exists AND its employer matches the
invite company AND its title matches the invited title. Anything else is "unverified" with a
reason. Nothing is ever guessed or filled in.
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from ..lib import constants as c
from ..lib.profiles import Profile

_COMPANY_SUFFIXES = {"inc", "incorporated", "corp", "corporation", "llc", "ltd", "limited", "co",
                     "company", "plc", "gmbh"}
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_title(title: str | None) -> str:
    """Lowercase, drop punctuation, expand abbreviations (VP -> vice president)."""
    if not title:
        return ""
    tokens = _NON_ALNUM.sub(" ", title.lower()).split()
    expanded: list[str] = []
    for token in tokens:
        expanded.extend(c.TITLE_ABBREVIATIONS.get(token, token).split())
    return " ".join(expanded)


def normalize_company(name: str | None) -> str:
    if not name:
        return ""
    tokens = _NON_ALNUM.sub(" ", name.lower()).split()
    while len(tokens) > 1 and tokens[-1] in _COMPANY_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def employer_matches(company_name: str | None, company_domain: str | None, profile: Profile) -> bool:
    if company_name and normalize_company(company_name) == normalize_company(profile.employer):
        return True
    return bool(company_domain) and company_domain.strip().lower() == profile.employer_domain


def _profile_summary(profile: Profile) -> dict[str, str]:
    return {"employer": profile.employer, "title": profile.title, "sourceUrl": profile.source_url}


def verify_attendee(
    attendee: Mapping[str, Any],
    company_name: str | None,
    company_domain: str | None,
    directory: Mapping[str, Profile | Sequence[Profile]],
) -> dict[str, Any]:
    """Return one `attendee_check` object (design 5.5)."""
    email = (attendee.get("email") or "").strip().lower()
    invited_title = (attendee.get("title") or "").strip() or None
    result: dict[str, Any] = {
        "email": email,
        "name": attendee.get("name") or "",
        "invitedTitle": invited_title,
        "status": c.VERDICT_UNVERIFIED,
        "reason": None,
        "profile": None,
    }

    found = directory.get(email)
    if found is None:
        result["reason"] = "no_profile_found"
        return result
    if isinstance(found, Sequence) and not isinstance(found, Profile):
        if len(found) > 1:
            result["reason"] = "ambiguous"  # never pick one
            return result
        if not found:
            result["reason"] = "no_profile_found"
            return result
        found = found[0]
    profile: Profile = found
    result["profile"] = _profile_summary(profile)

    if invited_title is None:
        result["reason"] = "title_missing"
    elif not employer_matches(company_name, company_domain, profile):
        result["reason"] = "employer_mismatch"
    elif normalize_title(invited_title) != normalize_title(profile.title):
        result["reason"] = "title_mismatch"
    else:
        result["status"] = c.VERDICT_VERIFIED
    return result


def verify_attendees(parsed_invite: Mapping[str, Any], directory: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Check every attendee of a confirmed invite, in invite order."""
    company = parsed_invite["company"]
    return [
        verify_attendee(a, company.get("name"), company.get("domain"), directory)
        for a in parsed_invite["attendees"]
    ]
