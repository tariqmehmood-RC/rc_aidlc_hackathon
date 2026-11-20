"""SQS worker Lambda. The only function that calls Amazon Bedrock (design 7).

Settings in CDK: reserved concurrency 1, batch size 1, timeout 180 s. Configuration comes from
environment variables set by CDK. No secrets.
"""
from __future__ import annotations

import json
import os
from typing import Any

from ..lib.bedrock_client import BedrockClient
from ..lib.brief_store import BriefStore
from ..lib.observability import PowertoolsMetrics, bind_brief, bind_request, get_logger
from ..lib.profiles import load_profiles
from ..services import pipeline
from ..services.brief_writer import brief_model_from_env
from ..services.case_study_matcher import load_case_studies
from ..services.research import ResearchService
from ..services.research_provider import PublicWebProvider
from ..services.rules import RulesStore

REGION = "us-east-1"
logger = get_logger(service="worker")
_deps: pipeline.Deps | None = None
_metrics: PowertoolsMetrics | None = None


def _build_deps() -> pipeline.Deps:
    """Created once per container. The Bedrock client, and so its rate limiter, is shared by
    every job this container runs."""
    import boto3

    global _metrics
    ddb = boto3.resource("dynamodb", region_name=REGION)
    _metrics = PowertoolsMetrics()
    bedrock = BedrockClient(metrics=_metrics)
    return pipeline.Deps(
        store=BriefStore(ddb.Table(os.environ["BRIEFS_TABLE"])),
        research=ResearchService(bedrock, PublicWebProvider(), ddb.Table(os.environ["RESEARCH_CACHE_TABLE"])),
        bedrock=bedrock,
        rules=RulesStore(ddb.Table(os.environ["RULES_TABLE"])),
        studies=load_case_studies(),
        profiles=load_profiles(),
        metrics=_metrics,
        log=lambda event, data: logger.info(event, extra=data),
        brief_model=brief_model_from_env(),
    )


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    global _deps
    if _deps is None:
        _deps = _build_deps()
    if context is not None:
        bind_request(logger, getattr(context, "aws_request_id", "-"))
    outcomes = []
    try:
        for record in event.get("Records", []):
            try:
                body = json.loads(record["body"])
            except (KeyError, TypeError, ValueError):
                logger.warning("message_unreadable")
                outcomes.append("invalid")
                continue
            bind_brief(logger, str(body.get("briefId", "-")) if isinstance(body, dict) else "-")
            outcomes.append(pipeline.handle_message(body, _deps))
    finally:
        if _metrics is not None:
            _metrics.flush()
    return {"outcomes": outcomes}
