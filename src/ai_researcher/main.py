import json
import logging
import os
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request

from ai_researcher.github import handle_github_event, verify_github_signature

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Researcher")


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/webhooks/github")
async def github_webhook_info() -> dict[str, str]:
    return {
        "detail": "GitHub webhook endpoint is ready. Send POST requests to this URL.",
    }


@app.post("/webhooks/github")
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(default=None, alias="X-GitHub-Event"),
    x_github_delivery: str | None = Header(default=None, alias="X-GitHub-Delivery"),
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
) -> dict[str, Any]:
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(status_code=500, detail="GITHUB_WEBHOOK_SECRET is not configured")

    raw_body = await request.body()

    if not verify_github_signature(raw_body, x_hub_signature_256, secret):
        raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    event = x_github_event or "unknown"
    delivery_id = x_github_delivery or "unknown"
    result = await handle_github_event(event, payload, delivery_id)
    logger.info(
        "GitHub webhook delivery: %s",
        json.dumps(
            {
                "delivery_id": delivery_id,
                "event": event,
                "action": payload.get("action"),
                "repository": payload.get("repository", {}).get("full_name"),
                "sender": payload.get("sender", {}).get("login"),
                "result": result,
            },
            sort_keys=True,
        ),
    )

    return {
        "ok": True,
        "event": event,
        "delivery_id": delivery_id,
        "result": result,
    }
