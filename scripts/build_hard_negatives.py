# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.corpus.hard_negative_builder import build_hard_negative_corpus


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Week 5A hard negative corpus.")
    parser.add_argument("--public-corpus", type=Path, default=Path("data/public_corpus"))
    parser.add_argument("--output", type=Path, default=Path("data/hard_negative_corpus"))
    parser.add_argument("--pairs", type=int, default=20)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = build_hard_negative_corpus(
        public_corpus_dir=args.public_corpus,
        output_dir=args.output,
        pair_count=args.pairs,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
