"""Checks that the sample invites, their expected results, and the profile file agree."""
import datetime
import json
import re
from pathlib import Path

import pytest

from backend.src.lib.profiles import load_profiles, lookup

ROOT = Path(__file__).resolve().parents[2]
INVITES = ROOT / "data" / "sample_invites"
EXPECTED = json.loads((INVITES / "expected.json").read_text(encoding="utf-8"))
PROFILES = load_profiles()
INVITE_FILES = sorted(INVITES.glob("*.txt"))

ALL_REASONS = {"title_mismatch", "no_profile_found", "employer_mismatch", "title_missing"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


def test_there_are_four_invites_and_each_has_expected_results():
    assert len(INVITE_FILES) == 4
    assert {f.name for f in INVITE_FILES} == set(EXPECTED)


@pytest.mark.parametrize("invite", INVITE_FILES, ids=lambda f: f.name)
def test_invite_length_is_within_the_limit(invite):
    text = invite.read_text(encoding="utf-8")
    assert 1 <= len(text) <= 10_000


@pytest.mark.parametrize("invite", INVITE_FILES, ids=lambda f: f.name)
def test_company_and_attendees_appear_in_the_invite(invite):
    text = invite.read_text(encoding="utf-8").lower()
    exp = EXPECTED[invite.name]
    assert exp["company"]["name"].lower() in text
    assert exp["company"]["domain"] in text
    for a in exp["attendees"]:
        assert a["email"] in text
        assert a["name"].lower() in text
        if a["invitedTitle"]:
            assert a["invitedTitle"].lower() in text


@pytest.mark.parametrize("invite", INVITE_FILES, ids=lambda f: f.name)
def test_meeting_date_matches_the_invite(invite):
    text = invite.read_text(encoding="utf-8")
    date = EXPECTED[invite.name]["meetingDate"]
    if date is None:
        assert "date still to be confirmed" in text.lower()
    else:
        d = datetime.date.fromisoformat(date)
        assert d > datetime.date(2026, 11, 20)  # dates are in the future relative to the event
        written_forms = {date, f"{d.strftime('%B')} {d.day}, {d.year}"}
        assert any(form.lower() in text.lower() for form in written_forms)


def test_duplicate_emails_in_the_invite_match_the_expected_merge_count():
    for invite in INVITE_FILES:
        text = invite.read_text(encoding="utf-8")
        emails = [e.lower() for e in re.findall(r"[\w.\-]+@[\w.\-]+\.\w+", text)]
        exp = EXPECTED[invite.name]
        distinct = {a["email"] for a in exp["attendees"]}
        assert set(emails) == distinct
        assert len(emails) - len(distinct) == exp["duplicateEmailsMerged"]


def test_expected_results_are_consistent_with_the_profile_file():
    """Each expected reason must be possible given the profile data (without running the verifier)."""
    for name, exp in EXPECTED.items():
        company = _norm(exp["company"]["name"])
        for a in exp["attendees"]:
            profile = lookup(PROFILES, a["email"])
            reason = a["reason"]
            if reason == "no_profile_found":
                assert profile is None, (name, a["email"])
                continue
            assert profile is not None, (name, a["email"])
            if reason == "employer_mismatch":
                assert _norm(profile.employer) != company
                assert profile.employer_domain != exp["company"]["domain"]
            else:
                assert _norm(profile.employer) == company
            if reason == "title_missing":
                assert a["invitedTitle"] is None
            if reason == "title_mismatch":
                assert a["invitedTitle"]
                assert _norm(profile.title) != _norm(a["invitedTitle"])
            if a["status"] == "verified":
                assert reason is None and a["invitedTitle"]


def test_demo_cases_are_covered_across_the_invites():
    """R4.13: at least one verified, one title mismatch, one no profile found."""
    attendees = [a for exp in EXPECTED.values() for a in exp["attendees"]]
    assert any(a["status"] == "verified" for a in attendees)
    reasons = {a["reason"] for a in attendees if a["reason"]}
    assert ALL_REASONS <= reasons


def test_invites_cover_free_mail_duplicate_and_missing_date_cases():
    texts = {f.name: f.read_text(encoding="utf-8").lower() for f in INVITE_FILES}
    assert any("@gmail.com" in t for t in texts.values())
    assert any(exp["duplicateEmailsMerged"] > 0 for exp in EXPECTED.values())
    assert any(exp["meetingDate"] is None for exp in EXPECTED.values())


def test_the_invites_name_four_different_real_public_companies():
    names = {exp["company"]["name"] for exp in EXPECTED.values()}
    assert names == {"Delta Air Lines", "Duolingo", "Marriott International", "Allstate"}


def test_every_profile_is_synthetic():
    assert all(p.source_url == "synthetic://profiles" for p in PROFILES.values())
