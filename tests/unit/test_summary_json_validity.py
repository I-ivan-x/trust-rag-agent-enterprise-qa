from __future__ import annotations

import json
from pathlib import Path


def test_existing_eval_run_summaries_are_valid_json() -> None:
    for path in Path("data/eval_runs").glob("*/summary.json"):
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        assert isinstance(payload, dict)
        assert payload.get("run_id")

