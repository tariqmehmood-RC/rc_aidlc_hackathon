import pytest

from backend.src.handlers import briefs_read as h
from backend.src.lib import api
from backend.src.lib import constants as c
from backend.src.services import pipeline
from backend.tests.api_helpers import api_deps, event, payload
from backend.tests.env_helpers import backend, invite_text


def call(route, ev, env):
    return api.run(route, ev, api_deps(env))


def create(env, text=None, **kw):
    return call(h.create_brief, event("POST /api/briefs", body={"inviteText": text or invite_text("01-delta-air-lines.txt")}, **kw), env)


# --- POST /briefs ----------------------------------------------------------------------------------
def test_valid_text_gives_202_a_queued_brief_and_one_parse_message():
    with backend() as env:
        resp = create(env)
        assert resp["statusCode"] == 202
        out = payload(resp)
        assert out["status"] == "queued"
        brief = env.store.get(out["briefId"])
        assert brief["userId"] == "alice" and brief["bu"] == "ServiceNow"
        (message,) = env.sent_messages()
        assert message == {"type": "parse", "briefId": out["briefId"], "jobId": brief["currentJobId"]}


@pytest.mark.parametrize("text,code", [("", "INVITE_EMPTY"), ("   \n\t ", "INVITE_EMPTY"), ("x" * 10_001, "INVITE_TOO_LONG")])
def test_empty_whitespace_and_too_long_text_give_400_and_nothing_is_saved_or_queued(text, code):
    with backend() as env:
        resp = create(env, text=text) if text else call(h.create_brief, event("POST /api/briefs", body={"inviteText": ""}), env)
        assert resp["statusCode"] == 400 and payload(resp)["error"]["code"] == code
        assert env.sent_messages() == []
        assert env.store.list_for_user("alice") == ([], None)


def test_exactly_10000_characters_is_accepted():
    with backend() as env:
        assert create(env, text="x" * 10_000)["statusCode"] == 202


@pytest.mark.parametrize("bad", [{"inviteText": 5}, {"inviteText": None}, {}, {"text": "hello"}])
def test_missing_or_non_string_text_gives_400(bad):
    with backend() as env:
        resp = call(h.create_brief, event("POST /api/briefs", body=bad), env)
        assert resp["statusCode"] == 400 and payload(resp)["error"]["code"] == "INVALID_BODY"


def test_a_user_without_a_bu_cannot_create_a_brief():
    with backend() as env:
        resp = create(env, bu=None)
        assert resp["statusCode"] == 403 and payload(resp)["error"]["code"] == "NO_BU"


def test_bu_in_the_body_is_ignored():
    with backend() as env:
        resp = call(h.create_brief, event("POST /api/briefs", bu="AWS",
                                          body={"inviteText": "Hello", "bu": "ServiceNow", "userId": "bob"}), env)
        brief = env.store.get(payload(resp)["briefId"])
        assert (brief["bu"], brief["userId"]) == ("AWS", "alice")


def test_unauthenticated_requests_get_401():
    with backend() as env:
        assert create(env, user=None)["statusCode"] == 401


def test_a_queue_failure_marks_the_brief_failed_and_returns_503():
    with backend() as env:
        deps = api_deps(env)

        class Down:
            def send(self, *a):
                raise RuntimeError("sqs down")

        deps.queue = Down()
        resp = api.run(h.create_brief, event("POST /api/briefs", body={"inviteText": "Hi"}), deps)
        assert resp["statusCode"] == 503
        (row,), _ = env.store.list_for_user("alice")
        assert row["status"] == "failed" and row["error"]["code"] == "QUEUE_FAILED"


# --- GET /briefs/{id} -----------------------------------------------------------------------------------
def test_get_returns_the_view_with_queue_position():
    with backend() as env:
        first = payload(create(env))["briefId"]
        env.clock.advance(1)
        second = payload(create(env))["briefId"]
        out = payload(call(h.get_brief, event("GET /api/briefs/{id}", path={"id": second}), env))
        assert out["status"] == "queued" and out["queuePosition"] == 2
        assert "inviteText" not in out and "userId" not in out and "currentJobId" not in out
        assert payload(call(h.get_brief, event("GET /api/briefs/{id}", path={"id": first}), env))["queuePosition"] == 1


def test_another_users_brief_gives_404_like_a_missing_one():
    with backend() as env:
        brief_id = payload(create(env))["briefId"]
        theirs = call(h.get_brief, event("GET /api/briefs/{id}", user="bob", path={"id": brief_id}), env)
        missing = call(h.get_brief, event("GET /api/briefs/{id}", path={"id": "f" * 32}), env)
        malformed = call(h.get_brief, event("GET /api/briefs/{id}", path={"id": "../../etc"}), env)
        assert theirs["statusCode"] == missing["statusCode"] == malformed["statusCode"] == 404
        assert payload(theirs) == payload(missing)


def test_a_stuck_brief_is_returned_as_failed():
    with backend() as env:
        brief_id = payload(create(env))["briefId"]
        job = env.store.get(brief_id)["currentJobId"]
        env.store.begin_job(brief_id, job, c.STATUS_QUEUED, "Parsing")
        env.clock.advance(121)
        out = payload(call(h.get_brief, event("GET /api/briefs/{id}", path={"id": brief_id}), env))
        assert out["status"] == "failed" and out["error"]["code"] == "STUCK"


def test_get_shows_the_step_while_processing_and_the_brief_when_ready():
    with backend() as env:
        brief_id = payload(create(env, text=invite_text("04-allstate.txt")))["briefId"]
        brief = env.store.get(brief_id)
        env.store.begin_job(brief_id, brief["currentJobId"], c.STATUS_QUEUED, "Parsing")
        out = payload(call(h.get_brief, event("GET /api/briefs/{id}", path={"id": brief_id}), env))
        assert out["step"] == "Parsing" and "queuePosition" not in out
        # run the real worker to the end
        env.store.fail(brief_id, brief["currentJobId"], "X", None, "reset")
        job = env.store.requeue(brief_id, c.STATUS_FAILED, clear_error=True)
        pipeline.handle_message({"type": "parse", "briefId": brief_id, "jobId": job}, env.deps)
        parsed = env.store.get(brief_id)["parsedInvite"]
        job = env.store.requeue(brief_id, c.STATUS_AWAITING_CONFIRMATION, {"confirmedInvite": parsed})
        pipeline.handle_message({"type": "pipeline", "briefId": brief_id, "jobId": job}, env.deps)
        out = payload(call(h.get_brief, event("GET /api/briefs/{id}", path={"id": brief_id}), env))
        assert out["status"] == "ready" and "content" in out and "research" in out and "draft" not in out


# --- GET /briefs ----------------------------------------------------------------------------------------------
def test_list_returns_only_the_callers_briefs_newest_first_20_per_page():
    with backend() as env:
        ids = []
        for _ in range(23):
            env.clock.advance(1)
            ids.append(payload(create(env))["briefId"])
        create(env, user="bob")
        page1 = payload(call(h.list_briefs, event("GET /api/briefs"), env))
        assert len(page1["items"]) == 20 and page1["nextCursor"]
        page2 = payload(call(h.list_briefs, event("GET /api/briefs", query={"cursor": page1["nextCursor"]}), env))
        assert len(page2["items"]) == 3 and page2["nextCursor"] is None
        assert [i["briefId"] for i in page1["items"] + page2["items"]] == list(reversed(ids))


@pytest.mark.parametrize("q,code", [({"limit": "0"}, "INVALID_LIMIT"), ({"limit": "21"}, "INVALID_LIMIT"),
                                    ({"limit": "abc"}, "INVALID_LIMIT"), ({"cursor": "garbage"}, "INVALID_CURSOR")])
def test_bad_paging_parameters_give_400(q, code):
    with backend() as env:
        resp = call(h.list_briefs, event("GET /api/briefs", query=q), env)
        assert resp["statusCode"] == 400 and payload(resp)["error"]["code"] == code


def test_another_users_cursor_is_rejected():
    with backend() as env:
        for _ in range(3):
            env.clock.advance(1)
            create(env)
        cursor = payload(call(h.list_briefs, event("GET /api/briefs", query={"limit": "1"}), env))["nextCursor"]
        resp = call(h.list_briefs, event("GET /api/briefs", user="bob", query={"cursor": cursor}), env)
        assert resp["statusCode"] == 400


def test_empty_history():
    with backend() as env:
        assert payload(call(h.list_briefs, event("GET /api/briefs"), env)) == {"items": [], "nextCursor": None}
