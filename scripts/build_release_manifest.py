"""Build or verify the versioned Agent Reliability Lab release manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.eval.release_manifest import (  # noqa: E402
    CLEAN_CLONE_RECEIPT_PATH,
    RELEASE_MANIFEST_PATH,
    verify_release_manifest,
    write_release_manifest,
    write_release_schema,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("schema", "build", "verify"))
    parser.add_argument("--tested-commit", default="HEAD")
    parser.add_argument("--receipt", type=Path, default=CLEAN_CLONE_RECEIPT_PATH)
    parser.add_argument("--output", type=Path, default=RELEASE_MANIFEST_PATH)
    args = parser.parse_args()
    if args.command == "schema":
        result = {"schema_path": write_release_schema().relative_to(ROOT).as_posix()}
    elif args.command == "build":
        write_release_schema()
        manifest = write_release_manifest(
            tested_commit=args.tested_commit,
            clean_clone_receipt=args.receipt,
            output=args.output,
        )
        result = manifest.model_dump(mode="json")
    else:
        result = verify_release_manifest(args.output)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
