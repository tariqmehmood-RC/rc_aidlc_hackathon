"""Run the whole backend locally on one invite and print the brief (task 3.10).

    backend/.venv/bin/python -m backend.local_run data/sample_invites/04-allstate.txt --bu ServiceNow
    backend/.venv/bin/python -m backend.local_run <invite> --bu AWS --fake-bedrock --fixtures

DynamoDB lives in memory (moto). The worker's job code runs as it does in Lambda, through the
same shared Bedrock client and its 1 request per second limiter. With --fake-bedrock nothing
calls AWS. With --fixtures research reads recorded pages instead of the live web.
Not part of the Lambda package.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "tests" / "fixtures" / "research"
TABLES = {
    "Rules": {
        "KeySchema": [{"AttributeName": "userId", "KeyType": "HASH"}, {"AttributeName": "ruleId", "KeyType": "RANGE"}],
        "AttributeDefinitions": [{"AttributeName": "userId", "AttributeType": "S"}, {"AttributeName": "ruleId", "AttributeType": "S"}],
        "BillingMode": "PAY_PER_REQUEST",
    },
    "ResearchCache": {
        "KeySchema": [{"AttributeName": "companyDomain", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "companyDomain", "AttributeType": "S"}],
        "BillingMode": "PAY_PER_REQUEST",
    },
}
# Real Bedrock calls pass through the in-memory AWS mock.
BEDROCK_URL = r"https://bedrock-runtime\.us-east-1\.amazonaws\.com/.*"


def _cdk_context() -> dict[str, Any]:
    try:
        return json.loads((ROOT / "infra" / "cdk.json").read_text(encoding="utf-8"))["context"]
    except (OSError, ValueError, KeyError):
        return {}


def _configure_env(fake: bool, brief_model: str | None = None) -> None:
    """Defaults from CDK context, so the local run uses the same models as the deployed one.
    Environment variables that are already set win."""
    from .src.lib import constants as c

    ctx = _cdk_context()
    os.environ.setdefault(c.ENV_RESEARCH_USER_AGENT, ctx.get("researchUserAgent", c.RESEARCH_USER_AGENT_DEFAULT))
    if brief_model:
        os.environ[c.ENV_BRIEF_MODEL] = brief_model
    else:
        os.environ.setdefault(c.ENV_BRIEF_MODEL, ctx.get("briefModel", c.DEFAULT_BRIEF_MODEL))
    if not fake:
        os.environ.setdefault(c.ENV_MODEL_HAIKU, ctx.get("haikuModelId", ""))
        os.environ.setdefault(c.ENV_MODEL_SONNET, ctx.get("sonnetModelId", ""))
    os.environ["AWS_REGION"] = os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


class ScoreRecorder:
    """Passes calls through and keeps the raw case study scores, to report how many reached 60."""

    def __init__(self, inner: Any):
        self.inner = inner
        self.raw_scores: list[dict[str, Any]] = []

    def converse_json(self, **kw: Any) -> dict[str, Any]:
        from .src.services import case_study_matcher

        out = self.inner.converse_json(**kw)
        if kw.get("schema") is case_study_matcher.P3_SCHEMA:
            self.raw_scores = list(out["scores"])
        return out

    @property
    def usage(self) -> dict[str, dict[str, int]]:
        return getattr(self.inner, "usage", {})

    @property
    def json_repairs(self) -> dict[str, int]:
        return getattr(self.inner, "json_repairs", {})


def run(invite_path: str, bu: str, *, fake: bool, fixtures: bool, user: str = "local-user",
        rules: list[str] | None = None, out=sys.stdout, brief_model: str | None = None) -> dict[str, Any]:
    _configure_env(fake, brief_model)
    import boto3
    from moto import mock_aws

    from .src.lib import constants as c
    from .src.lib.bedrock_client import BedrockClient
    from .src.lib.brief_store import BRIEFS_TABLE_DEFINITION, BriefStore
    from .src.services import invite_parser, pipeline
    from .src.services.brief_writer import brief_model_from_env
    from .src.services.case_study_matcher import load_case_studies
    from .src.services.offline_model import OfflineModel
    from .src.services.research import ResearchService
    from .src.services.research_provider import FixtureProvider, PublicWebProvider
    from .src.services.rules import RulesStore

    text = Path(invite_path).read_text(encoding="utf-8")
    if len(text) > c.MAX_INVITE_CHARS or not text.strip():
        raise SystemExit(f"invite must be 1 to {c.MAX_INVITE_CHARS} characters")

    config = {"core": {"mock_credentials": fake, "passthrough": {"urls": [] if fake else [BEDROCK_URL], "services": []}}}
    with mock_aws(config=config):
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        briefs = ddb.create_table(TableName="Briefs", **BRIEFS_TABLE_DEFINITION)
        rules_table = ddb.create_table(TableName="Rules", **TABLES["Rules"])
        cache = ddb.create_table(TableName="ResearchCache", **TABLES["ResearchCache"])

        model = ScoreRecorder(OfflineModel() if fake else BedrockClient())
        provider = FixtureProvider(FIXTURES) if fixtures else PublicWebProvider()
        store = BriefStore(briefs)
        steps: list[tuple[str, float]] = []
        real_set_step = store.set_step

        def timed_set_step(brief_id: str, job_id: str, step: str) -> bool:
            steps.append((step, time.monotonic()))
            return real_set_step(brief_id, job_id, step)

        store.set_step = timed_set_step  # type: ignore[method-assign]
        events: list[tuple[str, dict[str, Any]]] = []
        deps = pipeline.Deps(store=store, research=ResearchService(model, provider, cache), bedrock=model,
                             rules=RulesStore(rules_table), studies=load_case_studies(),
                             log=lambda e, d: events.append((e, d)), brief_model=brief_model_from_env())
        for rule in rules or []:
            deps.rules.add(user, rule)

        started = time.monotonic()
        brief, job = store.create(user, bu, text)
        outcome = pipeline.handle_message({"type": "parse", "briefId": brief["briefId"], "jobId": job}, deps)
        parse_s = time.monotonic() - started
        parsed = store.get(brief["briefId"]).get("parsedInvite")
        if outcome != "parsed":
            return _report_failure(store.get(brief["briefId"]), out)

        # The SE confirms the parsed fields as they are (the UI lets them edit first).
        check = invite_parser.validate_confirmation(parsed, company_confirmed=True)
        if not check.ok:
            print("Confirmation rejected: " + "; ".join(e["message"] for e in check.errors), file=out)
            return {"status": "rejected", "errors": check.errors}
        job = store.requeue(brief["briefId"], c.STATUS_AWAITING_CONFIRMATION,
                            {"parsedInvite": check.normalized, "confirmedInvite": check.normalized})
        pipeline_started = time.monotonic()
        pipeline.handle_message({"type": "pipeline", "briefId": brief["briefId"], "jobId": job}, deps)
        done = time.monotonic()
        final = store.get(brief["briefId"])
        if final["status"] != c.STATUS_READY:
            return _report_failure(final, out)

        timing = {"parseSeconds": round(parse_s, 1), "pipelineSeconds": round(done - pipeline_started, 1),
                  "totalSeconds": round(done - started, 1)}
        step_times = [(name, round((steps[i + 1][1] if i + 1 < len(steps) else done) - t, 1)) for i, (name, t) in enumerate(steps)]
        qualifying = [s for s in model.raw_scores if s["score"] >= c.CASE_STUDY_MIN_SCORE]
        failed_checks = [d.get("checks", []) for e, d in events if e == "brief_check_failed"]
        summary = {"status": final["status"], "timing": timing, "steps": step_times,
                   "scoredAtLeast60": len(qualifying), "candidatesScored": len(model.raw_scores),
                   "candidateIds": [s["caseStudyId"] for s in model.raw_scores],
                   "allScores": sorted((s["score"] for s in model.raw_scores), reverse=True),
                   "briefModel": deps.brief_model,
                   "checkRepairs": len(failed_checks), "failedChecks": [x for f in failed_checks for x in f],
                   "jsonRepairs": dict(model.json_repairs),
                   "usage": model.usage, "brief": final}
        _print_brief(final, bu, summary, out)
        return summary


def _report_failure(brief: dict[str, Any], out) -> dict[str, Any]:
    err = brief.get("error") or {}
    print(f"Brief FAILED at {err.get('step')}: {err.get('code')} - {err.get('message')}", file=out)
    return {"status": brief["status"], "error": err}


def _print_brief(brief: dict[str, Any], bu: str, summary: dict[str, Any], out) -> None:
    content = brief["content"]
    research = brief["research"]
    invite = brief["confirmedInvite"]
    p = lambda line="": print(line, file=out)  # noqa: E731
    p("=" * 78)
    p(f"DISCOVERY BRIEF: {research['company']['name']} ({research['company']['domain']})   BU: {bu}")
    p(f"Meeting: {invite.get('subject') or '-'}   Date: {invite.get('meetingDate') or 'not given'}")
    p(f"Match confidence: {research['company']['matchConfidence']}")
    p("=" * 78)

    p("\n1. COMPANY SNAPSHOT")
    for item in content["companySnapshot"]:
        p(f"  - {item['text']}")
        for url in item["sourceUrls"]:
            p(f"      source: {url}")

    p("\n2. ATTENDEES")
    for a in content["attendees"]:
        p(f"  - {a['name']}, {a['title'] or '(no title given)'} <{a['email']}>")

    p("\n3. PAIN-POINT HYPOTHESES")
    for h in content["painPointHypotheses"]:
        p(f"  - {h['text']}")
        for url in h["sourceUrls"]:
            p(f"      based on: {url}")

    p("\n4. AGENDA (30 min)")
    for a in content["agenda"]:
        p(f"  {a['minutes']:>2} min  {a['topic']}: {a['note']}")
    p(f"  total: {sum(a['minutes'] for a in content['agenda'])} min")

    p("\n5. DISCOVERY QUESTIONS")
    for i, q in enumerate(content["discoveryQuestions"], 1):
        p(f"  {i:>2}. {q['text']}")

    p("\n6. CASE STUDIES TO MENTION")
    scores = {m["caseStudyId"]: m["score"] for m in brief["caseStudyMatches"]["matches"]}
    for cs in content["caseStudies"]:
        p(f"  - [{scores.get(cs['caseStudyId'], '?')}] {cs['title']}")
        p(f"      why: {cs['reason']}")
        p(f"      link: {cs['url']}")
    if content.get("caseStudiesNote"):
        p(f"  note: {content['caseStudiesNote']}")

    p("\n7. SOURCES")
    for s in content["sources"]:
        p(f"  - {s['label']}: {s['url']}")

    if brief.get("rulesApplied"):
        p("\nRules applied: " + "; ".join(r["text"] for r in brief["rulesApplied"]))
    t = summary["timing"]
    p("\n" + "-" * 78)
    p(f"Time: parse {t['parseSeconds']} s + pipeline {t['pipelineSeconds']} s = {t['totalSeconds']} s total")
    p("Steps: " + ", ".join(f"{name} {secs} s" for name, secs in summary["steps"]))
    p(f"Case studies scoring 60 or more: {summary['scoredAtLeast60']} of {summary['candidatesScored']} candidates scored "
      f"(top {len(content['caseStudies'])} shown). All scores: {summary['allScores']}")
    p(f"Brief model: {summary['briefModel']}. Check repairs: {summary['checkRepairs']} {summary['failedChecks'] or ''}. "
      f"JSON repairs: {summary['jsonRepairs'] or 0}")
    for model, u in summary["usage"].items():
        p(f"Bedrock {model}: {u['calls']} calls, {u['inputTokens']} input tokens, {u['outputTokens']} output tokens")


def main(argv: list[str] | None = None) -> int:
    from .src.lib import constants as c

    parser = argparse.ArgumentParser(description="Run the copilot locally on one invite.")
    parser.add_argument("invite", help="path to an invite text file")
    parser.add_argument("--bu", required=True, choices=c.BUSINESS_UNITS, help="the business unit of the signed-in SE")
    parser.add_argument("--fake-bedrock", action="store_true", help="use the offline model instead of Bedrock")
    parser.add_argument("--fixtures", action="store_true", help="read recorded research instead of the live web")
    parser.add_argument("--rule", action="append", default=[], help="a saved rule to apply (repeatable)")
    parser.add_argument("--json", action="store_true", help="also print the result as JSON")
    parser.add_argument("--brief-model", choices=c.BRIEF_MODELS, help="model that writes the brief (default: BRIEF_MODEL or cdk.json)")
    args = parser.parse_args(argv)
    result = run(args.invite, args.bu, fake=args.fake_bedrock, fixtures=args.fixtures, rules=args.rule,
                 brief_model=args.brief_model)
    if args.json:
        print(json.dumps({k: v for k, v in result.items() if k != "brief"}, indent=2))
    return 0 if result.get("status") == c.STATUS_READY else 1


if __name__ == "__main__":
    sys.exit(main())
