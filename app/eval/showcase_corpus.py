"""Hash-closed verification for the demonstration-only interview corpus."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.schemas.showcase import ShowcaseManifest

SHOWCASE_ROOT = Path("data/showcase/interview-v1")
SHOWCASE_VIEW_PATH = Path("frontend/src/data/interview-showcase.json")
FORMAL_PUBLIC_FILES = (
    Path("data/claims/claim_registry.json"),
    Path("frontend/src/data/headline-results.json"),
    Path("frontend/src/data/questions.json"),
)


def verify_interview_showcase(
    root: Path | str = SHOWCASE_ROOT,
    *,
    verify_formal_isolation: bool = True,
) -> dict[str, Any]:
    corpus_root = Path(root)
    manifest = ShowcaseManifest.model_validate(
        json.loads((corpus_root / "manifest.json").read_text(encoding="utf-8"))
    )
    actual_files = {
        path.name
        for path in corpus_root.iterdir()
        if path.is_file() and path.name != "manifest.json"
    }
    if actual_files != set(manifest.files):
        raise ValueError("showcase directory file matrix differs from manifest")
    for name, expected in manifest.files.items():
        actual = hashlib.sha256((corpus_root / name).read_bytes()).hexdigest()
        if actual != expected.sha256:
            raise ValueError(f"showcase file hash mismatch: {name}")
    _verify_trajectory_contract(corpus_root)
    if verify_formal_isolation:
        verify_showcase_isolation()
    manifest_hash = hashlib.sha256((corpus_root / "manifest.json").read_bytes()).hexdigest()
    return {
        "schema_version": "interview-showcase-verification-v1",
        "corpus_id": manifest.corpus_id,
        "file_count": len(manifest.files) + 1,
        "manifest_sha256": manifest_hash,
        "data_mode": manifest.data_mode,
        "use": manifest.use,
        "headline_eligible": manifest.headline_eligible,
        "formal_evaluation": manifest.formal_evaluation,
        "model_requests": manifest.model_requests,
        "external_requests": manifest.external_requests,
        "formal_claim_references": 0,
        "status": "passed",
    }


def verify_showcase_isolation(paths: tuple[Path, ...] = FORMAL_PUBLIC_FILES) -> None:
    for path in paths:
        payload = path.read_text(encoding="utf-8").replace("\\", "/").lower()
        if "data/showcase/" in payload:
            raise ValueError(f"formal claim surface references showcase corpus: {path}")


def build_interview_showcase(*, check: bool = False) -> dict[str, Any]:
    receipt = verify_interview_showcase()
    root = SHOWCASE_ROOT
    observation = _read_json(root / "live-observation.json")
    access = _read_json(root / "access-policy.json")
    approval = _read_json(root / "approval-policy.json")
    trajectory = _read_json(root / "authorized-trajectory.json")
    blocked = _read_json(root / "blocked-trajectory.json")
    payload = {
        "schema_version": "interview-showcase-view-v1",
        "corpus_id": receipt["corpus_id"],
        "manifest_sha256": receipt["manifest_sha256"],
        "incident": {
            "service": observation["deployment"]["service_ref"],
            "request": "判断发布后错误率升高的原因，并在合规时回滚。",
            "result": "回滚提案有依据，但执行权限不足，已等待事故负责人审批。",
        },
        "journey": [
            {"stage": "请求", "detail": "值班工程师请求诊断并回滚异常发布"},
            {"stage": "找证据", "detail": "采用当前手册；隔离过期与无权限文档"},
            {
                "stage": "实时观察",
                "detail": (
                    f"错误率 {_percent(observation['error_rate']['before_release'])} → "
                    f"{_percent(observation['error_rate']['after_release'])}"
                ),
            },
            {"stage": "提出动作", "detail": "提议回滚到上一健康版本"},
            {"stage": "权限检查", "detail": "允许提议，但拒绝直接执行"},
            {"stage": "等待审批", "detail": "进入事故负责人审批队列，副作用为零"},
        ],
        "evidence": {
            "authorized_count": len(trajectory["evidence"]),
            "blocked_count": len(blocked["blocked_evidence"]),
            "authorized_ids": [item["document_id"] for item in trajectory["evidence"]],
            "blocked_ids": list(access["blocked_documents"]),
        },
        "observation": {
            "request_id": observation["request_id"],
            "release": observation["deployment"]["current_release"],
            "target_release": observation["deployment"]["previous_release"],
            "error_rate": _percent(observation["error_rate"]["after_release"]),
            "threshold": _percent(observation["error_rate"]["threshold"]),
        },
        "terminal": {
            "proposal": trajectory["proposal"]["action"],
            "authorization": trajectory["authorization_result"],
            "state": approval["pending_state"],
            "side_effect_executed": trajectory["side_effect_executed"],
        },
        "data_mode": "synthetic",
        "use": "demonstration_only",
        "headline_eligible": False,
        "formal_evaluation": False,
    }
    expected = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode()
    if check:
        if not SHOWCASE_VIEW_PATH.is_file() or SHOWCASE_VIEW_PATH.read_bytes() != expected:
            raise ValueError("generated interview showcase view drifted")
    else:
        SHOWCASE_VIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
        SHOWCASE_VIEW_PATH.write_bytes(expected)
    return {**receipt, "generated_view": SHOWCASE_VIEW_PATH.as_posix()}


def _verify_trajectory_contract(root: Path) -> None:
    access = _read_json(root / "access-policy.json")
    observation = _read_json(root / "live-observation.json")
    approval = _read_json(root / "approval-policy.json")
    authorized = _read_json(root / "authorized-trajectory.json")
    blocked = _read_json(root / "blocked-trajectory.json")
    journey = _read_json(root / "expected-journey.json")
    authorized_documents = set(access["authorized_documents"])
    blocked_documents = set(access["blocked_documents"])
    trajectory_documents = {item["document_id"] for item in authorized["evidence"]}
    if not trajectory_documents <= authorized_documents:
        raise ValueError("authorized trajectory contains a document outside the ACL")
    if trajectory_documents & blocked_documents:
        raise ValueError("authorized and blocked showcase evidence overlap")
    if {item["document_id"] for item in blocked["blocked_evidence"]} != blocked_documents:
        raise ValueError("blocked showcase evidence does not close against the ACL")
    if observation["status"] != "ok" or not observation["authorized"]:
        raise ValueError("trusted showcase observation must be successful and authorized")
    if observation["request_id"] not in authorized["observations"]:
        raise ValueError("authorized trajectory does not cite the trusted observation")
    if approval["execution_before_approval"] or authorized["side_effect_executed"]:
        raise ValueError("showcase trajectory must not execute before approval")
    if authorized["terminal"] != approval["pending_state"]:
        raise ValueError("showcase pending terminal does not match approval policy")
    if journey["final_state"] != authorized["terminal"]:
        raise ValueError("expected journey and authorized trajectory terminal differ")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"
