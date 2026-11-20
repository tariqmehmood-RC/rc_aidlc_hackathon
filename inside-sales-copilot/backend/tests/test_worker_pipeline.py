import json

import pytest

from backend.src.lib import constants as c
from backend.src.lib import models
from backend.src.lib.bedrock_client import BedrockUnavailable, InvalidModelOutput
from backend.src.services import pipeline
from backend.src.services.offline_model import OfflineModel
from backend.src.services.research_provider import RawResearch
from backend.tests.env_helpers import INVITES, backend, invite_text

EXPECTED = json.loads((INVITES / "expected.json").read_text(encoding="utf-8"))


def msg(brief_id, job_id, kind):
    return {"type": kind, "briefId": brief_id, "jobId": job_id}


def parse_and_confirm(env, invite="04-allstate.txt", bu="ServiceNow", user="alice"):
    brief, job = env.store.create(user, bu, invite_text(invite))
    assert pipeline.handle_message(msg(brief["briefId"], job, "parse"), env.deps) == "parsed"
    parsed = env.store.get(brief["briefId"])["parsedInvite"]
    job2 = env.store.requeue(brief["briefId"], c.STATUS_AWAITING_CONFIRMATION, {"confirmedInvite": parsed})
    return brief["briefId"], job2


class Flaky:
    """Wraps a model and fails on the n-th call for one prompt schema."""

    def __init__(self, model, fail_schema, exc, times=1):
        self.model, self.fail_schema, self.exc, self.left = model, fail_schema, exc, times
        self.calls = 0

    def converse_json(self, **kw):
        self.calls += 1
        if kw["schema"] is self.fail_schema and self.left > 0:
            self.left -= 1
            raise self.exc
        return self.model.converse_json(**kw)


# --- happy path ------------------------------------------------------------------------------------
def test_parse_job_moves_the_brief_to_awaiting_confirmation():
    with backend() as env:
        brief, job = env.store.create("alice", "ServiceNow", invite_text("01-delta-air-lines.txt"))
        assert pipeline.handle_message(msg(brief["briefId"], job, "parse"), env.deps) == "parsed"
        got = env.store.get(brief["briefId"])
        assert got["status"] == "awaiting_confirmation" and got["stepsCompleted"] == ["Parsing"]
        assert got["parsedInvite"]["company"] == EXPECTED["01-delta-air-lines.txt"]["company"]


def test_pipeline_runs_every_step_in_order_and_ends_ready():
    with backend() as env:
        brief_id, job = parse_and_confirm(env)
        steps_seen = []
        real_set_step = env.store.set_step
        env.store.set_step = lambda b, j, s: steps_seen.append(s) or real_set_step(b, j, s)
        assert pipeline.handle_message(msg(brief_id, job, "pipeline"), env.deps) == "ready"
        got = env.store.get(brief_id)
        assert steps_seen == ["Researching", "Checking attendees", "Matching case studies", "Writing brief"]
        assert got["status"] == "ready"
        assert got["stepsCompleted"] == ["Parsing", "Researching", "Checking attendees", "Matching case studies", "Writing brief"]
        assert got["draft"] == got["content"] and got["version"] == 0
        models.validate("brief_content", got["content"])
        models.validate("research_result", got["research"])


def test_the_insurance_invite_gets_three_servicenow_case_studies_and_the_expected_attendee_flags():
    with backend() as env:
        brief_id, job = parse_and_confirm(env)
        pipeline.handle_message(msg(brief_id, job, "pipeline"), env.deps)
        got = env.store.get(brief_id)
        assert len(got["caseStudyMatches"]["matches"]) == 3
        assert all(m["score"] >= 60 for m in got["caseStudyMatches"]["matches"])
        by_id = {s.id: s for s in env.deps.studies}
        assert all(by_id[m["caseStudyId"]].bu == "ServiceNow" for m in got["caseStudyMatches"]["matches"])
        flags = [(a["email"], a["status"], a["reason"]) for a in got["attendeeChecks"]]
        assert flags == [(a["email"], a["status"], a["reason"]) for a in EXPECTED["04-allstate.txt"]["attendees"]]


def test_the_bu_used_is_the_one_stored_on_the_brief():
    with backend() as env:
        brief_id, job = parse_and_confirm(env, bu="AWS")
        pipeline.handle_message(msg(brief_id, job, "pipeline"), env.deps)
        by_id = {s.id: s for s in env.deps.studies}
        matches = env.store.get(brief_id)["caseStudyMatches"]["matches"]
        assert all(by_id[m["caseStudyId"]].bu == "AWS" for m in matches)


def test_saved_rules_are_applied_to_the_next_brief():
    with backend() as env:
        env.deps.rules.add("alice", "Always ask about the budget cycle.")
        brief_id, job = parse_and_confirm(env)
        pipeline.handle_message(msg(brief_id, job, "pipeline"), env.deps)
        got = env.store.get(brief_id)
        assert [r["text"] for r in got["rulesApplied"]] == ["Always ask about the budget cycle."]
        assert any("budget cycle" in q["text"] for q in got["content"]["discoveryQuestions"])


def test_brief_generated_metric_is_counted():
    class Counter:
        def __init__(self):
            self.names = []

        def incr(self, name, count=1):
            self.names.append(name)

    with backend() as env:
        env.deps.metrics = Counter()
        brief_id, job = parse_and_confirm(env)
        pipeline.handle_message(msg(brief_id, job, "pipeline"), env.deps)
        assert env.deps.metrics.names == ["BriefGenerated"]


# --- duplicates and stale messages -------------------------------------------------------------------------
def test_a_redelivered_message_does_not_run_the_steps_twice():
    with backend() as env:
        brief_id, job = parse_and_confirm(env)
        assert pipeline.handle_message(msg(brief_id, job, "pipeline"), env.deps) == "ready"
        calls = len(env.model.calls)
        assert pipeline.handle_message(msg(brief_id, job, "pipeline"), env.deps) == "duplicate"
        assert len(env.model.calls) == calls


def test_a_stale_job_is_ignored():
    with backend() as env:
        brief, job = env.store.create("alice", "AWS", invite_text("01-delta-air-lines.txt"))
        assert pipeline.handle_message(msg(brief["briefId"], "old-job", "parse"), env.deps) == "stale"
        assert env.store.get(brief["briefId"])["status"] == "queued"
        assert env.model.calls == []


@pytest.mark.parametrize("body", [None, "text", {}, {"type": "parse"}, {"type": "drop_table", "briefId": "b", "jobId": "j"}])
def test_invalid_messages_are_dropped(body):
    with backend() as env:
        assert pipeline.handle_message(body, env.deps) == "invalid"


def test_a_missing_brief_is_stale():
    with backend() as env:
        assert pipeline.handle_message(msg("nope", "j", "parse"), env.deps) == "stale"


def test_a_job_that_loses_ownership_midway_stops_without_writing():
    with backend() as env:
        brief_id, job = parse_and_confirm(env)
        real = env.store.complete_step

        def steal(b, j, step, fields=None):
            env.clock.advance(500)
            env.store.expire_if_stuck(env.store.get(b))      # the stuck check fails the brief first
            return real(b, j, step, fields)

        env.store.complete_step = steal
        assert pipeline.handle_message(msg(brief_id, job, "pipeline"), env.deps) == "superseded"
        got = env.store.get(brief_id)
        assert got["status"] == "failed" and got["error"]["code"] == "STUCK"
        assert "research" not in got


# --- handled errors ---------------------------------------------------------------------------------------
def test_parse_failure_is_reported_and_the_text_is_kept():
    from backend.src.services import invite_parser

    with backend(model=Flaky(OfflineModel(), invite_parser.P1_SCHEMA, InvalidModelOutput("x"))) as env:
        brief, job = env.store.create("alice", "AWS", "Some invite")
        assert pipeline.handle_message(msg(brief["briefId"], job, "parse"), env.deps) == "failed"
        got = env.store.get(brief["briefId"])
        assert got["error"]["code"] == "PARSE_FAILED" and got["error"]["step"] == "Parsing"
        assert got["inviteText"] == "Some invite"


def test_no_public_info_fails_the_research_step():
    class Empty:
        def research(self, name, domain):
            return RawResearch()

    with backend(provider=Empty()) as env:
        brief_id, job = parse_and_confirm(env)
        assert pipeline.handle_message(msg(brief_id, job, "pipeline"), env.deps) == "failed"
        assert env.store.get(brief_id)["error"] == {"code": "NO_PUBLIC_INFO", "step": "Researching", "message": pipeline.MESSAGES["NO_PUBLIC_INFO"]}


@pytest.mark.parametrize("schema_name,exc,code,step", [
    ("research", BedrockUnavailable("x"), "BEDROCK_UNAVAILABLE", "Researching"),
    ("match", InvalidModelOutput("x"), "MATCH_FAILED", "Matching case studies"),
    ("match", BedrockUnavailable("x"), "BEDROCK_UNAVAILABLE", "Matching case studies"),
    ("write", InvalidModelOutput("x"), "WRITE_FAILED", "Writing brief"),
    ("write", BedrockUnavailable("x"), "BEDROCK_UNAVAILABLE", "Writing brief"),
])
def test_each_step_failure_gives_its_code(schema_name, exc, code, step):
    from backend.src.services import brief_writer, case_study_matcher, research

    schema = {"research": research.P2_SCHEMA, "match": case_study_matcher.P3_SCHEMA, "write": brief_writer.P4_SCHEMA}[schema_name]
    with backend(model=Flaky(OfflineModel(), schema, exc)) as env:
        brief_id, job = parse_and_confirm(env)
        assert pipeline.handle_message(msg(brief_id, job, "pipeline"), env.deps) == "failed"
        got = env.store.get(brief_id)
        assert (got["error"]["code"], got["error"]["step"]) == (code, step)


def test_retry_after_failure_reuses_finished_steps_and_the_research_cache():
    from backend.src.services import case_study_matcher

    flaky = Flaky(OfflineModel(), case_study_matcher.P3_SCHEMA, InvalidModelOutput("x"))
    with backend(model=flaky) as env:
        brief_id, job = parse_and_confirm(env)
        pipeline.handle_message(msg(brief_id, job, "pipeline"), env.deps)
        got = env.store.get(brief_id)
        assert got["status"] == "failed" and set(got["stepsCompleted"]) >= {"Researching", "Checking attendees"}
        calls_before = flaky.calls
        retry_job = env.store.requeue(brief_id, c.STATUS_FAILED, clear_error=True)
        assert pipeline.handle_message(msg(brief_id, retry_job, "pipeline"), env.deps) == "ready"
        assert flaky.calls - calls_before == 2   # only matching and writing ran again


def test_missing_confirmed_invite_fails_cleanly():
    with backend() as env:
        brief, _ = env.store.create("alice", "AWS", "x")
        job = env.store.requeue(brief["briefId"], c.STATUS_QUEUED)
        assert pipeline.handle_message(msg(brief["briefId"], job, "pipeline"), env.deps) == "failed"
        assert env.store.get(brief["briefId"])["error"]["code"] == "INVALID_STATE"


def test_an_unexpected_crash_is_raised_so_sqs_redelivers():
    class Boom:
        def research(self, name, domain):
            raise RuntimeError("bug")

    with backend(provider=Boom()) as env:
        brief_id, job = parse_and_confirm(env)
        with pytest.raises(RuntimeError):
            pipeline.handle_message(msg(brief_id, job, "pipeline"), env.deps)


def test_logs_from_the_pipeline_never_contain_invite_text_or_emails():
    with backend() as env:
        brief_id, job = parse_and_confirm(env)
        pipeline.handle_message(msg(brief_id, job, "pipeline"), env.deps)
        text = json.dumps(env.events)
        assert "@" not in text and "Rowan" not in text and "allstate.com" not in text


# --- the Lambda entry point ------------------------------------------------------------------------------
def test_lambda_handler_reads_sqs_records(monkeypatch):
    from backend.src.handlers import worker

    with backend() as env:
        brief, job = env.store.create("alice", "AWS", invite_text("01-delta-air-lines.txt"))
        monkeypatch.setattr(worker, "_deps", env.deps)
        out = worker.handler({"Records": [{"body": json.dumps(msg(brief["briefId"], job, "parse"))},
                                          {"body": "not json"}]}, None)
        assert out == {"outcomes": ["parsed", "invalid"]}
