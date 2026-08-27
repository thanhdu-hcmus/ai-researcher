import hashlib
import hmac
import json
import os
import uuid

import httpx
from dotenv import load_dotenv


def main() -> None:
    load_dotenv()

    secret = os.environ["GITHUB_WEBHOOK_SECRET"]
    url = os.getenv("GITHUB_WEBHOOK_TEST_URL", "http://localhost:8000/webhooks/github")
    payload = {
        "ref": "refs/heads/main",
        "before": "1111111111111111111111111111111111111111",
        "after": "2222222222222222222222222222222222222222",
        "repository": {"full_name": "octocat/ai-researcher"},
        "commits": [
            {
                "id": "2222222222222222222222222222222222222222",
                "message": "Test webhook",
                "added": ["app/github.py"],
                "modified": ["README.md"],
                "removed": [],
            }
        ],
    }

    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    response = httpx.post(
        url,
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-GitHub-Delivery": str(uuid.uuid4()),
            "X-Hub-Signature-256": f"sha256={signature}",
        },
        timeout=10,
    )

    print(f"POST {url}")
    print(response.status_code)
    print(response.text)


if __name__ == "__main__":
    main()
