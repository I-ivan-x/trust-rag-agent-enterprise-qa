"""Fail when the public claim registry or generated views drift."""

# ruff: noqa: E402, I001

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.eval.public_claims import build_public_claims  # noqa: E402


if __name__ == "__main__":
    print(json.dumps(build_public_claims(check=True), sort_keys=True))
