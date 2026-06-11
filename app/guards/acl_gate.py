from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.enums import AccessLevel
from app.schemas.retrieval import RetrievedChunk

_CLEARANCE_ORDER = {
    AccessLevel.public.value: 0,
    AccessLevel.internal.value: 1,
    AccessLevel.confidential.value: 2,
    AccessLevel.restricted.value: 3,
}


class ACLGateDecision(BaseModel):
    surviving_chunks: list[RetrievedChunk] = Field(default_factory=list)
    blocked_chunks: list[RetrievedChunk] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def apply_acl_gate(
    chunks: list[RetrievedChunk],
    user_role: str,
    user_department: str | None = None,
    user_clearance: str | None = None,
) -> ACLGateDecision:
    surviving_chunks: list[RetrievedChunk] = []
    blocked_chunks: list[RetrievedChunk] = []
    warnings: list[str] = []
    clearance = _normalize_clearance(user_clearance)
    normalized_role = user_role.strip().lower()

    for result in chunks:
        chunk = result.chunk
        if _is_allowed(
            access_level=chunk.access_level,
            allowed_roles=chunk.allowed_roles,
            user_role=normalized_role,
            user_clearance=clearance,
        ):
            surviving_chunks.append(result)
            continue
        blocked_chunks.append(result)
        warnings.append(
            "ACL blocked chunk "
            f"{chunk.chunk_id}: access_level={chunk.access_level.value} "
            f"user_role={user_role} user_department={user_department or 'unknown'}"
        )

    return ACLGateDecision(
        surviving_chunks=surviving_chunks,
        blocked_chunks=blocked_chunks,
        warnings=warnings,
    )


def _is_allowed(
    access_level: AccessLevel,
    allowed_roles: list[str],
    user_role: str,
    user_clearance: str,
) -> bool:
    if access_level == AccessLevel.public:
        return True
    if access_level == AccessLevel.internal:
        return _clearance_rank(user_clearance) >= _clearance_rank(AccessLevel.internal.value)
    if access_level == AccessLevel.confidential:
        return _clearance_rank(user_clearance) >= _clearance_rank(AccessLevel.confidential.value)
    if access_level == AccessLevel.restricted:
        return user_role in {role.lower() for role in allowed_roles}
    return False


def _normalize_clearance(user_clearance: str | None) -> str:
    if not user_clearance:
        return AccessLevel.public.value
    normalized = user_clearance.strip().lower()
    return normalized if normalized in _CLEARANCE_ORDER else AccessLevel.public.value


def _clearance_rank(clearance: str) -> int:
    return _CLEARANCE_ORDER.get(clearance, 0)
