# Troubleshooting

## Login issues

If you can't log in, first try resetting your password at /reset. SSO users must log in through their identity provider — the password form will not work for SSO accounts. If your account is locked after too many attempts, it unlocks automatically after 15 minutes.

## Workflow failures

Common causes of failed workflow runs:

1. **Expired credentials** — reconnect the integration under Settings → Integrations.
2. **Rate limits on the target service** — add a delay step or reduce the schedule frequency.
3. **Payload too large** — webhook payloads are capped at 5 MB.

Every failed run shows the full error log in the run detail view. Runs are retried automatically 3 times with exponential backoff before being marked failed.

## Webhook signature verification

All outbound webhooks are signed with HMAC-SHA256 in the `X-Acme-Signature` header. Verify using your workspace's signing secret from Settings → Webhooks. Timestamps older than 5 minutes should be rejected to prevent replay attacks.

## Status page

Live system status is at status.example.com. Subscribe there for incident notifications.
