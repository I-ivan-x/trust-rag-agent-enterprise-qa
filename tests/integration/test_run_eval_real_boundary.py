import subprocess
import sys


def test_run_eval_real_boundary_cli_fails_without_real_llm() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_eval.py",
            "--split",
            "external",
            "--systems",
            "final_gated",
            "--real-run",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "Current LLM_PROVIDER=mock" in completed.stderr

