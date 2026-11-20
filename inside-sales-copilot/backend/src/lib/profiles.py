"""Synthetic attendee profile directory.

Profiles are made-up people used only to check invites (requirement R4). The file is keyed by
lowercase email. No real person data is ever stored here.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

SYNTHETIC_SOURCE_URL = "synthetic://profiles"
# Repo layout is the same in the Lambda asset, so this works locally and deployed.
DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "attendee_profiles.json"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")
_FIELDS = ("name", "employer", "employer_domain", "title", "source_url")


class ProfileError(ValueError):
    """The profile file is invalid."""


@dataclass(frozen=True)
class Profile:
    email: str
    name: str
    employer: str
    employer_domain: str
    title: str
    source_url: str = SYNTHETIC_SOURCE_URL


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    seen: dict[str, object] = {}
    for key, value in pairs:
        if key.lower() in {k.lower() for k in seen}:
            raise ProfileError(f"duplicate email in profile file: {key}")
        seen[key] = value
    return seen


def parse_profiles(text: str) -> dict[str, Profile]:
    try:
        raw = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise ProfileError(f"profile file is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ProfileError("profile file must be an object keyed by email")

    profiles: dict[str, Profile] = {}
    for email, entry in raw.items():
        if email != email.lower() or not _EMAIL_RE.match(email):
            raise ProfileError(f"key must be a lowercase email address: {email!r}")
        if not isinstance(entry, dict):
            raise ProfileError(f"{email}: entry must be an object")
        missing = [f for f in _FIELDS if f not in entry]
        extra = [k for k in entry if k not in _FIELDS]
        if missing or extra:
            raise ProfileError(f"{email}: missing fields {missing}, unexpected fields {extra}")
        for field in _FIELDS:
            if not isinstance(entry[field], str) or not entry[field].strip():
                raise ProfileError(f"{email}: '{field}' must be a non-empty string")
        if entry["source_url"] != SYNTHETIC_SOURCE_URL:
            raise ProfileError(f"{email}: source_url must be {SYNTHETIC_SOURCE_URL!r}")
        if not _DOMAIN_RE.match(entry["employer_domain"]):
            raise ProfileError(f"{email}: employer_domain must be a lowercase domain name")
        profiles[email] = Profile(email=email, **entry)
    return profiles


def load_profiles(path: Path | str | None = None) -> dict[str, Profile]:
    return parse_profiles(Path(path or DEFAULT_PATH).read_text(encoding="utf-8"))


def lookup(profiles: dict[str, Profile], email: str | None) -> Profile | None:
    """Find a profile by email, ignoring case and surrounding spaces. Returns None if absent."""
    if not email:
        return None
    return profiles.get(email.strip().lower())
