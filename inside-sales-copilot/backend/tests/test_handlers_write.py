import copy

import pytest

from backend.src.handlers import briefs_read, briefs_write as h
from backend.src.lib import api
from backend.src.lib import constants as c
from backend.src.services import pipeline
from backend.tests.api_helpers import api_deps, event, payload
from backend.tests.env_helpers import backend, invite_text


def call(route, env, route_key, brief_id, body=None, user="alice", bu="ServiceNow"):
    return api.run(route, event(route_key, user=user, bu=bu, body=body, path={"id": brief_id}), api_deps(env))


def work(env):
    """Run every queued job, like the worker would."""
    for m in env.sent_messages():
        pipeline.handle_message(m, env.deps)


def parsed_brief(env, invite="04-allstate.txt"):
    resp = api.run(briefs_read.create_brief, event("POST /api/briefs", body={"inviteText": invite_text(invite)}), api_deps(env))
    brief_id = payload(resp)["briefId"]
    work(env)
    assert env.store.get(brief_id)["status"] == "awaiting_confirmation"
    return brief_id


def ready_brief(env):
    brief_id = parsed_brief(env)
    parsed = env.store.get(brief_id)["parsedInvite"]
    assert call(h.confirm_brief, env, "POST /api/briefs/{id}/confirm", brief_id, {"parsedInvite": parsed})["statusCode"] == 202
    work(env)
    assert env.store.get(brief_id)["status"] == "ready"
    return brief_id


# --- confirm --------------------------------------------------------------------------------------------
def test_confirm_queues_the_pipeline_and_stores_the_confirmed_invite():
    with backend() as env:
        brief_id = parsed_brief(env)
        parsed = env.store.get(brief_id)["parsedInvite"]
        parsed["attendees"][0]["title"] = "VP, IT Service Management"
        resp = call(h.confirm_brief, env, "POST /api/briefs/{id}/confirm", brief_id, {"parsedInvite": parsed})
        assert resp["statusCode"] == 202 and payload(resp)["status"] == "queued"
        brief = env.store.get(brief_id)
        assert brief["confirmedInvite"]["company"]["domain"] == "allstate.com"
        (message,) = env.sent_messages()
        assert message["type"] == "pipeline" and message["jobId"] == brief["currentJobId"]


@pytest.mark.parametrize("mutate,code", [
    (lambda p: p.update(company={"name": None, "domain": None}), "COMPANY_REQUIRED"),
    (lambda p: p.update(company={"name": "Globex Corp", "domain": "globex.com"}), "COMPANY_DOMAIN_MISMATCH"),
    (lambda p: p.update(attendees=[{"name": f"P{i}", "title": None, "email": f"p{i}@allstate.com"} for i in range(21)]), "TOO_MANY_ATTENDEES"),
    (lambda p: p["attendees"][0].update(email="not-an-email"), "INVALID_EMAIL"),
])
def test_confirmation_rules_give_400_and_nothing_is_queued(mutate, code):
    with backend() as env:
        brief_id = parsed_brief(env)
        parsed = env.store.get(brief_id)["parsedInvite"]
        mutate(parsed)
        resp = call(h.confirm_brief, env, "POST /api/briefs/{id}/confirm", brief_id, {"parsedInvite": parsed})
        assert resp["statusCode"] == 400 and payload(resp)["error"]["code"] == code
        assert env.sent_messages() == [] and env.store.get(brief_id)["status"] == "awaiting_confirmation"


def test_a_mismatch_is_accepted_once_the_company_is_confirmed():
    with backend() as env:
        brief_id = parsed_brief(env)
        parsed = env.store.get(brief_id)["parsedInvite"]
        parsed["company"] = {"name": "Globex Corp", "domain": "globex.com"}
        body = {"parsedInvite": parsed, "companyConfirmed": True}
        assert call(h.confirm_brief, env, "POST /api/briefs/{id}/confirm", brief_id, body)["statusCode"] == 202


def test_confirm_in_the_wrong_status_gives_409():
    with backend() as env:
        brief_id = ready_brief(env)
        parsed = env.store.get(brief_id)["parsedInvite"]
        resp = call(h.confirm_brief, env, "POST /api/briefs/{id}/confirm", brief_id, {"parsedInvite": parsed})
        assert resp["statusCode"] == 409 and payload(resp)["error"]["code"] == "BRIEF_NOT_CONFIRMABLE"


# --- PUT: parsed invite corrections ----------------------------------------------------------------------
def test_parsed_invite_corrections_are_saved_with_warnings_recomputed():
    with backend() as env:
        brief_id = parsed_brief(env)
        parsed = env.store.get(brief_id)["parsedInvite"]
        parsed["company"]["name"] = "Globex"
        parsed["warnings"] = []
        resp = call(h.update_brief, env, "PUT /api/briefs/{id}", brief_id, {"parsedInvite": parsed})
        assert resp["statusCode"] == 200
        assert "company_domain_mismatch" not in payload(resp)["parsedInvite"]["warnings"]   # the domain still matches
        parsed["company"] = {"name": "Globex", "domain": None}
        resp = call(h.update_brief, env, "PUT /api/briefs/{id}", brief_id, {"parsedInvite": parsed})
        assert "company_domain_mismatch" in payload(resp)["parsedInvite"]["warnings"]


def test_an_invalid_parsed_invite_gives_400():
    with backend() as env:
        brief_id = parsed_brief(env)
        resp = call(h.update_brief, env, "PUT /api/briefs/{id}", brief_id, {"parsedInvite": {"company": "x"}})
        assert resp["statusCode"] == 400


# --- PUT: content edits ---------------------------------------------------------------------------------------
def test_editing_one_line_saves_the_change_and_keeps_the_draft():
    with backend() as env:
        brief_id = ready_brief(env)
        brief = env.store.get(brief_id)
        content = copy.deepcopy(brief["content"])
        content["discoveryQuestions"][0]["text"] = "What is your budget cycle?"
        resp = call(h.update_brief, env, "PUT /api/briefs/{id}", brief_id, {"content": content, "version": 0})
        assert resp["statusCode"] == 200 and payload(resp)["version"] == 1
        after = env.store.get(brief_id)
        assert after["content"]["discoveryQuestions"][0]["text"] == "What is your budget cycle?"
        assert after["draft"] == brief["draft"]


def test_a_stale_version_gives_409_conflict():
    with backend() as env:
        brief_id = ready_brief(env)
        content = env.store.get(brief_id)["content"]
        call(h.update_brief, env, "PUT /api/briefs/{id}", brief_id, {"content": content, "version": 0})
        resp = call(h.update_brief, env, "PUT /api/briefs/{id}", brief_id, {"content": content, "version": 0})
        assert resp["statusCode"] == 409 and payload(resp)["error"]["code"] == "CONFLICT"


@pytest.mark.parametrize("mutate,message", [
    (lambda c_: c_["agenda"][0].update(minutes=c_["agenda"][0]["minutes"] + 1), "adds up to 31"),
    (lambda c_: c_["companySnapshot"][1]["sourceUrls"].append("https://invented.example/"), "cannot be invented"),
    (lambda c_: c_["attendees"][1].update(title="CEO"), "'attendees' section cannot be edited"),
    (lambda c_: c_["caseStudies"].pop(), "'caseStudies' section cannot be edited"),
    (lambda c_: c_["sources"].append({"url": "https://x.example/", "label": "x"}), "'sources' section cannot be edited"),
    (lambda c_: c_["painPointHypotheses"][0].update(basedOnFactIds=["f999"]), "fact that does not exist"),
    (lambda c_: c_["discoveryQuestions"].append(dict(c_["discoveryQuestions"][0])), "unique ids"),
    (lambda c_: c_.update(extra=1), "not valid"),
])
def test_edits_that_break_the_rules_are_rejected(mutate, message):
    with backend() as env:
        brief_id = ready_brief(env)
        content = copy.deepcopy(env.store.get(brief_id)["content"])
        mutate(content)
        resp = call(h.update_brief, env, "PUT /api/briefs/{id}", brief_id, {"content": content, "version": 0})
        assert resp["statusCode"] == 400 and payload(resp)["error"]["code"] == "INVALID_CONTENT"
        assert message in payload(resp)["error"]["message"]
        assert env.store.get(brief_id)["version"] == 0


def test_adding_and_removing_questions_is_allowed():
    with backend() as env:
        brief_id = ready_brief(env)
        content = copy.deepcopy(env.store.get(brief_id)["content"])
        content["discoveryQuestions"].pop()
        content["discoveryQuestions"].append({"id": "new-1", "text": "Who signs off on spend?"})
        assert call(h.update_brief, env, "PUT /api/briefs/{id}", brief_id, {"content": content, "version": 0})["statusCode"] == 200


def test_edits_are_refused_while_queued_and_after_approval():
    with backend() as env:
        brief_id = ready_brief(env)
        content = env.store.get(brief_id)["content"]
        call(h.approve_brief, env, "POST /api/briefs/{id}/approve", brief_id)
        resp = call(h.update_brief, env, "PUT /api/briefs/{id}", brief_id, {"content": content, "version": 0})
        assert resp["statusCode"] == 409 and payload(resp)["error"]["code"] == "BRIEF_NOT_EDITABLE"
        queued = payload(api.run(briefs_read.create_brief, event("POST /api/briefs", body={"inviteText": "Hi"}), api_deps(env)))["briefId"]
        resp = call(h.update_brief, env, "PUT /api/briefs/{id}", queued, {"content": content, "version": 0})
        assert resp["statusCode"] == 409


def test_missing_version_gives_400():
    with backend() as env:
        brief_id = ready_brief(env)
        content = env.store.get(brief_id)["content"]
        resp = call(h.update_brief, env, "PUT /api/briefs/{id}", brief_id, {"content": content})
        assert resp["statusCode"] == 400


# --- approve --------------------------------------------------------------------------------------------------------
def test_approve_locks_the_brief_and_queues_one_rules_job_without_calling_bedrock():
    with backend() as env:
        brief_id = ready_brief(env)
        model_calls = len(env.model.calls)
        resp = call(h.approve_brief, env, "POST /api/briefs/{id}/approve", brief_id)
        assert resp["statusCode"] == 202 and payload(resp) == {"briefId": brief_id, "status": "approved", "rulesStatus": "pending"}
        assert len(env.model.calls) == model_calls
        (message,) = env.sent_messages()
        assert message["type"] == "extract_rules"
        again = call(h.approve_brief, env, "POST /api/briefs/{id}/approve", brief_id)
        assert again["statusCode"] == 409 and payload(again)["error"]["code"] == "BRIEF_NOT_APPROVABLE"


def test_the_whole_edit_approve_and_rules_flow():
    with backend() as env:
        brief_id = ready_brief(env)
        content = copy.deepcopy(env.store.get(brief_id)["content"])
        content["discoveryQuestions"][0]["text"] = "What is your budget cycle?"
        call(h.update_brief, env, "PUT /api/briefs/{id}", brief_id, {"content": content, "version": 0})
        call(h.approve_brief, env, "POST /api/briefs/{id}/approve", brief_id)
        work(env)
        brief = env.store.get(brief_id)
        assert brief["status"] == "approved" and brief["rulesStatus"] == "ready"
        assert brief["ruleProposals"][0]["text"] == "Always ask about the budget cycle."


# --- retry ---------------------------------------------------------------------------------------------------------------
def test_retry_only_from_failed_and_it_picks_the_right_job_type():
    with backend() as env:
        brief_id = ready_brief(env)
        resp = call(h.retry_brief, env, "POST /api/briefs/{id}/retry", brief_id)
        assert resp["statusCode"] == 409 and payload(resp)["error"]["code"] == "BRIEF_NOT_FAILED"
        # a brief that failed before confirmation is retried as a parse job
        create = api.run(briefs_read.create_brief, event("POST /api/briefs", body={"inviteText": "Hi"}), api_deps(env))
        other = payload(create)["briefId"]
        env.sent_messages()
        brief = env.store.get(other)
        env.store.fail(other, brief["currentJobId"], "PARSE_FAILED", "Parsing", "m")
        assert call(h.retry_brief, env, "POST /api/briefs/{id}/retry", other)["statusCode"] == 202
        (message,) = env.sent_messages()
        assert message["type"] == "parse" and "error" not in env.store.get(other)


def test_a_failed_pipeline_is_retried_as_a_pipeline_job():
    with backend() as env:
        brief_id = parsed_brief(env)
        parsed = env.store.get(brief_id)["parsedInvite"]
        call(h.confirm_brief, env, "POST /api/briefs/{id}/confirm", brief_id, {"parsedInvite": parsed})
        (message,) = env.sent_messages()
        env.store.fail(brief_id, message["jobId"], "BEDROCK_UNAVAILABLE", "Researching", "m")
        call(h.retry_brief, env, "POST /api/briefs/{id}/retry", brief_id)
        (message,) = env.sent_messages()
        assert message["type"] == "pipeline"
        pipeline.handle_message(message, env.deps)
        assert env.store.get(brief_id)["status"] == "ready"


# --- ownership --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("route,key,body", [
    (h.update_brief, "PUT /api/briefs/{id}", {"content": {}, "version": 0}),
    (h.confirm_brief, "POST /api/briefs/{id}/confirm", {"parsedInvite": {}}),
    (h.approve_brief, "POST /api/briefs/{id}/approve", None),
    (h.retry_brief, "POST /api/briefs/{id}/retry", None),
])
def test_another_users_brief_gives_404_on_every_write_route(route, key, body):
    with backend() as env:
        brief_id = ready_brief(env)
        resp = call(route, env, key, brief_id, body, user="bob")
        assert resp["statusCode"] == 404 and payload(resp)["error"]["code"] == "NOT_FOUND"
        assert env.store.get(brief_id)["status"] == "ready"
