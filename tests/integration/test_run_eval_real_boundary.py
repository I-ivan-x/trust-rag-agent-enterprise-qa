import os
import subprocess
import sys


def _env_with(**overrides: str) -> dict[str, str]:
    env = dict(os.environ)
    env.update(overrides)
    return env


def test_run_eval_real_boundary_cli_fails_without_real_llm() -> None:
    # Force mock provider regardless of the local .env so the boundary is deterministic.
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
        env=_env_with(LLM_PROVIDER="mock", LLM_MODEL_NAME="mock-llm-v0"),
    )

    assert completed.returncode != 0
    assert "Current LLM_PROVIDER=mock" in completed.stderr


def test_run_eval_real_boundary_cli_fails_without_api_key() -> None:
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
        env=_env_with(
            LLM_PROVIDER="deepseek",
            LLM_MODEL_NAME="deepseek-v4-flash",
            DEEPSEEK_API_KEY="",
            OPENAI_API_KEY="",
        ),
    )

    assert completed.returncode != 0
    assert "requires an API key" in completed.stderr
    # The placeholder key value must never appear in surfaced errors.
    assert "Bearer" not in completed.stderr
