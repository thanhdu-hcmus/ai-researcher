# GitHub Webhooks: Local Implementation Guide

This project exposes one GitHub webhook endpoint:

```text
POST /webhooks/github
```

Run the app, expose it with ngrok, point GitHub at the ngrok URL, then trigger real repo activity such as pushes, pull requests, issues, and comments.

## Project Files

```text
src/ai_researcher/main.py       FastAPI routes
src/ai_researcher/github.py     Signature verification and event handlers
scripts/send_test_webhook.py    Signed local test request
tests/test_github_webhook.py    Webhook tests
run.sh                         Loads .env and starts uvicorn
.env.example                   Example local config
```

## Install

```bash
pip install -e ".[dev]"
```

Create `.env`:

```env
GITHUB_WEBHOOK_SECRET=your-long-random-secret
LOG_LEVEL=INFO
```

Generate a secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Run Locally

```bash
./run.sh
```

Equivalent manual command:

```bash
uvicorn ai_researcher.main:app --reload --host 0.0.0.0 --port 8000
```

Check the app:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/webhooks/github
```

Expected:

```json
{"ok":true}
```

and:

```json
{"detail":"GitHub webhook endpoint is ready. Send POST requests to this URL."}
```

## Test With a Signed Local Request

This does not require GitHub or ngrok:

```bash
python scripts/send_test_webhook.py
```

The script sends a signed `push` event to:

```text
http://localhost:8000/webhooks/github
```

Expected response shape:

```json
{
  "ok": true,
  "event": "push",
  "delivery_id": "generated-id",
  "result": {
    "handled": true,
    "repository": "octocat/ai-researcher",
    "branch": "main",
    "commit_count": 1,
    "changed_file_count": 2,
    "changed_files": ["README.md", "app/github.py"]
  }
}
```

## Test Real GitHub Events With ngrok

GitHub cannot reach `localhost`, so expose your local server:

```bash
ngrok http 8000
```

ngrok prints something like:

```text
Forwarding  https://abc123.ngrok-free.app -> http://localhost:8000
```

Your GitHub webhook payload URL is:

```text
https://abc123.ngrok-free.app/webhooks/github
```

Check the tunnel:

```bash
curl https://abc123.ngrok-free.app/health
```

You can also aim the signed test script through ngrok:

```bash
GITHUB_WEBHOOK_TEST_URL=https://abc123.ngrok-free.app/webhooks/github python scripts/send_test_webhook.py
```

PowerShell:

```powershell
$env:GITHUB_WEBHOOK_TEST_URL = "https://abc123.ngrok-free.app/webhooks/github"
python scripts/send_test_webhook.py
```

## GitHub Webhook Settings

In your repo, go to `Settings` > `Webhooks` > `Add webhook`.

Use:

```text
Payload URL: https://abc123.ngrok-free.app/webhooks/github
Content type: application/json
Secret: same value as GITHUB_WEBHOOK_SECRET
Events: push, pull_request, issues, issue_comment
```

GitHub sends a `ping` event immediately after creating the webhook.

Free ngrok URLs usually change when ngrok restarts. Update the GitHub payload URL after each ngrok restart.

## How GitHub Delivers a Webhook

Every delivery is an HTTP request.

Important headers:

```text
X-GitHub-Event: push
X-GitHub-Delivery: unique-delivery-id
X-Hub-Signature-256: sha256=...
Content-Type: application/json
```

Important body fields usually include:

```text
repository.full_name   owner/repo
sender.login           GitHub user or app that caused the event
action                 what happened, for action-based events
```

`push` is not action-based. It has `ref`, `before`, `after`, and `commits`.

`pull_request`, `issues`, and `issue_comment` are action-based. They include an `action` field such as `opened`, `edited`, `closed`, or `created`.

## Event Payloads To Test

### 1. ping

Trigger: create the webhook or redeliver the first delivery.

Fields to inspect:

```text
event = ping
repository.full_name
sender.login
hook_id
```

### 2. push

Trigger: push one or more commits to a branch.

Fields to inspect:

```text
event = push
ref = refs/heads/main
before = previous commit SHA
after = new commit SHA
commits[].added
commits[].modified
commits[].removed
head_commit.message
pusher.name
```

Use this for indexing changed files, triggering analysis, or syncing code metadata.

### 3. pull_request

Trigger: open a PR, push new commits to it, mark it ready for review, close it.

Fields to inspect:

```text
event = pull_request
action = opened | synchronize | ready_for_review | closed
pull_request.number
pull_request.title
pull_request.user.login
pull_request.head.ref
pull_request.head.sha
pull_request.base.ref
pull_request.draft
```

Use this for PR review automation, summaries, labels, or branch comparison.

### 4. issues

Trigger: open, edit, reopen, label, or close an issue.

Fields to inspect:

```text
event = issues
action = opened | edited | labeled | closed
issue.number
issue.title
issue.body
issue.labels[].name
issue.user.login
```

Use this for triage, classification, or creating internal tasks.

### 5. issue_comment

Trigger: comment on an issue or PR.

Fields to inspect:

```text
event = issue_comment
action = created
issue.number
issue.pull_request exists only when the comment is on a PR
comment.body
comment.user.login
```

Use this for slash commands:

```text
/review
/research topic
/summarize
```

## Current Event Routing

```text
ping             handled
push             handled
pull_request     handles opened, reopened, synchronize, ready_for_review
issues           handles opened, reopened, edited, labeled
issue_comment    handles created comments that start with /
```

Ignored events still return `200` with:

```json
{
  "handled": false,
  "reason": "Ignored ..."
}
```

That is intentional. A webhook endpoint should acknowledge valid deliveries quickly, even if your app chooses not to act on a specific event or action.

## Debugging Real Deliveries

You can inspect each event in three places.

### 1. Uvicorn terminal

Your app logs a compact JSON summary for every valid delivery:

```text
INFO:ai_researcher.main:GitHub webhook delivery: {"action": "opened", "delivery_id": "...", "event": "pull_request", "repository": "owner/repo", "sender": "username", "result": {...}}
```

This is the fastest place to see what your handler extracted from the payload.

### 2. ngrok request inspector

Open this while ngrok is running:

```text
http://127.0.0.1:4040
```

The inspector shows each request sent through the tunnel, including:

```text
method and path
request headers
request JSON body
response status
response body
timing
```

This is the easiest place to read the raw payload GitHub sent to your local machine.

### 3. GitHub Recent Deliveries

In GitHub:

1. Open `Settings` > `Webhooks`.
2. Click your webhook.
3. Open `Recent Deliveries`.
4. Click a delivery.
5. Check request headers, request payload, response status, and response body.
6. Use `Redeliver` to replay the same event.

Common results:

```text
200 OK       Signature passed and app received the event.
401         Secret mismatch or bad X-Hub-Signature-256.
404         Wrong URL or wrong app is running.
500         GITHUB_WEBHOOK_SECRET is not visible to the server process.
timeout     Server, tunnel, or handler took too long.
```

## Security Rules

```text
Keep .env out of Git.
Use the same secret in GitHub and GITHUB_WEBHOOK_SECRET.
Verify the raw request body before parsing JSON.
Use X-GitHub-Delivery as the idempotency key.
Return quickly; do slow work in a background job.
Treat payload content as untrusted input.
Rotate secrets if they are exposed.
```
