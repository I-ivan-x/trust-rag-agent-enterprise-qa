from __future__ import annotations

import re

from pydantic import BaseModel, Field


class RewriteDecision(BaseModel):
    should_rewrite: bool
    rewritten_query: str | None = None
    reason: str
    warnings: list[str] = Field(default_factory=list)


def rewrite_query_for_evidence(query: str) -> RewriteDecision:
    normalized = query.strip()
    if not normalized:
        return RewriteDecision(
            should_rewrite=False,
            rewritten_query=None,
            reason="blank_query",
            warnings=["Blank query cannot be rewritten."],
        )

    rewritten = normalized
    rewrites = [
        (r"\btoken\s+ttl\b", "access token lifetime", "token_ttl"),
        (r"\btoken\s+expiry\b", "access token lifetime", "token_expiry"),
        (r"\brefresh\s+limit\b", "refresh token rate limit", "refresh_limit"),
        (r"\brefresh\s+rlimit\b", "refresh token rate limit", "refresh_rlimit"),
        (
            r"\badmin\s+key\s+rotation\b",
            "admin key rotation sop",
            "admin_key_rotation",
        ),
    ]
    reasons: list[str] = []
    for pattern, replacement, reason in rewrites:
        updated = re.sub(pattern, replacement, rewritten, flags=re.IGNORECASE)
        if updated != rewritten:
            rewritten = updated
            reasons.append(reason)

    if rewritten == normalized:
        return RewriteDecision(
            should_rewrite=False,
            rewritten_query=None,
            reason="no_rule_matched",
        )

    return RewriteDecision(
        should_rewrite=True,
        rewritten_query=rewritten,
        reason="rule_based:" + ",".join(reasons),
    )
