"""Access to the Briefs table (design 5.1, status flow in design 3).

Every state change is a conditional update, so a duplicate queue message, a stale job, or two
requests at once cannot overwrite newer data (R9.13). Structured fields (research, content and
so on) are stored as JSON text. DynamoDB rejects Python floats, and a brief is always read and
written whole, so this keeps the data simple.
"""
from __future__ import annotations

import base64
import json
import re
import time
import uuid
from typing import Any, Callable, Iterable, Sequence

from botocore.exceptions import ClientError

from . import constants as c

JSON_FIELDS = (
    "parsedInvite", "confirmedInvite", "research", "attendeeChecks", "caseStudyMatches",  # attendeeChecks: old briefs only
    "draft", "content", "rulesApplied", "ruleProposals", "error",
)
QUEUE_KEY = "Q"

# Shape of the table. Tests create it from this, and the CDK stack must match it (task 5.2).
BRIEFS_TABLE_DEFINITION: dict[str, Any] = {
    "KeySchema": [{"AttributeName": "briefId", "KeyType": "HASH"}],
    "AttributeDefinitions": [
        {"AttributeName": "briefId", "AttributeType": "S"},
        {"AttributeName": "userId", "AttributeType": "S"},
        {"AttributeName": "createdAt", "AttributeType": "N"},
        {"AttributeName": "queueKey", "AttributeType": "S"},
        {"AttributeName": "queuedAt", "AttributeType": "N"},
    ],
    "GlobalSecondaryIndexes": [
        {"IndexName": "byUser",
         "KeySchema": [{"AttributeName": "userId", "KeyType": "HASH"}, {"AttributeName": "createdAt", "KeyType": "RANGE"}],
         "Projection": {"ProjectionType": "ALL"}},
        {"IndexName": "byQueue",
         "KeySchema": [{"AttributeName": "queueKey", "KeyType": "HASH"}, {"AttributeName": "queuedAt", "KeyType": "RANGE"}],
         "Projection": {"ProjectionType": "KEYS_ONLY"}},
    ],
    "BillingMode": "PAY_PER_REQUEST",
}


class InvalidCursor(ValueError):
    """The paging cursor is not one this service issued for this user."""


def _is_condition_failure(exc: ClientError) -> bool:
    return exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"


class BriefStore:
    def __init__(self, table, clock: Callable[[], float] = time.time,
                 id_factory: Callable[[], str] = lambda: uuid.uuid4().hex):
        self.table = table
        self._clock = clock
        self._new_id = id_factory

    # -- helpers --------------------------------------------------------------------------------
    def _now_ms(self) -> int:
        return int(self._clock() * 1000)

    def _update(self, brief_id: str, *, sets: dict[str, Any] | None = None, removes: Sequence[str] = (),
                condition: str, cond_values: dict[str, Any] | None = None,
                append_steps: Sequence[str] | None = None) -> bool:
        """Run one conditional update. Returns False if the condition did not hold."""
        names: dict[str, str] = {}
        values: dict[str, Any] = dict(cond_values or {})
        set_parts: list[str] = []
        for i, (key, value) in enumerate((sets or {}).items()):
            names[f"#s{i}"] = key
            values[f":s{i}"] = json.dumps(value, separators=(",", ":")) if key in JSON_FIELDS else value
            set_parts.append(f"#s{i} = :s{i}")
        if append_steps:
            names["#steps"] = "stepsCompleted"
            values[":steps"] = list(append_steps)
            values[":empty"] = []
            set_parts.append("#steps = list_append(if_not_exists(#steps, :empty), :steps)")
        remove_parts = []
        for i, key in enumerate(removes):
            names[f"#r{i}"] = key
            remove_parts.append(f"#r{i}")
        expression = "SET " + ", ".join(set_parts)
        if remove_parts:
            expression += " REMOVE " + ", ".join(remove_parts)
        # attribute names used in the condition
        for token in ("status", "currentJobId", "rulesStatus", "updatedAt", "version"):
            names[f"#{token}"] = token
        # DynamoDB rejects placeholders that are defined but not used, so keep only the used ones.
        full = f"{expression} {condition}"
        used_names = set(re.findall(r"#\w+", full))
        used_values = set(re.findall(r":\w+", full))
        try:
            self.table.update_item(
                Key={"briefId": brief_id},
                UpdateExpression=expression,
                ConditionExpression=f"attribute_exists(briefId) AND ({condition})",
                ExpressionAttributeNames={k: v for k, v in names.items() if k in used_names},
                ExpressionAttributeValues={k: v for k, v in values.items() if k in used_values},
            )
        except ClientError as exc:
            if _is_condition_failure(exc):
                return False
            raise
        return True

    @staticmethod
    def _decode(item: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in item.items():
            if key in JSON_FIELDS and isinstance(value, str):
                out[key] = json.loads(value)
            elif key == "stepsCompleted":
                out[key] = list(value)
            elif key in ("createdAt", "updatedAt", "queuedAt", "expiresAt", "version", "approvedAt") and value is not None:
                out[key] = int(value)
            else:
                out[key] = value
        return out

    # -- create and read -------------------------------------------------------------------------
    def create(self, user_id: str, bu: str | None, invite_text: str) -> tuple[dict[str, Any], str]:
        """Save a new brief as `queued`. Returns (brief, job id for the parse job)."""
        now_ms = self._now_ms()
        job_id = self._new_id()
        item: dict[str, Any] = {
            "briefId": self._new_id(),
            "userId": user_id,
            "status": c.STATUS_QUEUED,
            "currentJobId": job_id,
            "queueKey": QUEUE_KEY,
            "queuedAt": now_ms,
            "createdAt": now_ms,
            "updatedAt": now_ms,
            "expiresAt": now_ms // 1000 + c.BRIEF_TTL_DAYS * 24 * 3600,
            "inviteText": invite_text,
            "stepsCompleted": [],
            "rulesStatus": "none",
            "version": 0,
        }
        if bu:
            item["bu"] = bu
        self.table.put_item(Item=item, ConditionExpression="attribute_not_exists(briefId)")
        return self._decode(item), job_id

    def get(self, brief_id: str) -> dict[str, Any] | None:
        item = self.table.get_item(Key={"briefId": brief_id}, ConsistentRead=True).get("Item")
        if not item or int(item.get("expiresAt", 0)) <= self._now_ms() // 1000:
            return None
        return self._decode(item)

    def get_owned(self, brief_id: str, user_id: str) -> dict[str, Any] | None:
        """The brief, only if it belongs to this user. Same answer as 'does not exist' otherwise (R7.16)."""
        brief = self.get(brief_id)
        if brief is None or brief.get("userId") != user_id:
            return None
        return brief

    # -- worker transitions ----------------------------------------------------------------------------
    def begin_job(self, brief_id: str, job_id: str, expected_status: str, step: str | None = None) -> bool:
        """queued -> processing for this job. False for a stale or duplicate message."""
        sets: dict[str, Any] = {"status": c.STATUS_PROCESSING, "updatedAt": self._now_ms()}
        if step:
            sets["step"] = step
        return self._update(
            brief_id, sets=sets, removes=("queueKey",),
            condition="#currentJobId = :job AND #status = :expected",
            cond_values={":job": job_id, ":expected": expected_status},
        )

    def set_step(self, brief_id: str, job_id: str, step: str) -> bool:
        return self._update(
            brief_id, sets={"step": step, "updatedAt": self._now_ms()},
            condition="#currentJobId = :job AND #status = :processing",
            cond_values={":job": job_id, ":processing": c.STATUS_PROCESSING},
        )

    def complete_step(self, brief_id: str, job_id: str, step: str, fields: dict[str, Any] | None = None) -> bool:
        """Store a step's result and record it as done, in one write."""
        sets = dict(fields or {})
        sets["updatedAt"] = self._now_ms()
        return self._update(
            brief_id, sets=sets, append_steps=[step],
            condition="#currentJobId = :job AND #status = :processing",
            cond_values={":job": job_id, ":processing": c.STATUS_PROCESSING},
        )

    def finish(self, brief_id: str, job_id: str, new_status: str, fields: dict[str, Any] | None = None,
               completed_step: str | None = None) -> bool:
        """processing -> awaiting_confirmation or ready. Optionally records the last step as done."""
        if new_status not in (c.STATUS_AWAITING_CONFIRMATION, c.STATUS_READY):
            raise ValueError(f"finish() cannot set status {new_status!r}")
        sets = dict(fields or {})
        sets.update({"status": new_status, "updatedAt": self._now_ms()})
        return self._update(
            brief_id, sets=sets, removes=("step",), append_steps=[completed_step] if completed_step else None,
            condition="#currentJobId = :job AND #status = :processing",
            cond_values={":job": job_id, ":processing": c.STATUS_PROCESSING},
        )

    def fail(self, brief_id: str, job_id: str, code: str, step: str | None, message: str) -> bool:
        """Mark this job's brief failed (from queued or processing)."""
        return self._update(
            brief_id,
            sets={"status": c.STATUS_FAILED, "updatedAt": self._now_ms(),
                  "error": {"code": code, "step": step, "message": message}},
            removes=("step", "queueKey"),
            condition="#currentJobId = :job AND #status IN (:q, :p)",
            cond_values={":job": job_id, ":q": c.STATUS_QUEUED, ":p": c.STATUS_PROCESSING},
        )

    def set_rules_result(self, brief_id: str, job_id: str, rules_status: str,
                         proposals: Sequence[dict[str, Any]] | None = None) -> bool:
        """Result of the rule extraction job. Only while the rules are still pending for this job."""
        if rules_status not in ("ready", "none", "failed"):
            raise ValueError(f"unexpected rules status {rules_status!r}")
        sets: dict[str, Any] = {"rulesStatus": rules_status, "updatedAt": self._now_ms()}
        if proposals is not None:
            sets["ruleProposals"] = list(proposals)
        return self._update(
            brief_id, sets=sets,
            condition="#currentJobId = :job AND #rulesStatus = :pending AND #status = :approved",
            cond_values={":job": job_id, ":pending": "pending", ":approved": c.STATUS_APPROVED},
        )

    # -- API transitions ----------------------------------------------------------------------------------
    def requeue(self, brief_id: str, from_status: str, fields: dict[str, Any] | None = None,
                clear_error: bool = False) -> str | None:
        """Put a brief back in the queue under a new job id. Returns the job id, or None if the
        brief is not in `from_status` (used by confirm and retry)."""
        job_id = self._new_id()
        now = self._now_ms()
        sets = dict(fields or {})
        sets.update({"status": c.STATUS_QUEUED, "currentJobId": job_id, "queueKey": QUEUE_KEY,
                     "queuedAt": now, "updatedAt": now})
        ok = self._update(
            brief_id, sets=sets, removes=("step", "error") if clear_error else ("step",),
            condition="#status = :from",
            cond_values={":from": from_status},
        )
        return job_id if ok else None

    def save_parsed_invite(self, brief_id: str, parsed: dict[str, Any]) -> bool:
        """The SE's corrections to the parsed invite, saved without confirming."""
        return self._update(
            brief_id, sets={"parsedInvite": parsed, "updatedAt": self._now_ms()},
            condition="#status = :s", cond_values={":s": c.STATUS_AWAITING_CONFIRMATION},
        )

    def save_content(self, brief_id: str, content: dict[str, Any], expected_version: int) -> bool:
        """Save the SE's edits. Only while `ready`; the draft is never touched (R7.2)."""
        return self._update(
            brief_id, sets={"content": content, "version": expected_version + 1, "updatedAt": self._now_ms()},
            condition="#status = :s AND #version = :v",
            cond_values={":s": c.STATUS_READY, ":v": expected_version},
        )

    def approve(self, brief_id: str, final_content: dict[str, Any] | None = None) -> str | None:
        """ready -> approved and queue a rules job. Returns the new job id, or None."""
        job_id = self._new_id()
        sets: dict[str, Any] = {"status": c.STATUS_APPROVED, "rulesStatus": "pending",
                                "currentJobId": job_id, "approvedAt": self._now_ms(), "updatedAt": self._now_ms()}
        if final_content is not None:
            sets["content"] = final_content
        ok = self._update(brief_id, sets=sets, condition="#status = :ready", cond_values={":ready": c.STATUS_READY})
        return job_id if ok else None

    def set_rule_proposals_handled(self, brief_id: str) -> bool:
        """After the SE keeps or discards, the proposals are cleared so they cannot be applied twice."""
        return self._update(
            brief_id, sets={"ruleProposals": [], "rulesStatus": "none", "updatedAt": self._now_ms()},
            condition="#rulesStatus = :ready", cond_values={":ready": "ready"},
        )

    # -- progress and history --------------------------------------------------------------------------------
    def queue_position(self, brief: dict[str, Any]) -> int | None:
        """1 for the next brief to run. Only for `queued` briefs (R9.4)."""
        if brief.get("status") != c.STATUS_QUEUED or "queuedAt" not in brief:
            return None
        resp = self.table.query(
            IndexName="byQueue",
            KeyConditionExpression="queueKey = :q AND queuedAt < :t",
            ExpressionAttributeValues={":q": QUEUE_KEY, ":t": brief["queuedAt"]},
            Select="COUNT",
        )
        return int(resp["Count"]) + 1

    def expire_if_stuck(self, brief: dict[str, Any]) -> dict[str, Any]:
        """A `processing` brief with no progress for 120 s becomes `failed` (R9.9). A `queued`
        brief is never stuck: waiting in the queue is normal."""
        if brief.get("status") != c.STATUS_PROCESSING:
            return brief
        idle_s = (self._now_ms() - int(brief.get("updatedAt", 0))) / 1000
        if idle_s <= c.STUCK_SECONDS:
            return brief
        self._update(
            brief["briefId"],
            sets={"status": c.STATUS_FAILED, "updatedAt": self._now_ms(),
                  "error": {"code": "STUCK", "step": brief.get("step"),
                            "message": "The brief stopped making progress. You can retry it."}},
            removes=("step", "queueKey"),
            condition="#status = :p AND #updatedAt = :u",
            cond_values={":p": c.STATUS_PROCESSING, ":u": brief["updatedAt"]},
        )
        # If the update lost a race, someone changed the brief first: return the newer state.
        return self.get(brief["briefId"]) or brief

    def list_for_user(self, user_id: str, limit: int = c.PAGE_SIZE,
                      cursor: str | None = None) -> tuple[list[dict[str, Any]], str | None]:
        """The user's briefs, newest first, in pages (R8)."""
        limit = max(1, min(int(limit), c.PAGE_SIZE))
        kwargs: dict[str, Any] = dict(
            IndexName="byUser",
            KeyConditionExpression="userId = :u",
            ExpressionAttributeValues={":u": user_id},
            ScanIndexForward=False,
        )
        if cursor:
            kwargs["ExclusiveStartKey"] = self._decode_cursor(cursor, user_id)
        # Read one extra item so we know exactly whether another page exists.
        items: list[dict[str, Any]] = []
        now_s = self._now_ms() // 1000
        while len(items) < limit + 1:
            resp = self.table.query(**{**kwargs, "Limit": limit + 1 - len(items)})
            items += [i for i in resp["Items"] if int(i.get("expiresAt", 0)) > now_s]
            last_key = resp.get("LastEvaluatedKey")
            if not last_key:
                break
            kwargs["ExclusiveStartKey"] = last_key
        page = items[:limit]
        next_cursor = None
        if len(items) > limit:
            last = page[-1]
            next_cursor = self._encode_cursor(
                {"briefId": last["briefId"], "userId": last["userId"], "createdAt": last["createdAt"]})
        return [self._summary(self._decode(i)) for i in page], next_cursor

    @staticmethod
    def _encode_cursor(key: dict[str, Any]) -> str:
        plain = {k: (int(v) if k == "createdAt" else v) for k, v in key.items()}
        return base64.urlsafe_b64encode(json.dumps(plain).encode()).decode()

    @staticmethod
    def _decode_cursor(cursor: str, user_id: str) -> dict[str, Any]:
        try:
            key = json.loads(base64.urlsafe_b64decode(cursor.encode()))
            if set(key) != {"briefId", "userId", "createdAt"} or key["userId"] != user_id:
                raise ValueError
            if not isinstance(key["briefId"], str) or not isinstance(key["createdAt"], int):
                raise ValueError
        except (ValueError, TypeError, KeyError):
            raise InvalidCursor("invalid cursor") from None
        return key

    @staticmethod
    def _summary(brief: dict[str, Any]) -> dict[str, Any]:
        confirmed = brief.get("confirmedInvite") or brief.get("parsedInvite") or {}
        out = {
            "briefId": brief["briefId"],
            "companyName": (confirmed.get("company") or {}).get("name"),
            "meetingDate": confirmed.get("meetingDate"),
            "status": brief["status"],
            "createdAt": brief["createdAt"],
        }
        if brief["status"] == c.STATUS_FAILED and brief.get("error"):
            out["error"] = {"code": brief["error"].get("code"), "message": brief["error"].get("message")}
        return out

    # -- the API's view of a brief ---------------------------------------------------------------------------
    def view(self, brief: dict[str, Any], position: int | None = None) -> dict[str, Any]:
        """What GET /briefs/{id} returns. Fields appear only once they exist. Never includes the
        invite text, userId, or internal job ids."""
        out: dict[str, Any] = {
            "briefId": brief["briefId"], "status": brief["status"], "createdAt": brief["createdAt"],
            "rulesStatus": brief.get("rulesStatus", "none"), "version": brief.get("version", 0),
        }
        if brief.get("step"):
            out["step"] = brief["step"]
        if position is not None:
            out["queuePosition"] = position
        for key in ("parsedInvite", "confirmedInvite", "research", "caseStudyMatches",
                    "content", "rulesApplied", "ruleProposals", "error"):
            if key in brief:
                out[key] = brief[key]
        if brief["status"] != c.STATUS_FAILED:
            out.pop("error", None)
        return out
