from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_NAME = "Agent Reliability Lab"
PUBLIC_SUBTITLE = (
    "Governed Runtime, Evaluation Harness, and Decision Frontier for Tool-Using Agents"
)
PUBLIC_DOCS = (
    ROOT / "README.md",
    ROOT / "docs" / "LATEST_RESULTS_AND_DEMO.md",
    ROOT / "docs" / "EVALUATION_REPORT.md",
    ROOT / "docs" / "FAILURE_ANALYSIS.md",
    ROOT / "docs" / "PROJECT_OVERVIEW.md",
    ROOT / "docs" / "INTERVIEW_QA.md",
    ROOT / "docs" / "ENGINEERING_DISCIPLINE.md",
    ROOT / "docs" / "ROADMAP.md",
    ROOT / "frontend" / "README.md",
)


def test_public_brand_and_legacy_codename_are_explicit() -> None:
    for path in PUBLIC_DOCS:
        content = path.read_text(encoding="utf-8")
        assert PUBLIC_NAME in content, path
    assert PUBLIC_SUBTITLE in (ROOT / "README.md").read_text(encoding="utf-8")
    assert PUBLIC_SUBTITLE in (ROOT / "frontend" / "README.md").read_text(
        encoding="utf-8"
    )
    assert 'description = "' + PUBLIC_SUBTITLE + '"' in (
        ROOT / "pyproject.toml"
    ).read_text(encoding="utf-8")
    for path in (
        ROOT / "README.md",
        ROOT / "docs" / "PROJECT_OVERVIEW.md",
        ROOT / "frontend" / "README.md",
    ):
        assert "TrustRAG" in path.read_text(encoding="utf-8")
        assert "legacy codename" in path.read_text(encoding="utf-8")


def test_current_public_surfaces_do_not_claim_positive_proof_or_stale_q5_plan() -> None:
    for path in PUBLIC_DOCS:
        content = path.read_text(encoding="utf-8")
        assert re.search(r"\bproven\b", content, flags=re.IGNORECASE) is None, path
    roadmap = (ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    assert "正式 q5_test 在实现 freeze 后" not in roadmap
    assert "Q5-P6" not in roadmap
    assert "scoped_negative_complete" in roadmap
    assert "historical plan / superseded" in roadmap


def test_frontend_public_metadata_uses_current_brand() -> None:
    base = (ROOT / "frontend" / "src" / "layouts" / "Base.astro").read_text(
        encoding="utf-8"
    )
    hero = (ROOT / "frontend" / "src" / "components" / "Hero.astro").read_text(
        encoding="utf-8"
    )
    console = (ROOT / "app" / "web" / "index.html").read_text(encoding="utf-8")
    assert PUBLIC_NAME in base
    assert PUBLIC_SUBTITLE in base
    assert PUBLIC_NAME in hero
    assert PUBLIC_SUBTITLE in hero
    assert PUBLIC_NAME in console
