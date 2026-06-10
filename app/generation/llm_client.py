import hashlib
import json


class MockLLMClient:
    """Deterministic smoke-test LLM; never use for a formal EVALUATION_REPORT."""

    def generate(self, prompt: str) -> str:
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]
        payload = {
            "claims": [
                {
                    "claim_id": "claim-0001",
                    "text": "Mock response generated for schema and smoke tests only.",
                }
            ],
            "supporting_chunk_ids": [],
            "prompt_hash": prompt_hash,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

