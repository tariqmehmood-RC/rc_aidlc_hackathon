import itertools

import boto3
import pytest
from moto import mock_aws

from backend.src.lib import constants as c
from backend.src.lib.brief_store import BRIEFS_TABLE_DEFINITION, BriefStore, InvalidCursor
from backend.tests.fakes import FakeClock

START = 1_790_000_000.0


@pytest.fixture()
def env():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.create_table(TableName="Briefs", **BRIEFS_TABLE_DEFINITION)
        clock = FakeClock(start=START)
        counter = itertools.count(1)
        store = BriefStore(table, clock=clock.time, id_factory=lambda: f"id-{next(counter):04d}")
        yield store, clock, table


def make(store, clock, user="alice", bu="AWS", text="invite text"):
    clock.advance(1)  # distinct creation times
    brief, job = store.create(user, bu, text)
    return brief, job


def to_processing(store, brief, job, step="Parsing"):
    assert store.begin_job(brief["briefId"], job, c.STATUS_QUEUED, step)


# --- create and read ------------------------------------------------------------------------------
def test_create_saves_a_queued_brief(env):
    store, clock, table = env
    brief, job = make(store, clock, bu="ServiceNow")
    assert brief["status"] == "queued" and brief["currentJobId"] == job
    assert brief["bu"] == "ServiceNow" and brief["rulesStatus"] == "none"
    raw = table.get_item(Key={"briefId": brief["briefId"]})["Item"]
    assert raw["queueKey"] == "Q" and raw["inviteText"] == "invite text"


def test_expiry_is_30_days_after_creation(env):
    store, clock, _ = env
    brief, _ = make(store, clock)
    assert brief["expiresAt"] == brief["createdAt"] // 1000 + 30 * 24 * 3600


def test_an_expired_brief_is_not_returned(env):
    store, clock, _ = env
    brief, _ = make(store, clock)
    clock.advance(30 * 24 * 3600 + 5)
    assert store.get(brief["briefId"]) is None


def test_another_users_brief_looks_the_same_as_a_missing_one(env):
    store, clock, _ = env
    brief, _ = make(store, clock, user="alice")
    assert store.get_owned(brief["briefId"], "alice")["briefId"] == brief["briefId"]
    assert store.get_owned(brief["briefId"], "bob") is None
    assert store.get_owned("no-such-id", "alice") is None


# --- job transitions ------------------------------------------------------------------------------------
def test_begin_job_moves_queued_to_processing_and_leaves_the_queue_index(env):
    store, clock, table = env
    brief, job = make(store, clock)
    assert store.begin_job(brief["briefId"], job, "queued", "Parsing") is True
    got = store.get(brief["briefId"])
    assert got["status"] == "processing" and got["step"] == "Parsing"
    assert "queueKey" not in table.get_item(Key={"briefId": brief["briefId"]})["Item"]


def test_a_stale_job_id_cannot_change_anything(env):
    store, clock, _ = env
    brief, job = make(store, clock)
    assert store.begin_job(brief["briefId"], "some-other-job", "queued") is False
    assert store.get(brief["briefId"])["status"] == "queued"


def test_a_duplicate_delivery_cannot_start_the_job_twice(env):
    store, clock, _ = env
    brief, job = make(store, clock)
    assert store.begin_job(brief["briefId"], job, "queued") is True
    assert store.begin_job(brief["briefId"], job, "queued") is False


def test_begin_job_needs_the_expected_status(env):
    store, clock, _ = env
    brief, job = make(store, clock)
    assert store.begin_job(brief["briefId"], job, "awaiting_confirmation") is False


def test_a_duplicate_message_cannot_overwrite_a_newer_status(env):
    store, clock, _ = env
    brief, job = make(store, clock)
    to_processing(store, brief, job)
    assert store.finish(brief["briefId"], job, "awaiting_confirmation", {"parsedInvite": {"a": 1}})
    # the user confirms: a new job is queued
    new_job = store.requeue(brief["briefId"], "awaiting_confirmation", {"confirmedInvite": {"b": 2}})
    # a late duplicate of the OLD job tries to write
    assert store.complete_step(brief["briefId"], job, "Parsing", {"parsedInvite": {"a": "stale"}}) is False
    assert store.finish(brief["briefId"], job, "ready", {}) is False
    assert store.fail(brief["briefId"], job, "X", None, "late") is False
    got = store.get(brief["briefId"])
    assert got["status"] == "queued" and got["currentJobId"] == new_job
    assert got["parsedInvite"] == {"a": 1}


def test_steps_are_recorded_with_their_results(env):
    store, clock, _ = env
    brief, job = make(store, clock)
    to_processing(store, brief, job)
    assert store.set_step(brief["briefId"], job, "Researching")
    assert store.complete_step(brief["briefId"], job, "Researching", {"research": {"x": [1, 2]}})
    assert store.complete_step(brief["briefId"], job, "Checking attendees", {"attendeeChecks": [{"e": "a"}]})
    got = store.get(brief["briefId"])
    assert got["stepsCompleted"] == ["Researching", "Checking attendees"]
    assert got["research"] == {"x": [1, 2]} and got["attendeeChecks"] == [{"e": "a"}]


def test_finish_sets_ready_and_clears_the_step(env):
    store, clock, _ = env
    brief, job = make(store, clock)
    to_processing(store, brief, job, "Writing brief")
    assert store.finish(brief["briefId"], job, "ready", {"draft": {"d": 1}, "content": {"d": 1}})
    got = store.get(brief["briefId"])
    assert got["status"] == "ready" and "step" not in got and got["draft"] == got["content"]


def test_finish_only_allows_the_two_end_states(env):
    store, clock, _ = env
    brief, job = make(store, clock)
    with pytest.raises(ValueError):
        store.finish(brief["briefId"], job, "approved")


def test_fail_records_code_step_and_message(env):
    store, clock, _ = env
    brief, job = make(store, clock)
    to_processing(store, brief, job)
    assert store.fail(brief["briefId"], job, "NO_PUBLIC_INFO", "Researching", "Nothing found")
    got = store.get(brief["briefId"])
    assert got["status"] == "failed" and got["error"] == {"code": "NO_PUBLIC_INFO", "step": "Researching", "message": "Nothing found"}
    assert "step" not in got


def test_a_failed_job_cannot_fail_again_or_be_finished(env):
    store, clock, _ = env
    brief, job = make(store, clock)
    to_processing(store, brief, job)
    store.fail(brief["briefId"], job, "X", None, "m")
    assert store.fail(brief["briefId"], job, "Y", None, "m2") is False
    assert store.finish(brief["briefId"], job, "ready") is False


def test_requeue_needs_the_right_status_and_gives_a_new_job(env):
    store, clock, _ = env
    brief, job = make(store, clock)
    assert store.requeue(brief["briefId"], "failed") is None            # it is queued, not failed
    to_processing(store, brief, job)
    store.fail(brief["briefId"], job, "X", "Researching", "m")
    new_job = store.requeue(brief["briefId"], "failed", clear_error=True)
    assert new_job and new_job != job
    got = store.get(brief["briefId"])
    assert got["status"] == "queued" and "error" not in got and got["currentJobId"] == new_job
    assert store.begin_job(brief["briefId"], job, "queued") is False    # the old job id is dead
    assert store.begin_job(brief["briefId"], new_job, "queued") is True


def test_retry_keeps_the_steps_already_done(env):
    store, clock, _ = env
    brief, job = make(store, clock)
    to_processing(store, brief, job)
    store.complete_step(brief["briefId"], job, "Researching", {"research": {"ok": True}})
    store.fail(brief["briefId"], job, "X", "Matching case studies", "m")
    store.requeue(brief["briefId"], "failed", clear_error=True)
    got = store.get(brief["briefId"])
    assert got["stepsCompleted"] == ["Researching"] and got["research"] == {"ok": True}


# --- queue position ----------------------------------------------------------------------------------------
def test_queue_position_counts_only_earlier_queued_briefs(env):
    store, clock, _ = env
    first, job1 = make(store, clock)
    second, _ = make(store, clock)
    third, _ = make(store, clock)
    assert [store.queue_position(store.get(b["briefId"])) for b in (first, second, third)] == [1, 2, 3]
    to_processing(store, first, job1)                       # the first one starts running
    assert store.queue_position(store.get(first["briefId"])) is None
    assert [store.queue_position(store.get(b["briefId"])) for b in (second, third)] == [1, 2]


def test_a_confirmed_brief_goes_to_the_back_of_the_queue(env):
    store, clock, _ = env
    a, job_a = make(store, clock)
    to_processing(store, a, job_a)
    store.finish(a["briefId"], job_a, "awaiting_confirmation", {"parsedInvite": {}})
    b, _ = make(store, clock)
    clock.advance(5)
    store.requeue(a["briefId"], "awaiting_confirmation")
    assert store.queue_position(store.get(b["briefId"])) == 1
    assert store.queue_position(store.get(a["briefId"])) == 2


# --- stuck jobs ----------------------------------------------------------------------------------------------
def test_processing_brief_idle_for_more_than_120_seconds_becomes_failed_stuck(env):
    store, clock, _ = env
    brief, job = make(store, clock)
    to_processing(store, brief, job, "Researching")
    clock.advance(119)
    assert store.expire_if_stuck(store.get(brief["briefId"]))["status"] == "processing"
    clock.advance(2)
    out = store.expire_if_stuck(store.get(brief["briefId"]))
    assert out["status"] == "failed" and out["error"]["code"] == "STUCK" and out["error"]["step"] == "Researching"
    assert store.get(brief["briefId"])["status"] == "failed"        # saved, not just returned


def test_a_queued_brief_is_never_stuck(env):
    store, clock, _ = env
    brief, _ = make(store, clock)
    clock.advance(3600)
    assert store.expire_if_stuck(store.get(brief["briefId"]))["status"] == "queued"


def test_progress_resets_the_stuck_timer(env):
    store, clock, _ = env
    brief, job = make(store, clock)
    to_processing(store, brief, job)
    clock.advance(100)
    store.set_step(brief["briefId"], job, "Researching")
    clock.advance(100)
    assert store.expire_if_stuck(store.get(brief["briefId"]))["status"] == "processing"


def test_stuck_check_loses_gracefully_to_a_worker_that_just_wrote(env):
    store, clock, _ = env
    brief, job = make(store, clock)
    to_processing(store, brief, job)
    clock.advance(200)
    stale_view = store.get(brief["briefId"])
    store.set_step(brief["briefId"], job, "Researching")               # the worker was alive after all
    assert store.expire_if_stuck(stale_view)["status"] == "processing"


def test_a_stuck_job_cannot_write_after_it_was_failed(env):
    store, clock, _ = env
    brief, job = make(store, clock)
    to_processing(store, brief, job)
    clock.advance(200)
    store.expire_if_stuck(store.get(brief["briefId"]))
    assert store.complete_step(brief["briefId"], job, "Researching", {"research": {}}) is False
    assert store.finish(brief["briefId"], job, "ready") is False


# --- history ------------------------------------------------------------------------------------------------------
def test_25_briefs_paginate_20_then_5_newest_first_without_duplicates(env):
    store, clock, _ = env
    ids = [make(store, clock)[0]["briefId"] for _ in range(25)]
    page1, cursor = store.list_for_user("alice")
    assert len(page1) == 20 and cursor
    page2, cursor2 = store.list_for_user("alice", cursor=cursor)
    assert len(page2) == 5 and cursor2 is None
    listed = [b["briefId"] for b in page1 + page2]
    assert listed == list(reversed(ids))
    assert len(set(listed)) == 25


def test_exactly_20_briefs_has_no_second_page(env):
    store, clock, _ = env
    for _ in range(20):
        make(store, clock)
    page, cursor = store.list_for_user("alice")
    assert len(page) == 20 and cursor is None


def test_history_shows_only_the_users_own_briefs(env):
    store, clock, _ = env
    make(store, clock, user="alice")
    make(store, clock, user="bob")
    assert len(store.list_for_user("alice")[0]) == 1
    assert store.list_for_user("nobody") == ([], None)


def test_history_rows_show_company_date_status_and_failure_message(env):
    store, clock, _ = env
    brief, job = make(store, clock)
    to_processing(store, brief, job)
    store.finish(brief["briefId"], job, "awaiting_confirmation",
                 {"parsedInvite": {"company": {"name": "Delta Air Lines", "domain": "delta.com"}, "meetingDate": "2026-12-03"}})
    row = store.list_for_user("alice")[0][0]
    assert row["companyName"] == "Delta Air Lines" and row["meetingDate"] == "2026-12-03"
    assert row["status"] == "awaiting_confirmation" and "error" not in row
    new_job = store.requeue(brief["briefId"], "awaiting_confirmation")
    store.begin_job(brief["briefId"], new_job, "queued")
    store.fail(brief["briefId"], new_job, "NO_PUBLIC_INFO", "Researching", "Nothing found")
    row = store.list_for_user("alice")[0][0]
    assert row["status"] == "failed" and row["error"] == {"code": "NO_PUBLIC_INFO", "message": "Nothing found"}


def test_expired_briefs_are_not_listed(env):
    store, clock, _ = env
    make(store, clock)
    clock.advance(31 * 24 * 3600)
    assert store.list_for_user("alice") == ([], None)


def test_a_cursor_from_another_user_or_garbage_is_rejected(env):
    store, clock, _ = env
    for _ in range(3):
        make(store, clock, user="alice")
    _, cursor = store.list_for_user("alice", limit=2)
    assert cursor
    with pytest.raises(InvalidCursor):
        store.list_for_user("bob", cursor=cursor)
    for bad in ["", "garbage", "e30=", "not base64!!"]:
        if bad:
            with pytest.raises(InvalidCursor):
                store.list_for_user("alice", cursor=bad)


def test_limit_is_clamped_to_the_page_size(env):
    store, clock, _ = env
    for _ in range(25):
        make(store, clock)
    assert len(store.list_for_user("alice", limit=500)[0]) == 20
    assert len(store.list_for_user("alice", limit=0)[0]) == 1


# --- edits, approve, rules ------------------------------------------------------------------------------------------
def ready_brief(store, clock):
    brief, job = make(store, clock)
    to_processing(store, brief, job)
    draft = {"discoveryQuestions": [{"id": "q1", "text": "Why?"}]}
    store.finish(brief["briefId"], job, "ready", {"draft": draft, "content": draft})
    return brief


def test_edits_are_saved_only_while_ready_and_never_touch_the_draft(env):
    store, clock, _ = env
    brief = ready_brief(store, clock)
    edited = {"discoveryQuestions": [{"id": "q1", "text": "Why now?"}]}
    assert store.save_content(brief["briefId"], edited, 0) is True
    got = store.get(brief["briefId"])
    assert got["content"] == edited and got["draft"] == {"discoveryQuestions": [{"id": "q1", "text": "Why?"}]}
    assert got["version"] == 1


def test_a_second_edit_with_an_old_version_is_rejected(env):
    store, clock, _ = env
    brief = ready_brief(store, clock)
    assert store.save_content(brief["briefId"], {"a": 1}, 0)
    assert store.save_content(brief["briefId"], {"a": 2}, 0) is False
    assert store.save_content(brief["briefId"], {"a": 2}, 1) is True


def test_edits_are_refused_in_every_other_status(env):
    store, clock, _ = env
    queued, _ = make(store, clock)
    assert store.save_content(queued["briefId"], {"a": 1}, 0) is False
    approved = ready_brief(store, clock)
    store.approve(approved["briefId"])
    assert store.save_content(approved["briefId"], {"a": 1}, 0) is False


def test_approve_locks_the_brief_and_starts_a_rules_job(env):
    store, clock, _ = env
    brief = ready_brief(store, clock)
    rules_job = store.approve(brief["briefId"])
    got = store.get(brief["briefId"])
    assert got["status"] == "approved" and got["rulesStatus"] == "pending" and got["currentJobId"] == rules_job
    assert store.approve(brief["briefId"]) is None                    # a second approve is refused


def test_approve_only_works_from_ready(env):
    store, clock, _ = env
    brief, _ = make(store, clock)
    assert store.approve(brief["briefId"]) is None


def test_approve_can_store_the_final_content_in_the_same_write(env):
    store, clock, _ = env
    brief = ready_brief(store, clock)
    store.approve(brief["briefId"], {"final": True})
    assert store.get(brief["briefId"])["content"] == {"final": True}


def test_rules_result_is_accepted_once_for_the_right_job(env):
    store, clock, _ = env
    brief = ready_brief(store, clock)
    job = store.approve(brief["briefId"])
    assert store.set_rules_result(brief["briefId"], "wrong-job", "ready", []) is False
    assert store.set_rules_result(brief["briefId"], job, "ready", [{"proposalId": "p1", "text": "t"}]) is True
    assert store.set_rules_result(brief["briefId"], job, "failed") is False          # duplicate delivery
    got = store.get(brief["briefId"])
    assert got["rulesStatus"] == "ready" and got["ruleProposals"][0]["proposalId"] == "p1"
    assert got["status"] == "approved"


def test_rules_result_rejects_unknown_statuses(env):
    store, clock, _ = env
    with pytest.raises(ValueError):
        store.set_rules_result("x", "j", "pending")


def test_proposals_can_be_cleared_once_handled(env):
    store, clock, _ = env
    brief = ready_brief(store, clock)
    job = store.approve(brief["briefId"])
    store.set_rules_result(brief["briefId"], job, "ready", [{"proposalId": "p1", "text": "t"}])
    assert store.set_rule_proposals_handled(brief["briefId"]) is True
    assert store.set_rule_proposals_handled(brief["briefId"]) is False
    assert store.get(brief["briefId"])["ruleProposals"] == []


def test_parsed_invite_corrections_are_saved_only_while_awaiting_confirmation(env):
    store, clock, _ = env
    brief, job = make(store, clock)
    assert store.save_parsed_invite(brief["briefId"], {"a": 1}) is False
    to_processing(store, brief, job)
    store.finish(brief["briefId"], job, "awaiting_confirmation", {"parsedInvite": {"a": 0}})
    assert store.save_parsed_invite(brief["briefId"], {"a": 1}) is True
    assert store.get(brief["briefId"])["parsedInvite"] == {"a": 1}


# --- the API view -------------------------------------------------------------------------------------------------------
def test_view_hides_internal_fields_and_shows_position_only_while_queued(env):
    store, clock, _ = env
    brief, job = make(store, clock, text="secret invite text with jane@example.com")
    view = store.view(store.get(brief["briefId"]), store.queue_position(store.get(brief["briefId"])))
    assert view["queuePosition"] == 1 and view["status"] == "queued"
    dumped = str(view)
    for hidden in ("secret invite text", "alice", job, "userId", "currentJobId", "inviteText", "queueKey"):
        assert hidden not in dumped
    to_processing(store, brief, job, "Parsing")
    view = store.view(store.get(brief["briefId"]))
    assert "queuePosition" not in view and view["step"] == "Parsing"


def test_view_shows_the_error_only_for_failed_briefs(env):
    store, clock, _ = env
    brief, job = make(store, clock)
    to_processing(store, brief, job)
    store.fail(brief["briefId"], job, "STUCK", "Parsing", "m")
    assert store.view(store.get(brief["briefId"]))["error"]["code"] == "STUCK"
    new_job = store.requeue(brief["briefId"], "failed")                  # error kept in the row until cleared
    assert "error" not in store.view(store.get(brief["briefId"]))
