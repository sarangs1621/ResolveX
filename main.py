"""AI Customer Support Agent — Enterprise Production-Grade FastAPI Platform.

Features:
- Dual LLM Providers: Google Gemini 3.5 & Anthropic Claude
- Multi-Turn Conversation Sessions & CRM History
- Dynamic Knowledge Base (BM25 RAG) with Live Editing & Instant Re-indexing
- Enterprise Business Tools: Order status, Account quota, 14-day refund simulation,
  Real-time Shipment Tracking & Support Ticket Dispatch
- Confidence Gating & Human Agent Escalation Queue
- Real-time Escalation Notifications via Slack Webhooks & Email Alerts
- Role-Based Access Control (RBAC) with secure PBKDF2 hashing and JWT tokens
- Structured Observability, Latency Middleware & Prometheus /metrics Endpoint
- Modern Single-Page Web Dashboard (Customer Live Chat, Escalation Desk, CRM Activity, KB Manager, Analytics)
"""

from __future__ import annotations
import json
import logging
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional, List

# Ensure project root is first in sys.path for serverless execution
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import traceback
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()
logger = logging.getLogger("support_agent")
logging.basicConfig(level=logging.INFO)

IS_VERCEL = bool(
    os.getenv("VERCEL") == "1"
    or os.getenv("VERCEL_ENV")
    or os.getenv("NOW_REGION")
)
BASE_DIR = Path(__file__).resolve().parent
KB_DIR = BASE_DIR / "kb"
DB_PATH = Path(tempfile.gettempdir()) / "crm.db" if IS_VERCEL else (BASE_DIR / "crm.db")
STATIC_DIR = BASE_DIR / "static"

# Ensure essential directories exist if writable
if not IS_VERCEL:
    try:
        KB_DIR.mkdir(exist_ok=True)
        STATIC_DIR.mkdir(exist_ok=True)
    except Exception:
        pass

# Initialize FastAPI application IMMEDIATELY so Vercel can always import it
app = FastAPI(
    title="ResolveX — Autonomous Enterprise Resolution & Support Intelligence",
    description="ResolveX autonomous customer support & resolution platform with RAG, business tool calling, RBAC, semantic caching, and human escalation triage.",
    version="3.0.0"
)

# Enable CORS for local testing/web embedding
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STARTUP_ERROR = None
STARTUP_TRACE = None

try:
    from services.rag import KnowledgeBaseService, BM25, load_chunks
    from services.crm import CRMService
    from services.tools import ToolRegistry
    from services.agent import AgentEngine
    from services.auth import (
        create_access_token,
        verify_password,
        get_current_user,
        get_optional_user,
        require_role,
        hash_password,
    )
    from services.notifications import NotificationService
    from services.metrics import metrics_service
    from services.cache import semantic_cache
    from services.limiter import enforce_rate_limit, rate_limiter
    from services.tracing import tracer
    from services.database import db_manager

    # Initialize core platform services with fail-safe fallback
    try:
        kb_service = KnowledgeBaseService(KB_DIR)
        crm_service = CRMService(DB_PATH)
        tools_registry = ToolRegistry(kb_service, crm_service)
        agent_engine = AgentEngine(tools_registry)
        notification_service = NotificationService()
    except Exception as init_err:
        logger.error(f"Error during service initialization: {init_err}", exc_info=True)
        kb_service = KnowledgeBaseService(KB_DIR)
        crm_service = CRMService(Path(":memory:"))
        tools_registry = ToolRegistry(kb_service, crm_service)
        agent_engine = AgentEngine(tools_registry)
        notification_service = NotificationService()

    index = kb_service.index

except BaseException as exc:
    STARTUP_ERROR = str(exc)
    STARTUP_TRACE = traceback.format_exc()
    logger.critical(f"FATAL STARTUP EXCEPTION:\n{STARTUP_TRACE}")

    # Fallback stub services to keep API routes alive and return diagnostic info
    class _Stub:
        def __getattr__(self, name):
            return lambda *a, **k: {}

    kb_service = _Stub()
    crm_service = _Stub()
    tools_registry = _Stub()
    agent_engine = _Stub()
    notification_service = _Stub()
    metrics_service = _Stub()
    metrics_service.record_request = lambda *a, **k: None
    metrics_service.record_tool_call = lambda *a, **k: None
    metrics_service.get_metrics = lambda: {"uptime_seconds": 0, "total_requests": 0, "latency": {"avg_ms": 0}}
    metrics_service.get_prometheus_format = lambda: "# startup failed"
    semantic_cache = _Stub()
    semantic_cache.get_stats = lambda: {"hits": 0, "misses": 0}
    tracer = _Stub()
    tracer.start_trace = lambda *a, **k: "trace-err"
    tracer.finalize_trace = lambda *a, **k: None
    tracer.get_recent_traces = lambda *a, **k: []
    db_manager = _Stub()

    def create_access_token(*a, **k): return "token"
    def verify_password(*a, **k): return True
    def get_current_user(): return {"sub": "admin@resolvex.ai", "role": "admin", "name": "Admin"}
    def get_optional_user(): return {"sub": "guest@example.com", "role": "customer", "name": "Guest"}
    def require_role(*a, **k): return lambda: {"sub": "admin@resolvex.ai", "role": "admin"}
    def hash_password(p, s=None): return ("hash", s or "salt")
    def enforce_rate_limit(*a, **k): return None
    rate_limiter = _Stub()
    index = _Stub()

CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.7"))


def should_escalate(confidence: float, threshold: float = CONFIDENCE_THRESHOLD) -> bool:
    return confidence < threshold


def exec_tool(name: str, tool_input: dict) -> str:
    metrics_service.record_tool_call(name)
    return tools_registry.exec_tool(name, tool_input)


# ---------------------------------------------------------------- Observability Middleware

@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    start_ts = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start_ts) * 1000
    response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"
    
    path = request.url.path
    # Skip recording static file asset hits to avoid polluting business metrics
    if not path.startswith("/static"):
        metrics_service.record_request(path, response.status_code, duration_ms)
    return response


# ---------------------------------------------------------------- Data Models

class AskRequest(BaseModel):
    message: str
    customer_email: str = "customer@example.com"
    channel: str = "web"  # web | slack | email
    session_id: Optional[str] = None


class FeedbackRequest(BaseModel):
    feedback: str  # positive | negative | text comment


class HumanRespondRequest(BaseModel):
    response: str
    status: str = "resolved"


class ArticleRequest(BaseModel):
    content: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TicketCreateRequest(BaseModel):
    customer_email: str
    issue_description: str
    priority: str = "medium"


class TicketUpdateRequest(BaseModel):
    status: str


# ---------------------------------------------------------------- Authentication & RBAC

@app.post("/auth/login")
async def login(req: LoginRequest, request: Request):
    """Authenticates credentials against CRM and issues signed token with brute-force rate limiting."""
    await enforce_rate_limit(request, key_prefix="login", limit=10, window_seconds=60)
    user = crm_service.get_user_by_email(req.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if not verify_password(req.password, user["salt"], user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = create_access_token({
        "email": user["email"],
        "role": user["role"],
        "name": user["name"]
    })
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "name": user["name"]
        }
    }


@app.get("/auth/me")
def get_profile(user: dict = Depends(get_optional_user)):
    """Returns profile information for the authenticated user or guest persona."""
    return user


@app.get("/auth/demo-users")
def get_demo_users():
    """Returns quick-switch personas with pre-signed demo tokens for instant web UI testing."""
    users = crm_service.list_users()
    personas = []
    for u in users:
        token = create_access_token({"email": u["email"], "role": u["role"], "name": u["name"]})
        personas.append({
            "email": u["email"],
            "role": u["role"],
            "name": u["name"],
            "token": token
        })
    return personas


# ---------------------------------------------------------------- Customer Support Inbound

@app.post("/ask")
async def ask(
    req: AskRequest,
    request: Request,
    response: Response,
    user: dict = Depends(get_optional_user)
):
    """Inbound customer query endpoint with semantic caching, distributed tracing, tool execution, and confidence gating."""
    # 1. Enforce Token Bucket Rate Limiting (30 req / 60s)
    await enforce_rate_limit(request, key_prefix="ask", limit=30, window_seconds=60)

    trace_id = tracer.new_trace_id()
    response.headers["X-Trace-Id"] = trace_id

    session_id = req.session_id or f"sess_{uuid.uuid4().hex[:10]}"
    customer_email = req.customer_email.strip() if req.customer_email.strip() else user.get("sub", "customer@example.com")

    # 2. Check Distributed Semantic Cache (<15ms response path)
    with tracer.span("cache.lookup", trace_id=trace_id) as cache_span:
        cached_res = await semantic_cache.get_answer(req.message)
        cache_span.set_attribute("cache.hit", cached_res is not None)

    if cached_res:
        response.headers["X-Cache"] = "HIT"
        conv_id = crm_service.record_conversation(
            session_id=session_id,
            channel=req.channel,
            customer=customer_email,
            question=req.message,
            answer=cached_res["answer"],
            confidence=cached_res["confidence"],
            escalated=False,
            sources=cached_res.get("sources", []),
            tool_calls=[]
        )
        tracer.finalize_trace(trace_id, meta={"cache_hit": True, "customer": customer_email})
        return {
            "conversation_id": conv_id,
            "session_id": session_id,
            "answer": cached_res["answer"],
            "draft_answer": None,
            "confidence": cached_res["confidence"],
            "escalated": False,
            "sources": cached_res.get("sources", []),
            "tool_calls": [],
            "cached": True,
            "trace_id": trace_id
        }

    response.headers["X-Cache"] = "MISS"

    # 3. Agent Pipeline (RAG + Business Tools + LLM)
    history = crm_service.get_session_messages(session_id, limit=6)
    with tracer.span("agent.pipeline", trace_id=trace_id) as pipe_span:
        try:
            result, tool_log = await agent_engine.run(
                message=req.message,
                customer_email=customer_email,
                history=history
            )
            for t in tool_log:
                metrics_service.record_tool_call(t.get("tool", "unknown"))
        except Exception as e:
            logger.error(f"Agent engine execution failure: {e}", exc_info=True)
            result = {
                "answer": f"Service temporarily busy. Escalate to human agent: {str(e)}",
                "confidence": 0.0,
                "sources": []
            }
            tool_log = [{"tool": "system_error", "input": {}, "result_preview": str(e)}]

    confidence = float(result.get("confidence", 0.0))
    escalated = should_escalate(confidence)
    draft_answer = result.get("answer", "")

    if escalated:
        customer_reply = (
            "Thank you for contacting us. Your request requires specialized assistance, "
            "so I have passed this to our support team. A team member will follow up with you shortly."
        )
    else:
        customer_reply = draft_answer
        # Cache verified high-confidence answers
        if confidence >= 0.75:
            await semantic_cache.set_answer(req.message, {
                "answer": customer_reply,
                "confidence": confidence,
                "sources": result.get("sources", []),
                "tool_calls": tool_log
            })

    conv_id = crm_service.record_conversation(
        session_id=session_id,
        channel=req.channel,
        customer=customer_email,
        question=req.message,
        answer=customer_reply,
        confidence=confidence,
        escalated=escalated,
        sources=result.get("sources", []),
        tool_calls=tool_log
    )

    if escalated:
        notification_service.notify_escalation({
            "conversation_id": conv_id,
            "session_id": session_id,
            "customer": customer_email,
            "channel": req.channel,
            "question": req.message,
            "draft_answer": draft_answer,
            "confidence": confidence,
        })

    tracer.finalize_trace(trace_id, meta={"cache_hit": False, "escalated": escalated, "confidence": confidence})

    return {
        "conversation_id": conv_id,
        "session_id": session_id,
        "answer": customer_reply,
        "draft_answer": draft_answer if escalated else None,
        "confidence": confidence,
        "escalated": escalated,
        "sources": result.get("sources", []),
        "tool_calls": tool_log,
        "cached": False,
        "trace_id": trace_id
    }


@app.get("/sessions/{session_id}/messages")
def get_session_history(session_id: str):
    """Retrieve full message history for a chat session."""
    return crm_service.get_session_messages(session_id)


@app.post("/conversations/{conv_id}/feedback")
def submit_feedback(conv_id: int, req: FeedbackRequest):
    """Save customer CSAT feedback (thumbs up / thumbs down)."""
    crm_service.set_feedback(conv_id, req.feedback)
    return {"status": "ok", "conversation_id": conv_id, "feedback": req.feedback}


@app.get("/conversations")
def list_conversations(limit: int = 50, search: Optional[str] = None):
    """List customer conversations logged in SQLite CRM."""
    return crm_service.list_conversations(limit=limit, search=search)


@app.get("/conversations/{conv_id}")
def get_conversation_details(conv_id: int):
    """Get single conversation record with full tool execution breakdown."""
    conv = crm_service.get_conversation(conv_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    return conv


# ---------------------------------------------------------------- Escalation Management

@app.get("/escalations")
def list_escalations(status: str = "open"):
    """List open or resolved escalation tickets."""
    return crm_service.list_escalations(status=status)


@app.post("/escalations/{escalation_id}/resolve")
def resolve_escalation(escalation_id: int):
    """Mark an escalation ticket resolved."""
    return crm_service.resolve_escalation(escalation_id)


@app.post("/escalations/{escalation_id}/respond")
def respond_escalation(escalation_id: int, req: HumanRespondRequest):
    """Human agent overrides draft answer and resolves escalation."""
    return crm_service.resolve_escalation(escalation_id, human_response=req.response)


@app.get("/notifications")
def get_notifications(limit: int = 20):
    """Retrieve recent escalation notification alerts dispatched to Slack/Email."""
    return notification_service.get_recent_notifications(limit=limit)


# ---------------------------------------------------------------- Support Tickets

@app.get("/tickets")
def list_tickets(status: Optional[str] = None, limit: int = 50):
    """List internal support tickets created by tools or support agents."""
    return crm_service.list_tickets(status=status, limit=limit)


@app.post("/tickets")
def create_ticket(req: TicketCreateRequest):
    """Create a new support ticket."""
    return crm_service.create_ticket(
        customer_email=req.customer_email,
        issue_description=req.issue_description,
        priority=req.priority
    )


@app.patch("/tickets/{ticket_id}")
def update_ticket(ticket_id: str, req: TicketUpdateRequest):
    """Update ticket status (open, in_progress, resolved)."""
    return crm_service.update_ticket_status(ticket_id, req.status)


# ---------------------------------------------------------------- Analytics & Metrics

@app.get("/analytics")
def get_analytics():
    """Aggregated support analytics and KPIs."""
    return crm_service.get_analytics()


@app.get("/metrics")
def get_metrics(request: Request):
    """Operational metrics in JSON or standard Prometheus text format."""
    accept_header = request.headers.get("accept", "")
    if "text/plain" in accept_header or request.query_params.get("format") == "prometheus":
        return PlainTextResponse(metrics_service.get_prometheus_format())
    return metrics_service.get_metrics()


# ---------------------------------------------------------------- Knowledge Base Management

@app.get("/kb")
def list_kb_articles():
    """List knowledge base articles."""
    return kb_service.list_articles()


@app.get("/kb/{filename}")
def get_kb_article(filename: str):
    """Get markdown content of a KB article."""
    try:
        content = kb_service.get_article(filename)
        return {"filename": filename, "content": content}
    except FileNotFoundError:
        raise HTTPException(404, f"Article {filename} not found")


@app.post("/kb/{filename}")
async def save_kb_article(filename: str, req: ArticleRequest):
    """Save or update a KB article and automatically refresh the BM25 index & invalidate semantic cache."""
    result = kb_service.save_article(filename, req.content)
    await semantic_cache.clear()
    return result


@app.delete("/kb/{filename}")
async def delete_kb_article(filename: str):
    """Delete a KB article, refresh index, and clear semantic cache."""
    success = kb_service.delete_article(filename)
    if not success:
        raise HTTPException(404, f"Article {filename} not found")
    await semantic_cache.clear()
    return {"deleted": True, "filename": filename}


@app.post("/kb/reindex")
async def reindex_kb():
    """Force re-index of all knowledge base documents and invalidate cache."""
    chunks = kb_service.reload()
    await semantic_cache.clear()
    return {"status": "ok", "total_chunks": chunks}


# ---------------------------------------------------------------- Observability & Tracing

@app.get("/traces")
def get_traces(limit: int = 25):
    """Inspect recent distributed OpenTelemetry trace spans with component latency breakdown."""
    return {
        "service": "resolvex-agent",
        "traces": tracer.get_recent_traces(limit=limit)
    }


# ---------------------------------------------------------------- System Status & Health

@app.get("/health")
def health():
    """Comprehensive system health diagnostics and runtime telemetry."""
    if STARTUP_ERROR:
        return JSONResponse(
            status_code=500,
            content={
                "status": "startup_failed",
                "error": STARTUP_ERROR,
                "traceback": STARTUP_TRACE.splitlines() if STARTUP_TRACE else None,
                "environment": "vercel" if IS_VERCEL else "local",
                "sys_path": sys.path,
                "cwd": os.getcwd()
            }
        )
    try:
        provider, model = agent_engine._get_provider_and_model()
    except Exception:
        provider, model = ("gemini", "gemini-3.5-flash-lite")

    try:
        cur = crm_service.db.cursor()
        cur.execute("SELECT 1")
        db_healthy = True
    except Exception:
        db_healthy = False

    try:
        metrics = metrics_service.get_metrics()
    except Exception:
        metrics = {"uptime_seconds": 0, "total_requests": 0, "latency": {"avg_ms": 0}}

    return {
        "status": "healthy" if db_healthy else "degraded",
        "environment": "vercel" if IS_VERCEL else "local",
        "provider": provider,
        "model": model,
        "kb_chunks": len(getattr(kb_service, "index", None).docs) if hasattr(getattr(kb_service, "index", None), "docs") else 0,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "database_connected": db_healthy,
        "cache": semantic_cache.get_stats(),
        "rate_limiting": "active",
        "tracing": "active",
        "uptime_seconds": metrics["uptime_seconds"],
        "total_requests": metrics["total_requests"],
        "avg_latency_ms": metrics["latency"]["avg_ms"],
        "slack_alerts_configured": bool(getattr(notification_service, "slack_webhook_url", None)),
        "email_alerts_configured": bool(getattr(notification_service, "smtp_host", None)),
    }


@app.get("/api/diagnostic")
def diagnostic():
    """Emergency diagnostic endpoint providing runtime environment inspection."""
    return {
        "status": "startup_failed" if STARTUP_ERROR else "healthy",
        "error": STARTUP_ERROR,
        "traceback": STARTUP_TRACE.splitlines() if STARTUP_TRACE else None,
        "environment": "vercel" if IS_VERCEL else "local",
        "sys_path": sys.path,
        "cwd": os.getcwd(),
        "static_exists": STATIC_DIR.exists(),
        "kb_exists": KB_DIR.exists()
    }


# ---------------------------------------------------------------- Web Application Serving

# Mount static files directory
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def index_page():
    """Serve the single-page application dashboard."""
    html_path = STATIC_DIR / "index.html"
    if html_path.exists():
        try:
            return FileResponse(str(html_path))
        except Exception:
            return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return {"message": "ResolveX Enterprise Platform API is running. Visit /docs for Swagger UI."}
