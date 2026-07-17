# Product FAQ

## What is Acme Assist?

Acme Assist is an API platform for building automation workflows. You define workflows in YAML or through the visual editor, and Acme runs them on a schedule or in response to webhooks.

## API keys

Create API keys under Settings → API Keys. Keys are shown once at creation — store them securely. You can have up to 10 active keys per workspace. Rotate a key by creating a new one and deleting the old one; there is no in-place rotation.

## Rate limits

- Free: 10 requests/minute
- Pro: 100 requests/minute
- Enterprise: custom

If you exceed the limit the API returns HTTP 429 with a `Retry-After` header. Rate limits are per-workspace, not per-key.

## Integrations

Acme Assist integrates natively with Slack, Gmail, Notion, GitHub, and 40+ other tools. Custom integrations can be built with the webhooks API. Slack and Gmail integrations require workspace-admin approval to install.

## Data retention

Workflow run logs are retained for 30 days on Free, 90 days on Pro, and up to 7 years on Enterprise (configurable). Deleted workspaces are purged within 30 days.
