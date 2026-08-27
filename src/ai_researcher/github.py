import hashlib
import hmac
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

SUPPORTED_PULL_REQUEST_ACTIONS = {
    "opened",
    "reopened",
    "synchronize",
    "ready_for_review",
}
SUPPORTED_ISSUE_ACTIONS = {
    "opened",
    "reopened",
    "edited",
    "labeled",
}


def verify_github_signature(
    raw_body: bytes,
    signature_header: str | None,
    secret: str,
) -> bool:
    """Verify GitHub's X-Hub-Signature-256 header against the raw body."""
    if not signature_header or not secret:
        return False

    expected_signature = hmac.new(
        key=secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    expected_header = f"sha256={expected_signature}"

    return hmac.compare_digest(expected_header, signature_header)


async def handle_github_event(
    event: str,
    payload: dict[str, Any],
    delivery_id: str,
) -> dict[str, Any]:
    if event == "ping":
        return handle_ping(payload)

    if event == "push":
        return await handle_push(payload, delivery_id)

    if event == "pull_request":
        return await handle_pull_request(payload, delivery_id)

    if event == "issues":
        return await handle_issues(payload, delivery_id)

    if event == "issue_comment":
        return await handle_issue_comment(payload, delivery_id)

    _log_event("Ignoring unsupported GitHub event", {"delivery_id": delivery_id, "event": event})
    return {
        "handled": False,
        "reason": f"Unsupported event: {event}",
    }


def handle_ping(payload: dict[str, Any]) -> dict[str, Any]:
    repository = payload.get("repository", {})
    sender = payload.get("sender", {})

    return {
        "handled": True,
        "repository": repository.get("full_name"),
        "sender": sender.get("login"),
    }


async def handle_push(payload: dict[str, Any], delivery_id: str) -> dict[str, Any]:
    repository = payload.get("repository", {}).get("full_name")
    ref = payload.get("ref", "")
    branch = ref.removeprefix("refs/heads/")
    commits = payload.get("commits", [])
    changed_files = _collect_changed_files(commits)

    _log_event(
        "Received GitHub push",
        {
            "delivery_id": delivery_id,
            "repository": repository,
            "branch": branch,
            "before": payload.get("before"),
            "after": payload.get("after"),
            "commit_count": len(commits),
            "commit_info": commits,
            "changed_files": changed_files,
        },
    )

    return {
        "handled": True,
        "repository": repository,
        "branch": branch,
        "commit_count": len(commits),
        "changed_file_count": len(changed_files),
        "changed_files": changed_files,
    }


async def handle_pull_request(payload: dict[str, Any], delivery_id: str) -> dict[str, Any]:
    action = payload.get("action")
    pull_request = payload.get("pull_request", {})
    repository = payload.get("repository", {}).get("full_name")

    if action not in SUPPORTED_PULL_REQUEST_ACTIONS:
        return {
            "handled": False,
            "reason": f"Ignored pull_request action: {action}",
        }

    result = {
        "handled": True,
        "action": action,
        "repository": repository,
        "pr_number": pull_request.get("number"),
        "title": pull_request.get("title"),
        "author": pull_request.get("user", {}).get("login"),
        "source_branch": pull_request.get("head", {}).get("ref"),
        "target_branch": pull_request.get("base", {}).get("ref"),
        "is_draft": pull_request.get("draft"),
    }

    _log_event("Received GitHub pull request event", {"delivery_id": delivery_id, **result})
    return result


async def handle_issues(payload: dict[str, Any], delivery_id: str) -> dict[str, Any]:
    action = payload.get("action")
    issue = payload.get("issue", {})
    repository = payload.get("repository", {}).get("full_name")
    labels = [label.get("name") for label in issue.get("labels", []) if label.get("name")]

    if action not in SUPPORTED_ISSUE_ACTIONS:
        return {
            "handled": False,
            "reason": f"Ignored issues action: {action}",
        }

    result = {
        "handled": True,
        "action": action,
        "repository": repository,
        "issue_number": issue.get("number"),
        "title": issue.get("title"),
        "author": issue.get("user", {}).get("login"),
        "labels": labels,
    }

    _log_event("Received GitHub issue event", {"delivery_id": delivery_id, **result})
    return result


async def handle_issue_comment(payload: dict[str, Any], delivery_id: str) -> dict[str, Any]:
    action = payload.get("action")
    comment = payload.get("comment", {})
    issue = payload.get("issue", {})
    repository = payload.get("repository", {}).get("full_name")

    if action != "created":
        return {
            "handled": False,
            "reason": f"Ignored issue_comment action: {action}",
        }

    body = comment.get("body", "").strip()

    if not body.startswith("/"):
        return {
            "handled": False,
            "reason": "Comment is not a command",
        }

    command = body.split(maxsplit=1)[0].lower()
    args = body[len(command):].strip()
    result = {
        "handled": True,
        "repository": repository,
        "issue_number": issue.get("number"),
        "is_pull_request": "pull_request" in issue,
        "command": command,
        "args": args,
        "comment_author": comment.get("user", {}).get("login"),
    }

    _log_event("Received GitHub comment command", {"delivery_id": delivery_id, **result})
    return result


def _collect_changed_files(commits: list[dict[str, Any]]) -> list[str]:
    changed_files: set[str] = set()

    for commit in commits:
        changed_files.update(commit.get("added", []))
        changed_files.update(commit.get("modified", []))
        changed_files.update(commit.get("removed", []))

    return sorted(changed_files)


def _log_event(message: str, data: dict[str, Any]) -> None:
    logger.info("%s: %s", message, json.dumps(data, sort_keys=True))
