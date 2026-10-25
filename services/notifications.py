"""Escalation Notification Service supporting Slack Webhooks and Email dispatch."""

import json
import logging
import os
import smtplib
import time
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

logger = logging.getLogger("support_agent.notifications")


class NotificationService:
    def __init__(self):
        self.slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
        self.smtp_host = os.environ.get("SMTP_HOST")
        self.smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        self.smtp_user = os.environ.get("SMTP_USER")
        self.smtp_password = os.environ.get("SMTP_PASSWORD")
        self.alert_email_to = os.environ.get("ALERT_EMAIL_TO", "support-lead@resolvex.ai")
        self.alert_email_from = os.environ.get("ALERT_EMAIL_FROM", "alerts@resolvex.ai")
        self._recent_notifications: List[dict] = []

    def notify_escalation(self, escalation: dict) -> dict:
        """Dispatches real-time alerts across configured notification channels."""
        alert_record = {
            "id": f"notif_{int(time.time() * 1000)}",
            "ts": time.time(),
            "customer": escalation.get("customer", "unknown"),
            "question": escalation.get("question", ""),
            "confidence": escalation.get("confidence", 0.0),
            "conversation_id": escalation.get("conversation_id"),
            "session_id": escalation.get("session_id"),
            "slack_sent": False,
            "email_sent": False,
            "simulated": False,
        }

        # 1. Slack Webhook Dispatch
        if self.slack_webhook_url and self.slack_webhook_url.startswith("http"):
            alert_record["slack_sent"] = self._send_slack(escalation)
        else:
            logger.info("SLACK_WEBHOOK_URL not configured. Escalation logged to dashboard notification feed.")
            alert_record["slack_simulated"] = True

        # 2. Email Dispatch
        if self.smtp_host and self.smtp_user:
            alert_record["email_sent"] = self._send_email(escalation)
        else:
            logger.info("SMTP_HOST not configured. Email escalation logged to dashboard notification feed.")
            alert_record["email_simulated"] = True

        self._recent_notifications.insert(0, alert_record)
        if len(self._recent_notifications) > 50:
            self._recent_notifications.pop()

        return alert_record

    def _send_slack(self, data: dict) -> bool:
        """Sends a structured BlockKit message to Slack."""
        customer = data.get("customer", "Customer")
        confidence = data.get("confidence", 0.0)
        question = data.get("question", "")
        conv_id = data.get("conversation_id", "N/A")

        blocks = {
            "text": f"🚨 Human Escalation Required: {customer}",
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "🚨 Human Escalation Required", "emoji": True}
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Customer:*\n`{customer}`"},
                        {"type": "mrkdwn", "text": f"*Confidence Score:*\n`{confidence:.2f}` (Low)"},
                        {"type": "mrkdwn", "text": f"*Interaction ID:*\n`#{conv_id}`"},
                        {"type": "mrkdwn", "text": f"*Channel:*\n`{data.get('channel', 'web')}`"}
                    ]
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Customer Inquired:*\n> {question[:300]}"}
                },
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": "Action required: Open Agent Workspace to triage and respond."}
                    ]
                }
            ]
        }

        try:
            req = urllib.request.Request(
                self.slack_webhook_url,
                data=json.dumps(blocks).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Failed to post escalation to Slack: {e}")
            return False

    def _send_email(self, data: dict) -> bool:
        """Sends an HTML formatted alert email to on-call support."""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[Escalation Alert] Support Ticket required for {data.get('customer')}"
            msg["From"] = self.alert_email_from
            msg["To"] = self.alert_email_to

            html = f"""
            <div style="font-family: Arial, sans-serif; color: #1e293b; max-width: 600px; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
                <h2 style="color: #ef4444; margin-top: 0;">🚨 Urgent Support Escalation</h2>
                <p>An inbound customer query received confidence <strong>{data.get('confidence', 0.0):.2f}</strong> and has been escalated for human assistance.</p>
                <table style="width: 100%; border-collapse: collapse; margin: 15px 0;">
                    <tr><td style="padding: 6px; font-weight: bold; width: 120px;">Customer:</td><td style="padding: 6px;">{data.get('customer')}</td></tr>
                    <tr><td style="padding: 6px; font-weight: bold;">Question:</td><td style="padding: 6px;">{data.get('question')}</td></tr>
                    <tr><td style="padding: 6px; font-weight: bold;">Draft Answer:</td><td style="padding: 6px; color: #64748b;">{data.get('draft_answer', 'None')}</td></tr>
                </table>
                <p style="font-size: 13px; color: #94a3b8;">Review and respond in the ResolveX Support Intelligence Dashboard.</p>
            </div>
            """
            msg.attach(MIMEText(html, "html"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=5) as server:
                server.starttls()
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            return True
        except Exception as e:
            logger.error(f"Failed to send escalation email: {e}")
            return False

    def get_recent_notifications(self, limit: int = 20) -> List[dict]:
        return self._recent_notifications[:limit]
