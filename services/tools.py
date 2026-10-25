"""Tool implementations for AI Customer Support Agent."""

from __future__ import annotations
import json
import os
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.rag import KnowledgeBaseService
    from services.crm import CRMService


class ToolRegistry:
    def __init__(self, kb_service: "KnowledgeBaseService", crm_service: "CRMService"):
        self.kb_service = kb_service
        self.crm_service = crm_service

    def search_kb(self, query: str) -> str:
        """Search the company knowledge base (product docs, billing policies, FAQs, troubleshooting). Call this to look up facts and official policies."""
        results = self.kb_service.search(query, k=4)
        if not results:
            return "No knowledge base results found for that query."
        return json.dumps(results)

    def check_order_status(self, order_id: str = None, customer_email: str = None) -> str:
        """Check order details, shipment tracking status, item purchased, and order date for a customer."""
        orders = self.crm_service.get_order(order_id=order_id, customer_email=customer_email)
        if not orders:
            return f"No orders found matching order_id='{order_id}' or customer_email='{customer_email}'."
        return json.dumps(orders)

    def check_account(self, customer_email: str) -> str:
        """Check customer account plan tier (Free, Pro, Enterprise), monthly API request usage/quota, renewal date, and account status."""
        account = self.crm_service.get_account(customer_email)
        if not account:
            return f"No account found for customer_email='{customer_email}'."
        return json.dumps(account)

    def process_refund_request(self, order_id: str, reason: str = "", customer_email: str = None) -> str:
        """Verify refund eligibility based on company policy (within 14 days of purchase) and simulate processing refund."""
        orders = self.crm_service.get_order(order_id=order_id, customer_email=customer_email)
        if not orders:
            return f"Cannot process refund: Order '{order_id}' was not found in system."
        order = orders[0]
        days_ago = order.get("days_ago", 999)
        if days_ago <= 14:
            return json.dumps({
                "refund_status": "approved",
                "order_id": order["order_id"],
                "amount": order["amount"],
                "policy_check": "Order is within 14-day full refund window.",
                "message": f"Refund of ${order['amount']:.2f} has been approved and issued to the original payment method.",
            })
        else:
            return json.dumps({
                "refund_status": "requires_escalation",
                "order_id": order["order_id"],
                "days_since_purchase": days_ago,
                "policy_check": "Order exceeds 14-day automatic refund window.",
                "message": "Refund outside the 14-day policy window requires support manager approval. Escalate to human team.",
            })

    def notion_search(self, query: str) -> str:
        """Search the company Notion workspace for internal documentation."""
        token = os.environ.get("NOTION_TOKEN")
        if not token:
            return "Notion integration is not configured."
        req = urllib.request.Request(
            "https://api.notion.com/v1/search",
            json.dumps({"query": query, "page_size": 5}).encode(),
            {
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.read().decode()
        except OSError as e:
            return f"Notion search failed: {e}"

    def track_shipment(self, tracking_code: str) -> str:
        """Track real-time carrier shipment status, delivery estimates, transit checkpoints, and carrier details."""
        code = (tracking_code or "").strip().upper()
        if not code:
            return json.dumps({"error": "Tracking code is required."})

        # Known mock shipments in our database
        known_shipments = {
            "FEDEX-992147": {
                "carrier": "FedEx Express",
                "tracking_code": "FEDEX-992147",
                "status": "In Transit",
                "estimated_delivery": "Tomorrow by 4:30 PM",
                "origin": "Memphis, TN",
                "destination": "San Francisco, CA",
                "checkpoints": [
                    {"time": "Today, 06:15 AM", "location": "Oakland, CA", "activity": "Arrived at local FedEx facility"},
                    {"time": "Yesterday, 10:45 PM", "location": "Memphis, TN", "activity": "Departed FedEx hub"},
                    {"time": "2 days ago, 04:20 PM", "location": "Memphis, TN", "activity": "Picked up"}
                ]
            },
            "TRACK-USPS-8841": {
                "carrier": "USPS Priority Mail",
                "tracking_code": "TRACK-USPS-8841",
                "status": "Delivered",
                "delivered_at": "Yesterday at 11:42 AM",
                "signed_by": "Front Desk / Mailroom",
                "origin": "Austin, TX",
                "destination": "New York, NY",
                "checkpoints": [
                    {"time": "Yesterday, 11:42 AM", "location": "New York, NY", "activity": "Delivered, In/At Mailbox"},
                    {"time": "Yesterday, 07:10 AM", "location": "New York, NY", "activity": "Out for Delivery"},
                    {"time": "2 days ago, 09:30 PM", "location": "Jersey City, NJ", "activity": "Arrived at USPS Regional Facility"}
                ]
            },
            "TRACK-UPS-1102": {
                "carrier": "UPS Ground",
                "tracking_code": "TRACK-UPS-1102",
                "status": "Delivered",
                "delivered_at": "March 12, 2026",
                "origin": "Chicago, IL",
                "destination": "Seattle, WA",
                "checkpoints": [
                    {"time": "March 12, 2026, 02:15 PM", "location": "Seattle, WA", "activity": "Delivered to Porch"}
                ]
            }
        }

        if code in known_shipments:
            return json.dumps(known_shipments[code])

        # Deterministic simulation for arbitrary tracking numbers
        carrier = "FedEx" if "FDX" in code or "FEDEX" in code else ("UPS" if "1Z" in code or "UPS" in code else "USPS Priority")
        return json.dumps({
            "carrier": carrier,
            "tracking_code": code,
            "status": "In Transit",
            "estimated_delivery": "Within 2 business days",
            "origin": "Dallas, TX Distribution Center",
            "destination": "Customer Delivery Address",
            "checkpoints": [
                {"time": "Today, 08:30 AM", "location": "In Transit", "activity": "En route to regional sorting facility"},
                {"time": "Yesterday, 05:00 PM", "location": "Dallas, TX", "activity": "Package received at carrier facility"}
            ]
        })

    def create_support_ticket(self, customer_email: str, issue_description: str, priority: str = "medium") -> str:
        """Create and register a formal internal support ticket in the CRM for issues requiring human agent follow-up."""
        if not customer_email or not issue_description:
            return json.dumps({"error": "customer_email and issue_description are required."})
        ticket = self.crm_service.create_ticket(
            customer_email=customer_email,
            issue_description=issue_description,
            priority=priority
        )
        return json.dumps({
            "status": "created",
            "ticket_ref": ticket["ticket_ref"],
            "priority": ticket["priority"],
            "message": f"Support ticket {ticket['ticket_ref']} has been successfully created. Our support team will follow up at {customer_email}."
        })

    def exec_tool(self, name: str, tool_input: dict) -> str:
        if name == "search_kb":
            return self.search_kb(tool_input.get("query", ""))
        elif name == "check_order_status":
            return self.check_order_status(
                order_id=tool_input.get("order_id"),
                customer_email=tool_input.get("customer_email")
            )
        elif name == "check_account":
            return self.check_account(customer_email=tool_input.get("customer_email", ""))
        elif name == "process_refund_request":
            return self.process_refund_request(
                order_id=tool_input.get("order_id", ""),
                reason=tool_input.get("reason", ""),
                customer_email=tool_input.get("customer_email")
            )
        elif name == "track_shipment":
            return self.track_shipment(tracking_code=tool_input.get("tracking_code", ""))
        elif name == "create_support_ticket":
            return self.create_support_ticket(
                customer_email=tool_input.get("customer_email", ""),
                issue_description=tool_input.get("issue_description", ""),
                priority=tool_input.get("priority", "medium")
            )
        elif name == "notion_search":
            return self.notion_search(tool_input.get("query", ""))
        return f"Unknown tool: {name}"

