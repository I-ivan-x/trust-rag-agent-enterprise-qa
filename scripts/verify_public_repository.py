# ruff: noqa: E402, I001
"""Run the fail-closed public repository and data-provenance audit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.eval.public_repository_audit import verify_public_repository  # noqa: E402


if __name__ == "__main__":
    print(json.dumps(verify_public_repository(), indent=2, sort_keys=True))
