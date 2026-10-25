"""AI Agent Engine supporting Google Gemini and Anthropic Claude with multi-turn conversations and business tools."""

from __future__ import annotations
import asyncio
import json
import os
from typing import TYPE_CHECKING
from pydantic import BaseModel

if TYPE_CHECKING:
    from services.tools import ToolRegistry

SYSTEM_PROMPT = """You are an expert AI Customer Support Agent for Acme Cloud Services.
You assist customers professionally, empathetically, and accurately.

Key Directives:
1. Ground your answers in facts:
   - ALWAYS search the knowledge base using `search_kb` for product features, billing rules, refund policies, and troubleshooting.
   - Use `check_order_status` when a customer asks about their order, package, shipment, or delivery.
   - Use `track_shipment` when a customer provides a package tracking number (e.g. FedEx, USPS, UPS) or asks about real-time transit details.
   - Use `check_account` when a customer asks about their subscription tier, request limits, or billing renewals.
   - Use `process_refund_request` when a customer requests a refund for an order.
   - Use `create_support_ticket` when an issue requires formal support escalation, bug investigation, or dedicated follow-up.
2. Rate your confidence honestly (0.0 to 1.0):
   - Set confidence high (0.8 - 1.0) when official docs or tools provide clear, decisive answers.
   - Set confidence low (< 0.70) when the question is ambiguous, requires human exception handling, or cannot be resolved from available data. This safely triggers escalation to a human agent.
3. Source citations: Always list source document names (e.g., "billing.md", "product.md", or "orders_db") you referenced.
"""


class AgentOutput(BaseModel):
    answer: str
    confidence: float
    sources: list[str]


class AgentEngine:
    def __init__(self, tools_registry: "ToolRegistry"):
        self.tools_registry = tools_registry

    def _get_provider_and_model(self) -> tuple[str, str]:
        if os.environ.get("GEMINI_API_KEY"):
            provider = "gemini"
            default_model = "gemini-3.5-flash-lite"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            provider = "anthropic"
            default_model = "claude-opus-4-8"
        else:
            provider = os.environ.get("LLM_PROVIDER", "gemini")
            default_model = "gemini-3.5-flash-lite"
        model = os.environ.get("SUPPORT_MODEL", default_model)
        return provider, model

    async def run(self, message: str, customer_email: str = "anonymous",
                  history: list[dict] = None) -> tuple[dict, list[dict]]:
        provider, model = self._get_provider_and_model()

        if provider == "gemini":
            return await self._run_gemini(message, customer_email, model, history or [])
        elif provider == "anthropic":
            return await self._run_anthropic(message, customer_email, model, history or [])
        else:
            raise ValueError(f"Unknown provider: {provider}")

    async def _run_gemini(self, message: str, customer_email: str, model: str,
                          history: list[dict]) -> tuple[dict, list[dict]]:
        from google import genai
        from google.genai import types

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured in .env")

        client = genai.Client(api_key=api_key)
        tool_log: list[dict] = []

        def search_kb(query: str) -> str:
            """Search the knowledge base for documentation, billing rules, FAQs, and troubleshooting guides."""
            out = self.tools_registry.search_kb(query)
            tool_log.append({"tool": "search_kb", "input": {"query": query}, "result_preview": out[:300]})
            return out

        def check_order_status(order_id: str = None, customer_email_param: str = None) -> str:
            """Look up customer order details, tracking codes, items, and status."""
            c_email = customer_email_param or customer_email
            out = self.tools_registry.check_order_status(order_id=order_id, customer_email=c_email)
            tool_log.append({"tool": "check_order_status", "input": {"order_id": order_id, "customer_email": c_email}, "result_preview": out})
            return out

        def track_shipment(tracking_code: str) -> str:
            """Track carrier shipment status, delivery estimates, transit checkpoints, and carrier details."""
            out = self.tools_registry.track_shipment(tracking_code=tracking_code)
            tool_log.append({"tool": "track_shipment", "input": {"tracking_code": tracking_code}, "result_preview": out})
            return out

        def check_account(customer_email_param: str = None) -> str:
            """Look up customer subscription plan tier, monthly request usage, and renewal date."""
            c_email = customer_email_param or customer_email
            out = self.tools_registry.check_account(customer_email=c_email)
            tool_log.append({"tool": "check_account", "input": {"customer_email": c_email}, "result_preview": out})
            return out

        def process_refund_request(order_id: str, reason: str = "") -> str:
            """Evaluate whether an order qualifies for automatic 14-day refund or requires escalation."""
            out = self.tools_registry.process_refund_request(order_id=order_id, reason=reason, customer_email=customer_email)
            tool_log.append({"tool": "process_refund_request", "input": {"order_id": order_id, "reason": reason}, "result_preview": out})
            return out

        def create_support_ticket(issue_description: str, priority: str = "medium") -> str:
            """File a formal customer support ticket for issues that require dedicated human team investigation."""
            out = self.tools_registry.create_support_ticket(customer_email=customer_email, issue_description=issue_description, priority=priority)
            tool_log.append({"tool": "create_support_ticket", "input": {"customer_email": customer_email, "issue_description": issue_description, "priority": priority}, "result_preview": out})
            return out

        gemini_tools = [search_kb, check_order_status, track_shipment, check_account, process_refund_request, create_support_ticket]

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=gemini_tools,
            response_mime_type="application/json",
            response_schema=AgentOutput,
        )

        def _execute():
            # Build conversation chat session
            chat = client.chats.create(model=model, config=config)
            # Seed relevant past turns if any
            for h in history[-4:]:
                if h["role"] == "user":
                    try:
                        chat.send_message(h["content"])
                    except Exception:
                        pass
            # Send current message
            return chat.send_message(f"[Customer Email: {customer_email}]\nCustomer Message: {message}")

        resp = await asyncio.to_thread(_execute)
        text = resp.text or ""

        try:
            result = json.loads(text)
        except Exception:
            result = {
                "answer": text or "I apologize, but I could not formulate a response.",
                "confidence": 0.0,
                "sources": [],
            }
        return result, tool_log

    async def _run_anthropic(self, message: str, customer_email: str, model: str,
                             history: list[dict]) -> tuple[dict, list[dict]]:
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured in .env")

        client = anthropic.AsyncAnthropic(api_key=api_key)
        tool_log: list[dict] = []

        tools = [
            {
                "name": "search_kb",
                "description": "Search the knowledge base.",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
            {
                "name": "check_order_status",
                "description": "Check order status and tracking info.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string"},
                        "customer_email": {"type": "string"},
                    },
                },
            },
            {
                "name": "check_account",
                "description": "Check account subscription tier and request quota.",
                "input_schema": {
                    "type": "object",
                    "properties": {"customer_email": {"type": "string"}},
                    "required": ["customer_email"],
                },
            },
            {
                "name": "process_refund_request",
                "description": "Check refund eligibility and simulate refund.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["order_id"],
                },
            },
            {
                "name": "track_shipment",
                "description": "Track carrier shipment status, delivery estimates, transit checkpoints, and carrier details.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "tracking_code": {"type": "string"},
                    },
                    "required": ["tracking_code"],
                },
            },
            {
                "name": "create_support_ticket",
                "description": "File a formal customer support ticket for issues that require dedicated human team investigation.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "issue_description": {"type": "string"},
                        "priority": {"type": "string"},
                    },
                    "required": ["issue_description"],
                },
            },
        ]

        messages = []
        for h in history[-4:]:
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({
            "role": "user",
            "content": f"[Customer Email: {customer_email}]\nCustomer: {message}",
        })

        output_format = {
            "type": "json_schema",
            "schema": {
                "type": "object",
                "properties": {
                    "answer": {"type": "string"},
                    "confidence": {"type": "number"},
                    "sources": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["answer", "confidence", "sources"],
            },
        }

        resp = None
        for _ in range(6):
            resp = await client.messages.create(
                model=model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=tools,
                output_config={"format": output_format},
                messages=messages,
            )
            if resp.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": resp.content})
                results = []
                for block in resp.content:
                    if block.type == "tool_use":
                        out = self.tools_registry.exec_tool(block.name, block.input)
                        tool_log.append({
                            "tool": block.name,
                            "input": block.input,
                            "result_preview": out,
                        })
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": out,
                        })
                messages.append({"role": "user", "content": results})
                continue
            break

        text = next((b.text for b in resp.content if b.type == "text"), "") if resp else ""
        try:
            result = json.loads(text)
        except Exception:
            result = {
                "answer": text or "I couldn't process this request.",
                "confidence": 0.0,
                "sources": [],
            }
        return result, tool_log
