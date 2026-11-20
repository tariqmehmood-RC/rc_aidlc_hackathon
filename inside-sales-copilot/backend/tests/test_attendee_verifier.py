import json
from pathlib import Path

import pytest

from backend.src.lib import models
from backend.src.lib.profiles import Profile, load_profiles
from backend.src.services import attendee_verifier as av

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = json.loads((ROOT / "data" / "sample_invites" / "expected.json").read_text(encoding="utf-8"))
PROFILES = load_profiles()


def p(employer="Acme Corp", domain="acme.com", title="Vice President, Sales", email="a@acme.com") -> Profile:
    return Profile(email=email, name="A", employer=employer, employer_domain=domain, title=title)


def check(invited_title, profile=None, company="Acme Corp", domain="acme.com", email="a@acme.com"):
    directory = {email: profile} if profile is not None else {}
    attendee = {"name": "A", "title": invited_title, "email": email}
    return av.verify_attendee(attendee, company, domain, directory)


# --- the three sample invites match the recorded expectations ----------------------------------
@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_results_match_expected_json(name):
    exp = EXPECTED[name]
    parsed = {
        "company": exp["company"],
        "attendees": [{"name": a["name"], "title": a["invitedTitle"], "email": a["email"]} for a in exp["attendees"]],
    }
    results = av.verify_attendees(parsed, PROFILES)
    assert [(r["email"], r["status"], r["reason"]) for r in results] == \
           [(a["email"], a["status"], a["reason"]) for a in exp["attendees"]]
    for r in results:
        models.validate("attendee_check", r)


def test_all_demo_cases_occur_in_the_samples():
    seen = set()
    for exp in EXPECTED.values():
        parsed = {"company": exp["company"],
                  "attendees": [{"name": a["name"], "title": a["invitedTitle"], "email": a["email"]} for a in exp["attendees"]]}
        for r in av.verify_attendees(parsed, PROFILES):
            seen.add(r["reason"] or "verified")
    assert {"verified", "title_mismatch", "no_profile_found", "employer_mismatch", "title_missing"} <= seen


# --- every reason --------------------------------------------------------------------------------
def test_verified_needs_employer_and_title_to_match():
    r = check("Vice President, Sales", p())
    assert r["status"] == "verified" and r["reason"] is None
    assert r["profile"]["sourceUrl"] == "synthetic://profiles"


def test_employer_mismatch_shows_both_values():
    r = check("Vice President, Sales", p(employer="Globex", domain="globex.com"))
    assert (r["status"], r["reason"]) == ("unverified", "employer_mismatch")
    assert r["profile"]["employer"] == "Globex"


def test_title_mismatch_shows_both_values():
    r = check("Chief Technology Officer", p())
    assert (r["status"], r["reason"]) == ("unverified", "title_mismatch")
    assert r["invitedTitle"] == "Chief Technology Officer" and r["profile"]["title"] == "Vice President, Sales"


def test_no_profile_found():
    r = check("VP Sales", None)
    assert (r["status"], r["reason"], r["profile"]) == ("unverified", "no_profile_found", None)


@pytest.mark.parametrize("title", [None, "", "   "])
def test_title_missing(title):
    r = check(title, p())
    assert (r["status"], r["reason"]) == ("unverified", "title_missing")
    assert r["invitedTitle"] is None


def test_ambiguous_when_two_profiles_could_fit_and_none_is_picked():
    directory = {"a@acme.com": [p(), p(title="Director")]}
    r = av.verify_attendee({"name": "A", "title": "Vice President, Sales", "email": "a@acme.com"}, "Acme Corp", "acme.com", directory)
    assert (r["status"], r["reason"], r["profile"]) == ("unverified", "ambiguous", None)


def test_an_empty_profile_list_counts_as_no_profile():
    r = av.verify_attendee({"name": "A", "title": "VP", "email": "a@acme.com"}, "Acme Corp", "acme.com", {"a@acme.com": []})
    assert r["reason"] == "no_profile_found"


def test_check_order_is_title_missing_then_employer_then_title():
    # wrong employer AND wrong title: employer is reported first
    r = check("CTO", p(employer="Globex", domain="globex.com"))
    assert r["reason"] == "employer_mismatch"
    # no title AND wrong employer: title_missing is reported first
    r = check(None, p(employer="Globex", domain="globex.com"))
    assert r["reason"] == "title_missing"


# --- title matching ---------------------------------------------------------------------------------
@pytest.mark.parametrize("invited,profile_title", [
    ("VP Sales", "Vice President, Sales"),
    ("VP, Sales", "vice president sales"),
    ("Vice-President - Sales", "Vice President, Sales"),
    ("Sr. Engineer", "Senior Engineer"),
    ("Sr Director, Enterprise Architecture", "Senior Director, Enterprise Architecture"),
    ("CTO", "Chief Technology Officer"),
    ("  chief   technology officer ", "CTO"),
    ("SVP Engineering", "Senior Vice President, Engineering"),
    ("Dir. of IT", "Director of Information Technology"),
])
def test_equivalent_titles_match(invited, profile_title):
    assert check(invited, p(title=profile_title))["status"] == "verified"


@pytest.mark.parametrize("invited,profile_title", [
    ("VP Sales", "VP Marketing"),
    ("Director", "Senior Director"),
    ("CTO", "CIO"),
    ("Engineer", "Engineering Manager"),
    ("Vice President, Digital", "Vice President, Digital Commerce"),
    ("Manager", "Mgr, Operations"),
])
def test_different_titles_never_match(invited, profile_title):
    r = check(invited, p(title=profile_title))
    assert (r["status"], r["reason"]) == ("unverified", "title_mismatch")


def test_normalize_title():
    assert av.normalize_title("VP, Information Technology") == "vice president information technology"
    assert av.normalize_title(None) == ""
    assert av.normalize_title("!!!") == ""


# --- employer matching ---------------------------------------------------------------------------------
def test_employer_matches_by_normalized_name():
    assert check("VP Sales", p(employer="ACME  corp."), company="Acme Corp", domain=None)["status"] == "verified"


def test_company_suffixes_are_ignored():
    assert check("VP Sales", p(employer="Acme"), company="Acme, Inc.", domain=None)["status"] == "verified"


def test_employer_matches_by_equal_domain_even_if_names_differ():
    r = check("VP Sales", p(employer="Acme Holdings", domain="acme.com"), company="Acme Corp", domain="acme.com")
    assert r["status"] == "verified"


def test_similar_names_with_different_domains_do_not_match():
    r = check("VP Sales", p(employer="Acme Labs", domain="acmelabs.com"), company="Acme Corp", domain="acme.com")
    assert r["reason"] == "employer_mismatch"


def test_no_company_info_never_verifies():
    r = check("VP Sales", p(), company=None, domain=None)
    assert r["reason"] == "employer_mismatch"


# --- never invent anything --------------------------------------------------------------------------------
def test_output_contains_only_invite_and_profile_data():
    r = check("VP Sales", None)
    assert r["profile"] is None
    assert set(r) == {"email", "name", "invitedTitle", "status", "reason", "profile"}


def test_email_lookup_ignores_case_and_spaces_in_the_invite():
    r = av.verify_attendee({"name": "A", "title": "VP, Sales", "email": "  A@ACME.com "}, "Acme Corp", "acme.com", {"a@acme.com": p()})
    assert r["status"] == "verified" and r["email"] == "a@acme.com"
