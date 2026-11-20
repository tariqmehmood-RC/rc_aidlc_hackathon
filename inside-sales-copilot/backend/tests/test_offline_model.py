"""The offline model must be good enough to run the whole pipeline without AWS."""
import json
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from backend.src.lib import constants as c
from backend.src.lib import models
from backend.src.services import brief_writer, case_study_matcher, invite_parser, research as research_mod, rules as rules_mod
from backend.src.services.offline_model import OfflineModel
from backend.src.services.research_provider import FixtureProvider

ROOT = Path(__file__).resolve().parents[2]
INVITES = ROOT / "data" / "sample_invites"
EXPECTED = json.loads((INVITES / "expected.json").read_text(encoding="utf-8"))
RECORDED = Path(__file__).resolve().parent / "fixtures" / "research"


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_it_parses_every_sample_invite_like_the_expected_results(name):
    parsed = invite_parser.parse_invite(OfflineModel(), (INVITES / name).read_text(encoding="utf-8"))
    exp = EXPECTED[name]
    assert parsed["company"] == exp["company"]
    assert parsed["meetingDate"] == exp["meetingDate"]
    assert [(a["email"], a["name"], a["title"]) for a in parsed["attendees"]] == \
           [(a["email"], a["name"], a["invitedTitle"]) for a in exp["attendees"]]


def test_the_schema_check_rejects_an_unknown_prompt():
    with pytest.raises(AssertionError):
        OfflineModel().converse_json(model="haiku", system="", user="", max_tokens=1, schema={"type": "object"})


@pytest.fixture()
def table():
    with mock_aws():
        yield boto3.resource("dynamodb", region_name="us-east-1").create_table(
            TableName="ResearchCache", KeySchema=[{"AttributeName": "companyDomain", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "companyDomain", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_research_from_recorded_fixtures_is_valid_and_sourced(table, name):
    company = EXPECTED[name]["company"]
    svc = research_mod.ResearchService(OfflineModel(), FixtureProvider(RECORDED), table)
    result, _ = svc.get_research(company["name"], company["domain"])
    models.validate("research_result", result)
    assert result["facts"] and all(f["sourceUrls"] for f in result["facts"])
    assert result["industry"] is not None


def test_research_finds_industry_and_size_for_a_known_company(table):
    svc = research_mod.ResearchService(OfflineModel(), FixtureProvider(RECORDED), table)
    result, _ = svc.get_research("Allstate", "allstate.com")
    assert result["industry"]["value"] == "Insurance"
    assert "Glenview" in (result["headquarters"] or {}).get("value", "Glenview")


def test_the_whole_chain_runs_for_the_insurance_invite(table):
    model = OfflineModel()
    exp = EXPECTED["04-allstate.txt"]
    research, _ = research_mod.ResearchService(model, FixtureProvider(RECORDED), table).get_research("Allstate", "allstate.com")
    studies = case_study_matcher.load_case_studies()
    matches = case_study_matcher.match_case_studies(model, "ServiceNow", research, studies)
    models.validate("case_study_matches", matches)
    assert len(matches["matches"]) == 3, "the insurance invite should give 3 strong ServiceNow matches"
    assert all(m["score"] >= 60 for m in matches["matches"])
    attendees = [{"email": a["email"], "name": a["name"], "title": a["invitedTitle"]} for a in exp["attendees"]]
    written = brief_writer.write_brief(model, research=research, attendees=attendees, case_matches=matches,
                                       rules=[], meeting={"subject": "s", "meetingDate": "2026-12-10", "notes": None})
    models.validate("brief_content", written.content)
    assert 8 <= len(written.content["discoveryQuestions"]) <= 10


def test_a_budget_rule_changes_the_questions():
    model = OfflineModel()
    base = {"company": {"name": "X", "domain": "x.com", "matchConfidence": "confirmed"}, "retrievedAt": 1,
            "facts": [{"id": "f1", "text": "X is a company.", "sourceUrls": ["https://x.com/"]}],
            "industry": None, "headquarters": None, "employees": None, "revenueUsd": None,
            "sizeTier": {"tier": "Unknown", "rule": "r", "basis": {"employees": None, "revenueUsd": None, "sourceUrls": []}},
            "news": [], "painPoints": [], "sourcesFetched": []}
    out = brief_writer.write_brief(model, research=base, attendees=[], case_matches={"matches": [], "message": None},
                                   rules=[{"ruleId": "r1", "text": "Always ask about the budget cycle."}], meeting={})
    assert any("budget cycle" in q["text"] for q in out.content["discoveryQuestions"])


def test_rule_extraction_spots_a_budget_edit():
    draft = {"discoveryQuestions": [{"id": "q1", "text": "Who decides?"}]}
    final = {"discoveryQuestions": [{"id": "q1", "text": "What is your budget cycle?"}]}
    out = rules_mod.extract_rules(OfflineModel(), draft, final, [])
    assert [p["text"] for p in out] == ["Always ask about the budget cycle."]
    assert rules_mod.extract_rules(OfflineModel(), draft, draft, []) == []
