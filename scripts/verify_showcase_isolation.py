"""Verify the synthetic interview showcase and its formal-claim isolation."""

# ruff: noqa: E402, I001

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.eval.showcase_corpus import verify_interview_showcase


if __name__ == "__main__":
    print(json.dumps(verify_interview_showcase(), ensure_ascii=False, sort_keys=True))
