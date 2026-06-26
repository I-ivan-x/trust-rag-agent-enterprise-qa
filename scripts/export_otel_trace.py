# ruff: noqa: E402
"""Q4-P6 CLI: export a run's JSONL governance trace to OpenInference/OTLP spans.

Opt-in observability tool. It is never invoked by eval runs, so existing run behaviour
is unchanged. Requires the optional 'otel' dependency group.

Examples:
  python scripts/export_otel_trace.py --run q4-p5-selection-calibrated --console
  python scripts/export_otel_trace.py --run q4-p5-selection-calibrated \
      --otlp-endpoint http://localhost:4317
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.observability.otel_exporter import export_run_to_otel

DEFAULT_EVAL_RUNS_DIR = Path("data/eval_runs")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a run trace to OpenInference/OTLP spans.")
    parser.add_argument("--run", required=True, help="run_id under data/eval_runs (or a path).")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_EVAL_RUNS_DIR)
    parser.add_argument("--service-name", default="trustrag-ops-governor")
    parser.add_argument(
        "--otlp-endpoint", default=None, help="OTLP gRPC endpoint (else env config)."
    )
    parser.add_argument(
        "--console",
        action="store_true",
        help="Emit spans to stdout via ConsoleSpanExporter instead of OTLP (no backend needed).",
    )
    return parser.parse_args()


def _resolve_traces(run: str, output_root: Path) -> Path:
    direct = Path(run)
    if direct.is_file():
        return direct
    if direct.is_dir() and (direct / "traces.jsonl").is_file():
        return direct / "traces.jsonl"
    candidate = output_root / run / "traces.jsonl"
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(f"Could not resolve traces.jsonl for run '{run}'.")


def _git_commit_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
        ).strip()
    except Exception:
        return None


def main() -> None:
    args = parse_args()
    traces_path = _resolve_traces(args.run, args.output_root)

    exporter = None
    if args.console:
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        exporter = ConsoleSpanExporter()
    elif args.otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        exporter = OTLPSpanExporter(endpoint=args.otlp_endpoint, insecure=True)

    span_count = export_run_to_otel(
        traces_path,
        exporter=exporter,
        service_name=args.service_name,
        commit_sha=_git_commit_sha(),
    )
    print(f"Exported {span_count} spans from {traces_path.as_posix()}")


if __name__ == "__main__":
    main()
