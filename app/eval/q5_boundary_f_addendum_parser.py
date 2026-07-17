"""Versioned runtime-only parser for the frozen Boundary F addendum scope."""

from __future__ import annotations

import re

from app.schemas.q5_frontier import FrontierDisposition
from app.schemas.q5_frontier_v6 import PracticalParserResult, PracticalRuntimeInput

_STATUS = re.compile(r"\b(?:signal|neutral)_[0-9]+\b", re.IGNORECASE)
_NO_ACTION_FORMS = (
    r"governance (?:state )?(?:unchanged|untouched)",
    r"preserv(?:e|es).{0,32}(?:state|decision)",
    r"no governance change",
    r"leave.{0,24}unchanged",
    r"keep(?:s|ing)?\s+(?:the\s+)?(?:(?:present|current)\s+)?"
    r"(?:governed\s+)?(?:state|governance)\s+unchanged",
)
_ACTION_CUES = {
    FrontierDisposition.mark_stale: re.compile(
        r"(?:classif(?:y|ies).{0,28}stale|mak(?:e|es).{0,20}stale|"
        r"marks?.{0,24}obsolete|retire.{0,24}stale|stale classification)",
        re.IGNORECASE,
    ),
    FrontierDisposition.remediate: re.compile(
        r"(?:remediat(?:e|ion)|corrective (?:work|handling)|starts? corrective)",
        re.IGNORECASE,
    ),
    FrontierDisposition.notify: re.compile(
        r"(?:send(?:ing|s)?.{0,32}(?:notice|advisory)|notif(?:y|ying|ication).{0,32}"
        r"(?:channel|result)?|governance advisory|policy notice|required notice)",
        re.IGNORECASE,
    ),
    FrontierDisposition.no_action: re.compile(
        "(?:" + "|".join(_NO_ACTION_FORMS) + ")",
        re.IGNORECASE,
    ),
}


def independent_runtime_challenger_v2(
    runtime: PracticalRuntimeInput,
) -> PracticalParserResult:
    """Compose one status predicate with two ordered, morphological action cues."""

    if not runtime.observation.successful or not runtime.observation.authorized:
        return PracticalParserResult(
            status="complete",
            reason="host safety facts require review",
            disposition=FrontierDisposition.human_review,
        )
    status_matches = list(_STATUS.finditer(runtime.policy_text))
    if len(status_matches) != 1:
        return _abstain("requires exactly one symbolic status predicate")
    actions = []
    for disposition, pattern in _ACTION_CUES.items():
        if match := pattern.search(runtime.policy_text):
            actions.append((match.start(), disposition))
    actions.sort(key=lambda item: item[0])
    if len(actions) != 2 or actions[0][1] == actions[1][1]:
        return _abstain("requires exactly two distinct deontic action cues")
    condition_precedes_actions = status_matches[0].start() < actions[0][0]
    true_action, false_action = (
        (actions[0][1], actions[1][1])
        if condition_precedes_actions
        else (actions[1][1], actions[0][1])
    )
    matched = runtime.observation.status == status_matches[0].group(0).lower()
    disposition = true_action if matched else false_action
    if disposition not in runtime.legal_dispositions:
        return PracticalParserResult(status="unsafe", reason="compiled result is not legal")
    return PracticalParserResult(
        status="complete",
        reason="composed status predicate and morphological action cues",
        disposition=disposition,
    )


def _abstain(reason: str) -> PracticalParserResult:
    return PracticalParserResult(status="abstain", reason=reason)
