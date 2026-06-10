from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["task_plan_version"] == "v0.3-q1-hard-demo-plan-freeze"


def test_root_returns_project_info() -> None:
    response = client.get("/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "TrustRAG Enterprise QA"
    assert payload["version"] == "0.1.0"
    assert payload["docs_url"] == "/docs"

