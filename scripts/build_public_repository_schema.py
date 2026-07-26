"""Generate the strict public-repository audit registry schema."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.eval.public_repository_audit import write_public_registry_schema  # noqa: E402


def main() -> None:
    target = write_public_registry_schema()
    print(
        json.dumps(
            {"schema_path": target.relative_to(ROOT).as_posix()},
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
