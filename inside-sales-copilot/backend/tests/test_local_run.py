import io
import json
from pathlib import Path

import pytest

from backend import local_run

INVITES = Path(__file__).resolve().parents[2] / "data" / "sample_invites"
EXPECTED = json.loads((INVITES / "expected.json").read_text(encoding="utf-8"))
SECTIONS = ["1. COMPANY SNAPSHOT", "2. ATTENDEES", "3. PAIN-POINT HYPOTHESES", "4. AGENDA (30 min)",
            "5. DISCOVERY QUESTIONS", "6. CASE STUDIES TO MENTION", "7. SOURCES"]


def run(name, bu, **kw):
    out = io.StringIO()
    result = local_run.run(str(INVITES / name), bu, fake=True, fixtures=True, out=out, **kw)
    return result, out.getvalue()


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_every_sample_invite_finishes_ready_and_prints_the_seven_sections(name):
    result, text = run(name, "ServiceNow")
    assert result["status"] == "ready", text
    positions = [text.index(s) for s in SECTIONS]
    assert positions == sorted(positions)
    assert "total: 30 min" in text


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_attendee_statuses_match_the_expected_results(name):
    result, text = run(name, "AWS")
    got = [(a["email"], a["status"], a["reason"]) for a in result["brief"]["content"]["attendees"]]
    assert got == [(a["email"], a["status"], a["reason"]) for a in EXPECTED[name]["attendees"]]
    for a in EXPECTED[name]["attendees"]:
        flag = "VERIFIED  " if a["status"] == "verified" else "UNVERIFIED"
        assert f"[{flag}] {a['name']}" in text


def test_aws_and_servicenow_get_different_case_studies():
    from backend.src.services.case_study_matcher import load_case_studies

    bu_of = {s.id: s.bu for s in load_case_studies()}
    aws, _ = run("01-delta-air-lines.txt", "AWS")
    snow, _ = run("01-delta-air-lines.txt", "ServiceNow")
    assert aws["candidateIds"] and snow["candidateIds"]
    assert {bu_of[i] for i in aws["candidateIds"]} == {"AWS"}
    assert {bu_of[i] for i in snow["candidateIds"]} == {"ServiceNow"}
    shown_aws = {c["caseStudyId"] for c in aws["brief"]["content"]["caseStudies"]}
    shown_snow = {c["caseStudyId"] for c in snow["brief"]["content"]["caseStudies"]}
    assert shown_aws.isdisjoint(shown_snow)


def test_the_insurance_invite_gives_three_strong_servicenow_matches():
    result, text = run("04-allstate.txt", "ServiceNow")
    assert len(result["brief"]["content"]["caseStudies"]) == 3
    assert result["scoredAtLeast60"] >= 3
    assert "Case studies scoring 60 or more:" in text


def test_timing_and_usage_are_reported():
    result, text = run("02-duolingo.txt", "Data & AI")
    assert result["timing"]["totalSeconds"] >= 0
    assert [name for name, _ in result["steps"]] == ["Researching", "Checking attendees", "Matching case studies", "Writing brief"]
    assert "Time: parse" in text and "Bedrock haiku:" in text and "Bedrock sonnet:" in text


def test_a_saved_rule_is_applied():
    result, text = run("04-allstate.txt", "ServiceNow", rules=["Always ask about the budget cycle."])
    assert "Rules applied: Always ask about the budget cycle." in text
    assert any("budget cycle" in q["text"] for q in result["brief"]["content"]["discoveryQuestions"])


def test_every_url_in_the_printed_brief_was_fetched_or_is_a_case_study():
    result, _ = run("04-allstate.txt", "ServiceNow")
    research = result["brief"]["research"]
    fetched = {u for f in research["facts"] for u in f["sourceUrls"]} | {n["url"] for n in research["news"]}
    for s in result["brief"]["content"]["sources"]:
        assert s["url"] in fetched or s["url"].startswith(("https://royalcyber.com/", "https://www.royalcyber.com/"))


def test_main_returns_0_and_rejects_a_bad_bu(capsys):
    assert local_run.main([str(INVITES / "04-allstate.txt"), "--bu", "ServiceNow", "--fake-bedrock", "--fixtures"]) == 0
    with pytest.raises(SystemExit):
        local_run.main([str(INVITES / "04-allstate.txt"), "--bu", "Oracle", "--fake-bedrock"])


def test_the_research_user_agent_default_is_set(monkeypatch):
    monkeypatch.delenv("RESEARCH_USER_AGENT", raising=False)
    local_run._configure_env(fake=True)
    import os

    assert "@" not in os.environ["RESEARCH_USER_AGENT"]


def test_an_env_var_overrides_the_user_agent(monkeypatch):
    monkeypatch.setenv("RESEARCH_USER_AGENT", "Custom/1.0")
    local_run._configure_env(fake=True)
    import os

    assert os.environ["RESEARCH_USER_AGENT"] == "Custom/1.0"
