# ruff: noqa: E402

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.schemas.chat import ChatRequest
from app.service.chat_service import answer_chat

DEMO_CASES = [
    {
        "case_id": "single_doc_fact",
        "query": "What is the refresh token rate limit in Auth Service API v2?",
        "user_role": "employee",
        "user_department": "Engineering",
        "user_clearance": "internal",
    },
    {
        "case_id": "no_evidence",
        "query": "How do I configure Kubernetes autoscaling?",
        "user_role": "employee",
        "user_department": "Engineering",
        "user_clearance": "internal",
    },
    {
        "case_id": "permission_denied",
        "query": "How often must admin keys be rotated?",
        "user_role": "employee",
        "user_department": "Engineering",
        "user_clearance": "internal",
    },
    {
        "case_id": "deprecated_doc",
        "query": "What was the v1 access token lifetime?",
        "user_role": "employee",
        "user_department": "Engineering",
        "user_clearance": "internal",
    },
    {
        "case_id": "conflict_doc",
        "query": "What is the access token lifetime during the v2 migration?",
        "user_role": "employee",
        "user_department": "Engineering",
        "user_clearance": "internal",
    },
    {
        "case_id": "obfuscated_rewrite",
        "query": "refresh rlimit",
        "user_role": "employee",
        "user_department": "Engineering",
        "user_clearance": "internal",
    },
]


def main() -> None:
    print(
        "Week 4 demo queries are functional smoke checks only; "
        "do not report these fixture outputs as formal metrics."
    )
    for case in DEMO_CASES:
        request = ChatRequest.model_validate(
            {
                **case,
                "retrieval_options": {
                    "top_k": 8,
                    "top_n_rerank": 4,
                    "return_retrieved_chunks": False,
                    "max_rewrite_rounds": 1,
                },
            }
        )
        response = answer_chat(request)
        print(json.dumps(_summarize(case, response), ensure_ascii=False, sort_keys=True))


def _summarize(case: dict[str, Any], response) -> dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "query": case["query"],
        "response_mode": response.response_mode.value,
        "answer_preview": response.answer[:140],
        "citation_chunk_ids": [citation.chunk_id for citation in response.citations],
        "trace_id": response.trace_id,
        "rewrite_triggered": response.trust_trace.get("rewrite_triggered", False),
        "decision_reason": response.decision.reason.value,
    }


if __name__ == "__main__":
    main()
