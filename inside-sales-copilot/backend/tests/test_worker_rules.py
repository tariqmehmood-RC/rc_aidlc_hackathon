from backend.src.lib import constants as c
from backend.src.lib.bedrock_client import BedrockUnavailable
from backend.src.services import pipeline
from backend.src.services import rules as rules_mod
from backend.src.services.offline_model import OfflineModel
from backend.tests.env_helpers import backend, invite_text
from backend.tests.test_worker_pipeline import Flaky, msg, parse_and_confirm


def ready_brief(env):
    brief_id, job = parse_and_confirm(env)
    assert pipeline.handle_message(msg(brief_id, job, "pipeline"), env.deps) == "ready"
    return brief_id


def approve(env, brief_id, edit=None):
    brief = env.store.get(brief_id)
    content = brief["content"]
    if edit:
        content = edit(content)
    return env.store.approve(brief_id, content)


def add_budget_question(content):
    content["discoveryQuestions"][0]["text"] = "What is your budget cycle, and who approves spend?"
    return content


def test_an_edited_brief_gets_rule_proposals():
    with backend() as env:
        brief_id = ready_brief(env)
        job = approve(env, brief_id, add_budget_question)
        assert pipeline.handle_message(msg(brief_id, job, "extract_rules"), env.deps) == "rules_ready"
        got = env.store.get(brief_id)
        assert got["status"] == "approved" and got["rulesStatus"] == "ready"
        assert [p["text"] for p in got["ruleProposals"]] == ["Always ask about the budget cycle."]
        assert 1 <= len(got["ruleProposals"]) <= 3


def test_identical_text_sets_none_without_a_bedrock_call():
    with backend() as env:
        brief_id = ready_brief(env)
        job = approve(env, brief_id)
        calls = len(env.model.calls)
        assert pipeline.handle_message(msg(brief_id, job, "extract_rules"), env.deps) == "rules_none"
        assert len(env.model.calls) == calls
        got = env.store.get(brief_id)
        assert got["rulesStatus"] == "none" and got["ruleProposals"] == []


def test_a_bedrock_failure_sets_failed_and_the_brief_stays_approved():
    flaky = Flaky(OfflineModel(), rules_mod.P5_SCHEMA, BedrockUnavailable("down"))
    with backend(model=flaky) as env:
        brief_id = ready_brief(env)
        job = approve(env, brief_id, add_budget_question)
        assert pipeline.handle_message(msg(brief_id, job, "extract_rules"), env.deps) == "rules_failed"
        got = env.store.get(brief_id)
        assert got["status"] == "approved" and got["rulesStatus"] == "failed"


def test_saved_rules_are_not_proposed_again():
    with backend() as env:
        env.deps.rules.add("alice", "Always ask about the budget cycle.")
        brief_id = ready_brief(env)
        job = approve(env, brief_id, add_budget_question)
        assert pipeline.handle_message(msg(brief_id, job, "extract_rules"), env.deps) == "rules_none"


def test_a_duplicate_rules_message_does_nothing():
    with backend() as env:
        brief_id = ready_brief(env)
        job = approve(env, brief_id, add_budget_question)
        pipeline.handle_message(msg(brief_id, job, "extract_rules"), env.deps)
        calls = len(env.model.calls)
        assert pipeline.handle_message(msg(brief_id, job, "extract_rules"), env.deps) == "duplicate"
        assert len(env.model.calls) == calls


def test_a_rules_message_for_a_brief_that_is_not_approved_is_stale():
    with backend() as env:
        brief_id = ready_brief(env)
        job = env.store.get(brief_id)["currentJobId"]
        assert pipeline.handle_message(msg(brief_id, job, "extract_rules"), env.deps) == "duplicate"
        assert env.store.get(brief_id)["status"] == c.STATUS_READY
