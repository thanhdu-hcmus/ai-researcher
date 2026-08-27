import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from ai_researcher.github import verify_github_signature
from ai_researcher.main import app


SECRET = "test-secret"


def signed_headers(event: str, body: bytes) -> dict[str, str]:
    signature = hmac.new(SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": "test-delivery-id",
        "X-Hub-Signature-256": f"sha256={signature}",
    }


def test_verify_github_signature_accepts_valid_signature() -> None:
    body = b'{"repository":{"full_name":"octocat/ai-researcher"}}'
    headers = signed_headers("ping", body)

    assert verify_github_signature(body, headers["X-Hub-Signature-256"], SECRET)


def test_verify_github_signature_rejects_invalid_signature() -> None:
    body = b'{"repository":{"full_name":"octocat/ai-researcher"}}'

    assert not verify_github_signature(body, "sha256=bad", SECRET)


def test_github_webhook_handles_ping(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    client = TestClient(app)
    payload = {
        "repository": {"full_name": "octocat/ai-researcher"},
        "sender": {"login": "octocat"},
    }
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    response = client.post("/webhooks/github", content=body, headers=signed_headers("ping", body))

    assert response.status_code == 200
    assert response.json()["result"] == {
        "handled": True,
        "repository": "octocat/ai-researcher",
        "sender": "octocat",
    }


def test_github_webhook_rejects_bad_signature(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    client = TestClient(app)

    response = client.post(
        "/webhooks/github",
        content=b"{}",
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "ping",
            "X-GitHub-Delivery": "test-delivery-id",
            "X-Hub-Signature-256": "sha256=bad",
        },
    )

    assert response.status_code == 401


def test_github_webhook_handles_push(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    client = TestClient(app)
    payload = {
        "ref": "refs/heads/main",
        "repository": {"full_name": "octocat/ai-researcher"},
        "commits": [
            {
                "added": ["src/ai_researcher/github.py"],
                "modified": ["README.md"],
                "removed": [],
            }
        ],
    }
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    response = client.post("/webhooks/github", content=body, headers=signed_headers("push", body))

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["handled"] is True
    assert result["branch"] == "main"
    assert result["commit_count"] == 1
    assert result["changed_files"] == ["README.md", "src/ai_researcher/github.py"]

