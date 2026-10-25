"""Comprehensive Test Suite for AI Customer Support Agent Platform.
Tests RAG, business tool dispatch, shipment tracking, ticket creation, RBAC auth, telemetry, and notifications.
Run: python test_agent.py
"""

from pathlib import Path
from main import BM25, load_chunks, should_escalate, exec_tool
from services.auth import (
    hash_password,
    verify_password,
    create_access_token,
    verify_access_token
)
from services.metrics import metrics_service
from services.notifications import NotificationService


def run():
    print("Running RAG and Knowledge Base tests...")
    chunks = load_chunks()
    assert len(chunks) >= 3, "KB should produce chunks"
    assert all(c["text"] and c["source"].endswith(".md") for c in chunks)

    index = BM25(chunks)
    hits = index.search("how do I get a refund")
    assert hits, "refund query should hit the KB"
    assert hits[0]["source"] == "billing.md", f"expected billing.md first, got {hits[0]['source']}"
    assert index.search("zqxwv nonsense gibberish") == []

    print("Running confidence threshold gating tests...")
    assert should_escalate(0.3) and not should_escalate(0.9)
    assert should_escalate(0.69) and not should_escalate(0.7)

    print("Running existing tool execution tests...")
    assert "billing" in exec_tool("search_kb", {"query": "refund policy"})
    assert "No knowledge base results" in exec_tool("search_kb", {"query": "zqxwv"})

    orders_res = exec_tool("check_order_status", {"order_id": "ORD-9021"})
    assert "Pro Annual Subscription" in orders_res, f"unexpected orders result: {orders_res}"

    account_res = exec_tool("check_account", {"customer_email": "jane@x.com"})
    assert "Jane Doe" in account_res and "Pro" in account_res, f"unexpected account result: {account_res}"

    refund_valid = exec_tool("process_refund_request", {"order_id": "ORD-9021"})
    assert "approved" in refund_valid

    refund_expired = exec_tool("process_refund_request", {"order_id": "ORD-6003"})
    assert "requires_escalation" in refund_expired

    print("Running new business tools tests (shipment tracking & support ticket dispatch)...")
    # 1. Track Shipment
    fedex_track = exec_tool("track_shipment", {"tracking_code": "FEDEX-992147"})
    assert "FedEx Express" in fedex_track and "In Transit" in fedex_track, f"Unexpected tracking: {fedex_track}"

    usps_track = exec_tool("track_shipment", {"tracking_code": "TRACK-USPS-8841"})
    assert "USPS Priority Mail" in usps_track and "Delivered" in usps_track, f"Unexpected tracking: {usps_track}"

    # 2. Create Support Ticket
    ticket_res = exec_tool("create_support_ticket", {
        "customer_email": "alex@company.org",
        "issue_description": "Network latency spike on US-West gateway",
        "priority": "urgent"
    })
    assert "TICK-" in ticket_res and "created" in ticket_res, f"Unexpected ticket: {ticket_res}"

    print("Running authentication & RBAC tests...")
    pwd_hash, salt = hash_password("secret_pass123")
    assert verify_password("secret_pass123", salt, pwd_hash), "Password verification failed"
    assert not verify_password("wrong_pass", salt, pwd_hash), "Password verification should fail on wrong password"

    token = create_access_token({"email": "agent@resolvex.ai", "role": "agent", "name": "Agent Jane"})
    payload = verify_access_token(token)
    assert payload is not None, "Token verification failed"
    assert payload["sub"] == "agent@resolvex.ai" and payload["role"] == "agent"

    # Tampered token check
    assert verify_access_token(token + "tampered") is None, "Tampered token should be rejected"

    print("Running telemetry and metrics tests...")
    metrics_service.record_request("/ask", 200, 45.2)
    metrics_service.record_request("/health", 200, 1.8)
    metrics_service.record_tool_call("track_shipment")
    m = metrics_service.get_metrics()
    assert m["total_requests"] >= 2, "Metric requests count incorrect"
    assert "track_shipment" in m["tool_executions"], "Tool execution not tracked"
    prom_text = metrics_service.get_prometheus_format()
    assert "resolvex_support_requests_total" in prom_text

    print("Running escalation notification service tests...")
    notif = NotificationService()
    alert = notif.notify_escalation({
        "customer": "jane@x.com",
        "question": "Can I get a discount?",
        "confidence": 0.45,
        "conversation_id": 999
    })
    assert alert["customer"] == "jane@x.com"
    recent = notif.get_recent_notifications()
    assert len(recent) > 0 and recent[0]["customer"] == "jane@x.com"

    print("Running distributed semantic cache tests...")
    import asyncio
    from services.cache import SemanticCacheService
    cache = SemanticCacheService()
    asyncio.run(cache.initialize())
    asyncio.run(cache.set_answer("What is the return policy?", {"answer": "14-day refund policy.", "confidence": 0.95}))
    cached = asyncio.run(cache.get_answer("what is the return policy???"))
    assert cached is not None and cached["cached"] is True
    assert cached["answer"] == "14-day refund policy."
    stats = cache.get_stats()
    assert stats["hits"] >= 1

    print("Running token bucket rate limiter tests...")
    from services.limiter import SlidingWindowRateLimiter
    limiter = SlidingWindowRateLimiter()
    asyncio.run(limiter.initialize())
    # Should allow first 3 requests with limit 3
    for _ in range(3):
        allowed, remaining, _ = asyncio.run(limiter.is_allowed("test_client", limit=3, window_seconds=60))
        assert allowed is True
    # 4th request must be rejected with 429 logic
    allowed, remaining, retry_after = asyncio.run(limiter.is_allowed("test_client", limit=3, window_seconds=60))
    assert allowed is False
    assert remaining == 0
    assert retry_after > 0

    print("Running OpenTelemetry distributed tracing tests...")
    from services.tracing import DistributedTracingService
    test_tracer = DistributedTracingService()
    tid = test_tracer.new_trace_id()
    with test_tracer.span("test.parent", trace_id=tid) as p_span:
        p_span.set_attribute("env", "test")
        with test_tracer.span("test.child", trace_id=tid) as c_span:
            c_span.set_attribute("status", "ok")
    test_tracer.finalize_trace(tid)
    traces = test_tracer.get_recent_traces(10)
    assert len(traces) > 0 and traces[0]["trace_id"] == tid

    print("Running Vercel deployment structure tests...")
    assert (Path("api/index.py")).exists(), "api/index.py entrypoint missing for Vercel"
    assert (Path("vercel.json")).exists(), "vercel.json configuration missing for Vercel"

    print("\n[SUCCESS] All checks passed successfully! (RAG, tools, shipment tracking, ticket dispatch, auth RBAC, metrics, notifications, semantic cache, rate limiter, OpenTelemetry, Vercel)")


if __name__ == "__main__":
    run()
