"""The worker's jobs (design 7.1): parse, pipeline, and extract_rules.

Each job checks that the queue message is still the current job for the brief, records the step
before it starts and the result after it ends, and skips steps that are already done (so a
retry or a duplicate message never repeats work). Expected failures end the job with a status
of `failed` and an error code. Anything unexpected is raised, so SQS delivers the message again
(up to 3 times, then the dead-letter queue).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from ..lib import constants as c
from ..lib import models
from ..lib.bedrock_client import BedrockUnavailable, InvalidModelOutput
from ..lib.brief_store import BriefStore
from ..lib.models import CaseStudy
from . import brief_writer, case_study_matcher, invite_parser
from . import rules as rules_mod
from .research import NoPublicInfo, ResearchService

MESSAGES = {
    "PARSE_FAILED": "The invite could not be read. Check the text and retry.",
    "NO_PUBLIC_INFO": "No public information was found for this company.",
    "BEDROCK_UNAVAILABLE": "The AI service is busy or unavailable. Please retry in a minute.",
    "MATCH_FAILED": "Case studies could not be matched. Please retry.",
    "WRITE_FAILED": "The brief could not be written in the required format. Please retry.",
    "INVALID_STATE": "The brief is missing data it needs. Please start a new brief.",
}


class _Fail(Exception):
    def __init__(self, code: str, step: str | None, detail: str | None = None):
        super().__init__(code)
        self.code, self.step, self.detail = code, step, detail


class _Superseded(Exception):
    """A conditional write failed: another job, a retry, or the stuck check owns the brief now."""


@dataclass
class Deps:
    store: BriefStore
    research: ResearchService
    bedrock: Any
    rules: rules_mod.RulesStore
    studies: Sequence[CaseStudy]
    metrics: Any = None
    log: Callable[[str, dict[str, Any]], None] = field(default=lambda event, data: None)
    brief_model: str = c.DEFAULT_BRIEF_MODEL

    def count(self, name: str) -> None:
        if self.metrics is not None:
            self.metrics.incr(name)


def handle_message(body: Any, deps: Deps) -> str:
    """Run one queue message. Returns a short outcome word (used in logs and tests)."""
    if not models.is_valid("queue_message", body):
        deps.log("message_invalid", {})
        return "invalid"
    brief = deps.store.get(body["briefId"])
    if brief is None or brief.get("currentJobId") != body["jobId"]:
        deps.log("message_stale", {"jobType": body["type"]})
        return "stale"
    job = {"parse": _parse_job, "pipeline": _pipeline_job, "extract_rules": _rules_job}[body["type"]]
    try:
        outcome = job(brief, body["jobId"], deps)
    except _Superseded:
        deps.log("job_superseded", {"jobType": body["type"]})
        return "superseded"
    deps.log("job_done", {"jobType": body["type"], "outcome": outcome})
    return outcome


# --- parse ----------------------------------------------------------------------------------------
def _parse_job(brief: dict[str, Any], job_id: str, deps: Deps) -> str:
    if not deps.store.begin_job(brief["briefId"], job_id, c.STATUS_QUEUED, c.STEP_PARSING):
        return "duplicate"
    try:
        parsed = invite_parser.parse_invite(deps.bedrock, brief["inviteText"])
    except (BedrockUnavailable, InvalidModelOutput, models.ModelValidationError) as exc:
        return _fail(deps, brief, job_id, "PARSE_FAILED" if not isinstance(exc, BedrockUnavailable) else "BEDROCK_UNAVAILABLE",
                     c.STEP_PARSING)
    _ok(deps.store.finish(brief["briefId"], job_id, c.STATUS_AWAITING_CONFIRMATION,
                          {"parsedInvite": parsed}, completed_step=c.STEP_PARSING))
    return "parsed"


# --- pipeline -----------------------------------------------------------------------------------------
PIPELINE_STEPS = (c.STEP_RESEARCHING, c.STEP_MATCHING, c.STEP_WRITING)


def _pipeline_job(brief: dict[str, Any], job_id: str, deps: Deps) -> str:
    done = set(brief.get("stepsCompleted", []))
    first = next((s for s in PIPELINE_STEPS if s not in done), c.STEP_WRITING)
    if not deps.store.begin_job(brief["briefId"], job_id, c.STATUS_QUEUED, first):
        return "duplicate"
    invite = brief.get("confirmedInvite")
    if not invite:
        return _fail(deps, brief, job_id, "INVALID_STATE", first)
    data = dict(brief)
    started = time.monotonic()
    try:
        for step in PIPELINE_STEPS:
            if step in done and _has_result(step, data):
                continue
            _ok(deps.store.set_step(brief["briefId"], job_id, step))
            if step == c.STEP_WRITING:
                written = _write(data, deps)
                _ok(deps.store.finish(
                    brief["briefId"], job_id, c.STATUS_READY,
                    {"draft": written.content, "content": written.content, "rulesApplied": written.rules_applied,
                     "version": 0},
                    completed_step=step))
                deps.count("BriefGenerated")
                deps.log("brief_ready", {"seconds": round(time.monotonic() - started, 1), "model": written.model,
                                         "repairs": written.repairs, "failedChecks": written.repair_problems})
                return "ready"
            field_name, value = _run_step(step, data, invite, deps)
            data[field_name] = value
            _ok(deps.store.complete_step(brief["briefId"], job_id, step, {field_name: value}))
    except _Fail as failure:
        return _fail(deps, brief, job_id, failure.code, failure.step, failure.detail)
    return "ready"  # pragma: no cover (the loop always returns at the writing step)


RESULT_FIELD = {c.STEP_RESEARCHING: "research", c.STEP_MATCHING: "caseStudyMatches"}


def _has_result(step: str, data: dict[str, Any]) -> bool:
    return step == c.STEP_WRITING or RESULT_FIELD[step] in data


def _run_step(step: str, data: dict[str, Any], invite: dict[str, Any], deps: Deps) -> tuple[str, Any]:
    if step == c.STEP_RESEARCHING:
        try:
            research, hit = deps.research.get_research(invite["company"]["name"], invite["company"]["domain"])
        except NoPublicInfo:
            raise _Fail("NO_PUBLIC_INFO", step) from None
        except (BedrockUnavailable, InvalidModelOutput) as exc:
            raise _Fail("BEDROCK_UNAVAILABLE", step, str(exc)) from None
        deps.log("research_done", {"cacheHit": hit})
        return "research", research
    if step == c.STEP_MATCHING:
        try:
            # The BU stored on the brief came from the creator's verified token (R5.1).
            matches = case_study_matcher.match_case_studies(
                deps.bedrock, data.get("bu"), data["research"], deps.studies,
                stated_needs=case_study_matcher.stated_needs_from_invite(invite))
        except BedrockUnavailable as exc:
            raise _Fail("BEDROCK_UNAVAILABLE", step, str(exc)) from None
        except InvalidModelOutput as exc:
            raise _Fail("MATCH_FAILED", step, str(exc)) from None
        return "caseStudyMatches", matches
    raise AssertionError(step)  # pragma: no cover


def _write(data: dict[str, Any], deps: Deps) -> brief_writer.WrittenBrief:
    invite = data["confirmedInvite"]
    try:
        return brief_writer.write_brief(
            deps.bedrock,
            research=data["research"],
            attendees=invite.get("attendees", []),
            case_matches=data["caseStudyMatches"],
            rules=deps.rules.list_newest(data["userId"]),
            meeting={"subject": invite.get("subject"), "meetingDate": invite.get("meetingDate"), "notes": invite.get("notes")},
            model=deps.brief_model,
            log=deps.log,
        )
    except BedrockUnavailable as exc:
        raise _Fail("BEDROCK_UNAVAILABLE", c.STEP_WRITING, str(exc)) from None
    except (InvalidModelOutput, brief_writer.BriefWriteError, models.ModelValidationError) as exc:
        raise _Fail("WRITE_FAILED", c.STEP_WRITING, type(exc).__name__) from None


# --- rules after approval ---------------------------------------------------------------------------------
def _rules_job(brief: dict[str, Any], job_id: str, deps: Deps) -> str:
    if brief.get("status") != c.STATUS_APPROVED or brief.get("rulesStatus") != "pending":
        return "duplicate"
    try:
        existing = [r["text"] for r in deps.rules.list_all(brief["userId"])]
        proposals = rules_mod.extract_rules(deps.bedrock, brief.get("draft") or {}, brief.get("content") or {}, existing)
    except (BedrockUnavailable, InvalidModelOutput):
        # The brief stays approved; the SE is told that no rules were proposed (R7.13).
        _ok(deps.store.set_rules_result(brief["briefId"], job_id, "failed", []))
        return "rules_failed"
    status = "ready" if proposals else "none"
    _ok(deps.store.set_rules_result(brief["briefId"], job_id, status, proposals))
    return f"rules_{status}"


# --- helpers ---------------------------------------------------------------------------------------------------
def _ok(written: bool) -> None:
    if not written:
        raise _Superseded()


def _fail(deps: Deps, brief: dict[str, Any], job_id: str, code: str, step: str | None,
          detail: str | None = None) -> str:
    # `detail` is the error class and code only (for example "ValidationException"), never user data.
    deps.log("job_failed", {"code": code, "step": step, "detail": detail})
    deps.store.fail(brief["briefId"], job_id, code, step, MESSAGES[code])
    return "failed"
