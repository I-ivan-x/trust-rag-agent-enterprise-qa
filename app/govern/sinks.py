from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from app.govern.conditions import GovernanceAction, OpsCondition, RiskTier

ApprovalState = Literal["committed", "pending_approval", "escalated"]

ACTION_STORE_DIR = Path("data/action_store")


class ActionRecord(BaseModel):
    record_id: str
    action: GovernanceAction
    condition: OpsCondition | None = None
    doc_ids: list[str] = Field(default_factory=list)
    evidence_citations: list[str] = Field(default_factory=list)
    actor_role: str
    risk_tier: RiskTier
    approval_state: ApprovalState
    dedup_key: str
    created_at: str


class ActionSink(Protocol):
    def record_action(
        self,
        *,
        action: GovernanceAction,
        condition: OpsCondition | None,
        doc_ids: Sequence[str],
        evidence_citations: Sequence[str],
        actor_role: str,
        risk_tier: RiskTier,
        approval_state: ApprovalState,
    ) -> ActionRecord: ...


class LocalJsonlSink:
    def __init__(self, root: Path = ACTION_STORE_DIR) -> None:
        self.root = root

    def create_ticket(
        self,
        *,
        condition: OpsCondition,
        doc_ids: Sequence[str],
        evidence_citations: Sequence[str],
        actor_role: str,
    ) -> ActionRecord:
        return self.record_action(
            action=GovernanceAction.open_remediation_ticket,
            condition=condition,
            doc_ids=doc_ids,
            evidence_citations=evidence_citations,
            actor_role=actor_role,
            risk_tier=RiskTier.approval,
            approval_state="pending_approval",
        )

    def send_alert(
        self,
        *,
        condition: OpsCondition,
        doc_ids: Sequence[str],
        evidence_citations: Sequence[str],
        actor_role: str,
    ) -> ActionRecord:
        return self.record_action(
            action=GovernanceAction.send_alert,
            condition=condition,
            doc_ids=doc_ids,
            evidence_citations=evidence_citations,
            actor_role=actor_role,
            risk_tier=RiskTier.approval,
            approval_state="pending_approval",
        )

    def flag_document(
        self,
        *,
        condition: OpsCondition,
        doc_ids: Sequence[str],
        evidence_citations: Sequence[str],
        actor_role: str,
    ) -> ActionRecord:
        return self.record_action(
            action=GovernanceAction.flag_stale,
            condition=condition,
            doc_ids=doc_ids,
            evidence_citations=evidence_citations,
            actor_role=actor_role,
            risk_tier=RiskTier.auto,
            approval_state="committed",
        )

    def escalate(
        self,
        *,
        condition: OpsCondition | None,
        doc_ids: Sequence[str],
        evidence_citations: Sequence[str],
        actor_role: str,
    ) -> ActionRecord:
        return self.record_action(
            action=GovernanceAction.escalate_to_human,
            condition=condition,
            doc_ids=doc_ids,
            evidence_citations=evidence_citations,
            actor_role=actor_role,
            risk_tier=RiskTier.terminal,
            approval_state="escalated",
        )

    def record_action(
        self,
        *,
        action: GovernanceAction,
        condition: OpsCondition | None,
        doc_ids: Sequence[str],
        evidence_citations: Sequence[str],
        actor_role: str,
        risk_tier: RiskTier,
        approval_state: ApprovalState,
    ) -> ActionRecord:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path_for(action)
        path.touch(exist_ok=True)
        dedup_key = _dedup_key(action=action, condition=condition, doc_ids=doc_ids)
        existing = _find_existing(path, dedup_key)
        if existing is not None:
            return existing

        record_id = f"{action.value}-{_record_hash(dedup_key)}"
        record = ActionRecord(
            record_id=record_id,
            action=action,
            condition=condition,
            doc_ids=sorted(set(doc_ids)),
            evidence_citations=list(dict.fromkeys(evidence_citations)),
            actor_role=actor_role,
            risk_tier=risk_tier,
            approval_state=approval_state,
            dedup_key=dedup_key,
            created_at=datetime.now(UTC).isoformat(),
        )
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.model_dump(mode="json"), sort_keys=True) + "\n")
        return record

    def _path_for(self, action: GovernanceAction) -> Path:
        filename = {
            GovernanceAction.flag_stale: "annotations.jsonl",
            GovernanceAction.open_remediation_ticket: "tickets.jsonl",
            GovernanceAction.send_alert: "alerts.jsonl",
            GovernanceAction.escalate_to_human: "escalations.jsonl",
        }.get(action)
        if filename is None:
            raise ValueError(f"unsupported sink action: {action}")
        return self.root / filename


def _find_existing(path: Path, dedup_key: str) -> ActionRecord | None:
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if payload.get("dedup_key") == dedup_key:
            return ActionRecord.model_validate(payload)
    return None


def _dedup_key(
    *,
    action: GovernanceAction,
    condition: OpsCondition | None,
    doc_ids: Sequence[str],
) -> str:
    raw = "|".join(
        [
            action.value,
            condition.value if condition is not None else "none",
            ",".join(sorted(set(doc_ids))),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _record_hash(dedup_key: str) -> str:
    return hashlib.sha256(dedup_key.encode("utf-8")).hexdigest()[:8]
