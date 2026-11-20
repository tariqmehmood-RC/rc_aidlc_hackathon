"""Saved rules (requirements R7.6 to R7.15, R6.6; design 5.1 and prompt P5).

A rule is a short reusable instruction learned from the SE's edits, for example "Always ask
about the budget cycle". Rules belong to one user. Every read and delete is keyed by userId, so
one user can never see or delete another user's rules.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from typing import Any, Callable, Iterable, Sequence

from botocore.exceptions import ClientError

from ..lib import constants as c

# --- ids --------------------------------------------------------------------------------------
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid(now_ms: int | None = None, random_bytes: Callable[[int], bytes] = os.urandom) -> str:
    """26 character id that sorts by creation time (48 bit time, 80 bit random)."""
    ms = int(time.time() * 1000) if now_ms is None else now_ms
    value = (ms << 80) | int.from_bytes(random_bytes(10), "big")
    return "".join(_CROCKFORD[(value >> shift) & 31] for shift in range(125, -1, -5))


def text_key(text: str) -> str:
    """Lowercase, single spaces, no trailing punctuation or quotes. Used to spot duplicates."""
    t = re.sub(r"\s+", " ", text.strip().lower())
    return t.strip(" \"'.!?;:,")


def clean_rule_text(text: Any) -> str:
    if not isinstance(text, str):
        raise ValueError("rule text must be a string")
    t = re.sub(r"\s+", " ", text).strip()
    if not t or len(t) > c.MAX_RULE_CHARS:
        raise ValueError(f"rule text must be 1 to {c.MAX_RULE_CHARS} characters")
    return t


# --- storage -----------------------------------------------------------------------------------
class RulesStore:
    def __init__(self, table, clock: Callable[[], float] = time.time,
                 ulid: Callable[[int], str] = lambda ms: new_ulid(ms)):
        self.table = table
        self._clock = clock
        self._ulid = ulid

    @staticmethod
    def _public(item: dict[str, Any]) -> dict[str, Any]:
        out = {"ruleId": item["ruleId"], "text": item["text"], "createdAt": int(item["createdAt"])}
        if item.get("sourceBriefId"):
            out["sourceBriefId"] = item["sourceBriefId"]
        return out

    def list_newest(self, user_id: str, limit: int = c.MAX_RULES_APPLIED) -> list[dict[str, Any]]:
        """The user's newest rules, newest first. The brief writer uses the newest 10 (R6.6)."""
        resp = self.table.query(
            KeyConditionExpression="userId = :u", ExpressionAttributeValues={":u": user_id},
            ScanIndexForward=False, Limit=limit,
        )
        return [self._public(i) for i in resp["Items"]]

    def list_all(self, user_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        kwargs: dict[str, Any] = dict(
            KeyConditionExpression="userId = :u", ExpressionAttributeValues={":u": user_id},
            ScanIndexForward=False,
        )
        while True:
            resp = self.table.query(**kwargs)
            items += resp["Items"]
            if "LastEvaluatedKey" not in resp:
                break
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        return [self._public(i) for i in items]

    def add(self, user_id: str, text: str, source_brief_id: str | None = None) -> dict[str, Any] | None:
        """Save a rule. Returns None when the user already has the same rule (R7.12)."""
        clean = clean_rule_text(text)
        key = text_key(clean)
        existing = self.table.query(
            KeyConditionExpression="userId = :u", ExpressionAttributeValues={":u": user_id},
            ProjectionExpression="textKey",
        )["Items"]
        # (a user has very few rules, so one query page is enough to compare against)
        if any(i.get("textKey") == key for i in existing):
            return None
        now_ms = int(self._clock() * 1000)
        item = {"userId": user_id, "ruleId": self._ulid(now_ms), "text": clean, "textKey": key, "createdAt": now_ms}
        if source_brief_id:
            item["sourceBriefId"] = source_brief_id
        self.table.put_item(Item=item)
        return self._public(item)

    def delete(self, user_id: str, rule_id: str) -> bool:
        """Delete one of the user's own rules. False if it does not exist for this user."""
        try:
            self.table.delete_item(
                Key={"userId": user_id, "ruleId": rule_id},
                ConditionExpression="attribute_exists(ruleId)",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise
        return True


# --- proposals: keep or discard ----------------------------------------------------------------
def apply_decisions(store: RulesStore, user_id: str, proposals: Sequence[dict[str, Any]],
                    decisions: Iterable[dict[str, Any]], source_brief_id: str | None = None) -> list[dict[str, Any]]:
    """Save the proposals the SE kept. Unknown proposal ids are ignored. Returns the saved rules."""
    by_id = {p["proposalId"]: p for p in proposals}
    saved: list[dict[str, Any]] = []
    seen: set[str] = set()
    for d in decisions:
        pid = d.get("proposalId")
        if pid in seen or pid not in by_id or d.get("keep") is not True:
            continue
        seen.add(pid)
        rule = store.add(user_id, by_id[pid]["text"], source_brief_id)
        if rule:
            saved.append(rule)
    return saved


# --- prompt P5: propose rules from the edits ---------------------------------------------------
P5_SYSTEM = (
    "You are given the changes a sales engineer made to a draft discovery brief, as before and "
    "after values of the items they changed. Propose 0 to 3 short, reusable instructions (each "
    "under 200 characters, imperative, not tied to this company) that would make future drafts "
    "match the user's edits, for example 'Always ask about the budget cycle'. If the changes are "
    "only company-specific corrections or typos, return none. Do not repeat the existing rules."
)
P5_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["rules"],
    "additionalProperties": False,
    "properties": {
        "rules": {
            "type": "array", "maxItems": c.MAX_RULE_PROPOSALS,
            "items": {
                "type": "object", "required": ["text", "rationale"], "additionalProperties": False,
                "properties": {
                    "text": {"type": "string", "maxLength": c.MAX_RULE_CHARS},
                    "rationale": {"type": "string", "maxLength": 200},
                },
            },
        }
    },
}

EDITABLE_FIELDS = {
    "companySnapshot": ("text",),
    "painPointHypotheses": ("text",),
    "agenda": ("minutes", "topic", "note"),
    "discoveryQuestions": ("text",),
}


def _norm(value: Any) -> Any:
    return re.sub(r"\s+", " ", value).strip() if isinstance(value, str) else value


def _pick(item: dict[str, Any], fields: Sequence[str]) -> dict[str, Any]:
    return {f: _norm(item.get(f)) for f in fields}


def diff_content(draft: dict[str, Any], final: dict[str, Any]) -> list[dict[str, Any]]:
    """The edits between draft and final, limited to the parts an SE can edit."""
    changes: list[dict[str, Any]] = []
    for section, fields in EDITABLE_FIELDS.items():
        d_items = {i.get("id"): i for i in draft.get(section, []) if isinstance(i, dict) and i.get("id")}
        f_list = [i for i in final.get(section, []) if isinstance(i, dict)]
        f_ids = set()
        for n, item in enumerate(f_list):
            iid = item.get("id") or f"new-{n}"
            f_ids.add(iid)
            after = _pick(item, fields)
            if iid not in d_items:
                changes.append({"section": section, "change": "added", "after": after})
                continue
            before = _pick(d_items[iid], fields)
            if before != after:
                changes.append({"section": section, "change": "edited", "before": before, "after": after})
        for iid, item in d_items.items():
            if iid not in f_ids:
                changes.append({"section": section, "change": "removed", "before": _pick(item, fields)})
    return changes


_CLOSE_RE = re.compile(r"</\s*(changes|existing_rules)\s*>", re.IGNORECASE)


def extract_rules(bedrock, draft: dict[str, Any], final: dict[str, Any], existing_rules: Sequence[str],
                  id_factory: Callable[[], str] = lambda: uuid.uuid4().hex[:12]) -> list[dict[str, str]]:
    """Return 0 to 3 proposals `{proposalId, text, rationale}`. No Bedrock call if nothing changed (R7.9)."""
    changes = diff_content(draft, final)
    if not changes:
        return []

    esc = lambda t: _CLOSE_RE.sub("&lt;/\\1&gt;", t)  # noqa: E731
    user = (
        "<existing_rules>\n" + "\n".join(f"- {esc(r)}" for r in existing_rules) + "\n</existing_rules>\n"
        "<changes>\n" + esc(json.dumps(changes, ensure_ascii=False)) + "\n</changes>"
    )
    out = bedrock.converse_json(
        model=c.MODEL_HAIKU, system=P5_SYSTEM, user=user,
        max_tokens=c.MAX_TOKENS["rules"], schema=P5_SCHEMA,
    )

    known = {text_key(r) for r in existing_rules}
    proposals: list[dict[str, str]] = []
    for r in out["rules"]:
        try:
            text = clean_rule_text(r["text"])
        except ValueError:
            continue
        key = text_key(text)
        if key in known:
            continue  # same as a saved rule or an earlier proposal
        known.add(key)
        proposals.append({"proposalId": id_factory(), "text": text, "rationale": r["rationale"].strip()})
        if len(proposals) == c.MAX_RULE_PROPOSALS:
            break
    return proposals
