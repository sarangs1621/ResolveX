# AI Customer Support Agent

Production-style support agent: FastAPI service, RAG over `kb/*.md` (BM25), Claude agent loop with tool calling, confidence gating with a human escalation queue, and every conversation/tool call logged to a SQLite CRM (`crm.db`).

## Run

```sh
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # or `ant auth login`
uvicorn main:app --port 8000
```

## Use

```sh
# Ask a question (any channel funnels through here — web widget, Slack bot, Gmail poller)
curl -s localhost:8000/ask -H 'content-type: application/json' \
  -d '{"message": "What is your refund policy?", "customer_email": "jane@x.com"}'

# Human escalation queue
curl -s localhost:8000/escalations
curl -s -X POST localhost:8000/escalations/1/resolve

# CRM log
curl -s localhost:8000/conversations
curl -s localhost:8000/health
```

Answers below the confidence threshold (default 0.7, env `CONFIDENCE_THRESHOLD`) are held for a human: the customer gets a "we'll get back to you" reply, the draft answer lands in the escalation queue, and Slack is pinged if `SLACK_WEBHOOK_URL` is set.

## Optional integrations (env vars)

- `SLACK_WEBHOOK_URL` — escalation notifications posted to Slack.
- `NOTION_TOKEN` — adds a `notion_search` tool the agent can use for internal docs.
- Gmail inbound: point any poller/forwarder at `POST /ask` with `channel: "gmail"`; there is no OAuth flow bundled.

## Tests

```sh
python test_agent.py
```
