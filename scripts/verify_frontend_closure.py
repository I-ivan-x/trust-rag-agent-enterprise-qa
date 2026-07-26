"""Verify the tracked frontend closure receipt and viewport screenshots."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "frontend/acceptance/frontend-closure/receipt.json"


def verify_frontend_closure(root: Path = ROOT) -> dict:
    receipt = root / RECEIPT.relative_to(ROOT)
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "frontend-closure-acceptance-v1":
        raise ValueError("unsupported frontend closure receipt")
    if (
        payload.get("model_requests") != 0
        or payload.get("external_requests") != 0
        or not payload.get("hard_thresholds_passed")
    ):
        raise ValueError("frontend closure request or threshold contract failed")
    screenshots = payload.get("screenshots", [])
    if len(screenshots) != 3:
        raise ValueError("frontend closure must bind exactly three screenshots")
    paths = [row["path"] for row in screenshots]
    if len(paths) != len(set(paths)):
        raise ValueError("frontend closure screenshot paths are duplicated")
    for row in screenshots:
        target = root / row["path"]
        if not target.is_file():
            raise ValueError(f"frontend screenshot is missing: {row['path']}")
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != row["sha256"]:
            raise ValueError(f"frontend screenshot hash mismatch: {row['path']}")
    runs = payload.get("lighthouse_runs", [])
    if len(runs) != 3 or any(
        row.get("performance", 0) < 90
        or row.get("accessibility", 0) < 90
        or row.get("external_requests") != 0
        for row in runs
    ):
        raise ValueError("frontend closure Lighthouse matrix failed")
    return {
        "schema_version": payload["schema_version"],
        "tested_commit": payload["tested_commit"],
        "tested_tree": payload["tested_tree"],
        "screenshot_count": len(screenshots),
        "lighthouse_run_count": len(runs),
        "model_requests": payload["model_requests"],
        "external_requests": payload["external_requests"],
        "status": "passed",
    }


if __name__ == "__main__":
    print(json.dumps(verify_frontend_closure(), indent=2, sort_keys=True))
