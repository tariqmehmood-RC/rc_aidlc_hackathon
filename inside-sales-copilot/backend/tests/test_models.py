import copy
import json
import re
from pathlib import Path

import pytest

from backend.src.lib import constants as c
from backend.src.lib import models as m

ROOT = Path(__file__).resolve().parents[2]
DESIGN = (ROOT / ".kiro" / "specs" / "inside-sales-copilot" / "design.md").read_text(encoding="utf-8")
REQUIREMENTS = (ROOT / ".kiro" / "specs" / "inside-sales-copilot" / "requirements.md").read_text(encoding="utf-8")

PARSED = {
    "subject": "Discovery call",
    "company": {"name": "Delta Air Lines", "domain": "delta.com"},
    "attendees": [{"name": "A B", "title": None, "email": "a.b@delta.com"}],
    "meetingDate": "2026-12-03",
    "notes": None,
    "warnings": ["company_domain_mismatch"],
}
RESEARCH = {
    "company": {"name": "Delta Air Lines", "domain": "delta.com", "matchConfidence": "confirmed"},
    "retrievedAt": 1790000000000,
    "facts": [{"id": "f1", "text": "An airline.", "sourceUrls": ["https://en.wikipedia.org/wiki/Delta_Air_Lines"]}],
    "industry": {"value": "Airline", "factId": "f1"},
    "headquarters": None,
    "employees": {"value": 100000, "factId": "f1"},
    "revenueUsd": None,
    "sizeTier": {
        "tier": "Enterprise",
        "rule": "More than 5,000 employees",
        "basis": {"employees": 100000, "revenueUsd": None, "sourceUrls": ["https://en.wikipedia.org/wiki/Delta_Air_Lines"]},
    },
    "news": [{"title": "T", "date": "2026-11-01", "url": "https://news.example/1"}],
    "painPoints": [{"id": "p1", "hypothesis": "Legacy IT.", "basedOnFactIds": ["f1"]}],
    "sourcesFetched": [{"url": "https://delta.com/", "status": "ok"}],
}
VERIFIED = {
    "email": "a.b@delta.com", "name": "A B", "invitedTitle": "VP", "status": "verified", "reason": None,
    "profile": {"employer": "Delta Air Lines", "title": "Vice President", "sourceUrl": "synthetic://profiles"},
}
UNVERIFIED = {
    "email": "x@delta.com", "name": "X", "invitedTitle": "CTO", "status": "unverified",
    "reason": "no_profile_found", "profile": None,
}
MATCHES = {
    "matches": [{"caseStudyId": "cs-1", "title": "T", "url": "https://www.royalcyber.com/x", "score": 80, "reason": "Fits."}],
    "message": None,
}
CONTENT = {
    "companySnapshot": [{"id": "b1", "text": "x", "sourceUrls": ["https://delta.com/"]}],
    "attendees": [{"email": "a@b.com", "name": "A", "title": "VP", "status": "verified", "reason": None}],
    "painPointHypotheses": [{"id": "h1", "text": "x", "basedOnFactIds": ["f1"], "sourceUrls": ["https://delta.com/"]}],
    "agenda": [{"id": "a1", "minutes": 30, "topic": "All", "note": "n"}],
    "discoveryQuestions": [{"id": "q1", "text": "Why?"}],
    "caseStudies": [{"caseStudyId": "cs-1", "title": "T", "url": "https://www.royalcyber.com/x", "reason": "r"}],
    "sources": [{"url": "https://delta.com/", "label": "Delta"}],
}
CASE_STUDY = {
    "id": "cs-1", "title": "T", "summary": "S", "bu": "AWS", "client_industry": "Retail",
    "tags": ["a"], "url": "https://www.royalcyber.com/x",
}
QUEUE = {"type": "parse", "briefId": "b", "jobId": "j"}

GOOD = {
    "parsed_invite": PARSED, "research_result": RESEARCH, "attendee_check": VERIFIED,
    "case_study_matches": MATCHES, "brief_content": CONTENT, "case_study": CASE_STUDY, "queue_message": QUEUE,
}


def test_every_schema_has_a_good_sample():
    assert set(GOOD) == set(m.SCHEMAS)


@pytest.mark.parametrize("name", sorted(GOOD))
def test_good_samples_validate(name):
    m.validate(name, GOOD[name])
    assert m.is_valid(name, GOOD[name])


def test_second_attendee_sample_validates():
    m.validate("attendee_check", UNVERIFIED)


@pytest.mark.parametrize("name", sorted(GOOD))
def test_extra_fields_are_rejected(name):
    bad = copy.deepcopy(GOOD[name])
    bad["surprise"] = 1
    with pytest.raises(m.ModelValidationError):
        m.validate(name, bad)


@pytest.mark.parametrize("name", sorted(GOOD))
def test_missing_required_fields_are_rejected(name):
    required = m.SCHEMAS[name]["required"]
    for key in required:
        bad = copy.deepcopy(GOOD[name])
        del bad[key]
        with pytest.raises(m.ModelValidationError):
            m.validate(name, bad)


@pytest.mark.parametrize("name,mutate", [
    ("parsed_invite", lambda d: d.update(meetingDate="12/03/2026")),
    ("parsed_invite", lambda d: d.update(warnings=["made_up"])),
    ("research_result", lambda d: d["sizeTier"].update(tier="Huge")),
    ("research_result", lambda d: d.update(news=[d["news"][0]] * 4)),
    ("research_result", lambda d: d["facts"][0].update(sourceUrls=[])),
    ("research_result", lambda d: d["painPoints"][0].update(basedOnFactIds=[])),
    ("attendee_check", lambda d: d.update(reason="because")),
    ("attendee_check", lambda d: d["profile"].update(sourceUrl="https://linkedin.com/in/x")),
    ("attendee_check", lambda d: d.update(status="maybe")),
    ("case_study_matches", lambda d: d["matches"][0].update(score=59)),
    ("case_study_matches", lambda d: d.update(matches=d["matches"] * 4)),
    ("brief_content", lambda d: d["agenda"][0].update(minutes=31)),
    ("brief_content", lambda d: d["companySnapshot"][0].update(sourceUrls=[])),
    ("case_study", lambda d: d.update(bu="Oracle")),
    ("case_study", lambda d: d.update(url="http://www.royalcyber.com/x")),
    ("queue_message", lambda d: d.update(type="delete_everything")),
])
def test_invalid_shapes_are_rejected(name, mutate):
    bad = copy.deepcopy(GOOD[name])
    mutate(bad)
    with pytest.raises(m.ModelValidationError):
        m.validate(name, bad)


def test_verified_attendee_cannot_have_a_reason_and_unverified_must_have_one():
    bad = copy.deepcopy(VERIFIED)
    bad["reason"] = "title_mismatch"
    assert not m.is_valid("attendee_check", bad)
    bad = copy.deepcopy(UNVERIFIED)
    bad["reason"] = None
    assert not m.is_valid("attendee_check", bad)


def test_validation_error_does_not_echo_values():
    bad = copy.deepcopy(PARSED)
    bad["attendees"][0]["email"] = "secret.person@example.com" * 20
    with pytest.raises(m.ModelValidationError) as err:
        m.validate("parsed_invite", bad)
    assert "secret.person" not in str(err.value)


def test_parsed_invite_round_trip():
    parsed = m.ParsedInvite.from_dict(PARSED)
    assert parsed.company_domain == "delta.com"
    assert parsed.attendees[0].title is None
    assert parsed.to_dict() == PARSED


def test_case_study_round_trip():
    cs = m.CaseStudy.from_dict(CASE_STUDY)
    assert cs.to_dict() == CASE_STUDY
    with pytest.raises(m.ModelValidationError):
        m.CaseStudy.from_dict({**CASE_STUDY, "bu": "Oracle"})


def test_real_case_study_file_matches_the_schema():
    for item in json.loads((ROOT / "data" / "case_studies.json").read_text(encoding="utf-8")):
        m.validate("case_study", item)


# --- constants match the design and requirements ---------------------------------------------
def test_statuses_and_steps_match_the_design():
    assert c.STATUSES == ("queued", "processing", "awaiting_confirmation", "ready", "approved", "failed")
    assert c.STEPS == ("Parsing", "Researching", "Checking attendees", "Matching case studies", "Writing brief")
    for name in c.STATUSES:
        assert f"`{name}`" in DESIGN, name
    for step in c.STEPS:
        assert step in DESIGN, step
    assert set(c.JOB_TYPES) == {"parse", "pipeline", "extract_rules"}


def test_business_units_and_tiers_match_the_requirements():
    assert c.BUSINESS_UNITS == ("AWS", "ServiceNow", "Salesforce", "Data & AI")
    for tier in ("Enterprise", "Mid-market", "SMB", "Boutique", "Unknown"):
        assert tier in c.SIZE_TIERS and tier in REQUIREMENTS


def test_limits_match_the_requirements():
    assert c.MAX_INVITE_CHARS == 10_000 and "10,000" in REQUIREMENTS
    assert c.MAX_ATTENDEES == 20
    assert (c.QUESTIONS_MIN, c.QUESTIONS_MAX) == (8, 10)
    assert c.AGENDA_TOTAL_MINUTES == 30
    assert c.CASE_STUDY_MIN_SCORE == 60 and c.MAX_CASE_STUDIES == 3
    assert c.STUCK_SECONDS == 120 and c.RESEARCH_CACHE_DAYS == 7 and c.BRIEF_TTL_DAYS == 30
    assert c.MAX_RULES_APPLIED == 10 and c.MAX_RULE_PROPOSALS == 3
    assert c.BEDROCK_MAX_REQUESTS_PER_SECOND == 1


def test_tier_thresholds():
    assert (c.ENTERPRISE_EMPLOYEES_ABOVE, c.ENTERPRISE_REVENUE_USD_ABOVE) == (5000, 1_000_000_000)
    assert (c.MID_MARKET_EMPLOYEES_MIN, c.SMB_EMPLOYEES_MIN) == (500, 50)


def test_every_prompt_has_a_max_tokens_value():
    assert c.MAX_TOKENS == {"parse": 1500, "research": 2500, "score": 1500, "write": 4000, "rules": 800}


def test_free_mail_domains_are_lowercase_and_include_the_common_ones():
    assert all(d == d.lower() and "." in d for d in c.FREE_MAIL_DOMAINS)
    assert {"gmail.com", "outlook.com", "yahoo.com", "hotmail.com", "icloud.com"} <= c.FREE_MAIL_DOMAINS
    assert "delta.com" not in c.FREE_MAIL_DOMAINS


def test_title_abbreviations():
    assert c.TITLE_ABBREVIATIONS["vp"] == "vice president"
    assert c.TITLE_ABBREVIATIONS["cto"] == "chief technology officer"
    assert c.TITLE_ABBREVIATIONS["sr"] == "senior"
    for key, expansion in c.TITLE_ABBREVIATIONS.items():
        assert key == key.lower() and re.fullmatch(r"[a-z]+", key)
        assert expansion == expansion.lower() and key not in expansion.split()


def test_model_ids_are_read_from_the_environment_only():
    assert c.ENV_MODEL_HAIKU == "BEDROCK_MODEL_HAIKU" and c.ENV_MODEL_SONNET == "BEDROCK_MODEL_SONNET"
    source = (ROOT / "backend" / "src" / "lib" / "constants.py").read_text(encoding="utf-8")
    assert "anthropic." not in source
