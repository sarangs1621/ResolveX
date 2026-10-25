# ResolveX — Autonomous Enterprise Resolution & Support Intelligence

Production-grade autonomous resolution and customer operations platform featuring FastAPI, multi-turn conversational memory, dynamic BM25 RAG over markdown documentation, dual LLM support (Google Gemini & Anthropic Claude), business tool execution, distributed semantic caching (<15ms fast-path), token-bucket rate limiting, OpenTelemetry distributed tracing, confidence gating with human escalation triage, Slack & Email notifications, Role-Based Access Control (RBAC), and a luxury obsidian single-page dashboard.

---

## 🌟 Key Features

1. **Modern Web UI Dashboard (`/`)**:
   - **Customer Portal**: Live chat with source citations, confidence gauges, tool breakdown pills, and CSAT feedback ratings.
   - **Escalation Desk**: Live human agent triage queue to review low-confidence interactions, approve AI drafts, or supply custom agent replies.
   - **CRM & Tool Inspector**: Searchable interaction logs, support tickets, and deep drill-down modals into tool arguments and results.
   - **Knowledge Base Studio**: Built-in Markdown editor with live preview, article creation/deletion, and instant re-indexing.
   - **Telemetry & Ops**: KPI metrics, channel traffic charts, tool execution breakdowns, and Slack/Email alert history.

2. **Enterprise Business Tools**:
   - `search_kb`: BM25 vector-free dynamic search across `kb/*.md`.
   - `check_order_status`: Customer order items, delivery dates, and tracking status.
   - `track_shipment`: Carrier tracking simulation (FedEx, USPS, UPS) with checkpoint history and ETA.
   - `check_account`: Subscription tier, monthly request quotas, and renewal dates.
   - `process_refund_request`: Policy verification (14-day window) and automated refund simulation.
   - `create_support_ticket`: Generates and logs formal internal support tickets (`TICK-XXXX`).

3. **Authentication & Role-Based Access Control (RBAC)**:
   - Salted PBKDF2-SHA256 password security (pure Python standard library).
   - Signed JWT-compatible access tokens.
   - Roles: `customer`, `agent`, `admin` with a one-click demo persona switcher in the dashboard.

4. **Escalation Notifications**:
   - Slack BlockKit webhook notifications on human escalations.
   - Email alert dispatch via SMTP or dashboard notification feed.

5. **Observability & Health Telemetry**:
   - Request latency middleware with `X-Response-Time-Ms` response header.
   - Prometheus and JSON operational metrics at `/metrics`.
   - Comprehensive `/health` diagnostic endpoint.

6. **Containerization & CI/CD**:
   - Hardened `Dockerfile` with non-root user and built-in healthcheck.
   - `docker-compose.yml` with persistent storage for SQLite DB and KB files.
   - `.github/workflows/ci.yml` automating test execution and image builds.

---

## 🚀 Quickstart

### 1. Local Setup

```bash
# Clone and enter directory
cd ResolveX

# Set up virtual environment
python -m venv .venv
.\.venv\Scripts\activate   # On Windows
# or: source .venv/bin/activate on Linux/macOS

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure `.env`

```ini
# Google Gemini API Key
GEMINI_API_KEY=your_gemini_api_key

# Support Model (defaults to gemini-3.5-flash-lite)
SUPPORT_MODEL=gemini-3.5-flash-lite

# Confidence threshold for human escalation (default: 0.70)
CONFIDENCE_THRESHOLD=0.7

# Optional: Slack Webhook & Email
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
ALERT_EMAIL_TO=support-leads@resolvex.ai
```

### 3. Run Application

```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

Open **`http://127.0.0.1:8000/`** in your browser to launch the dashboard.

---

## 🐳 Docker Deployment

### Run via Docker Compose

```bash
docker compose up -d
```

### Build and Run Standalone Container

```bash
docker build -t resolvex-api .
docker run -d -p 8000:8000 --env-file .env -v $(pwd)/crm.db:/app/crm.db -v $(pwd)/kb:/app/kb resolvex-api
```

---

## ☁️ Vercel Deployment

This project is fully configured for zero-configuration deployment to **Vercel** serverless Python runtime.

### Deploy in 2 Steps:

1. **Push to GitHub** or run Vercel CLI from this repository root:
   ```bash
   vercel
   ```
2. **Set Environment Variables in Vercel Project Settings**:
   - `GEMINI_API_KEY`: Your Google Gemini API key.
   - `DATABASE_URL` *(Optional)*: Your Vercel Postgres / Neon / Supabase connection string (`postgresql+asyncpg://...`). If omitted, uses temporary serverless SQLite storage (`/tmp/crm.db`).
   - `REDIS_URL` *(Optional)*: Your Vercel KV / Upstash Redis connection string. If omitted, uses fast in-memory LRU cache and sliding window rate limiter.
   - `JWT_SECRET_KEY` *(Optional)*: Secret string for signing authentication tokens.

All routing and serverless function packaging is handled automatically via `vercel.json` and `api/index.py`.

---

## 🏛️ Enterprise Architecture

1. **PostgreSQL & Connection Pooling (`services/database.py`)**:
   - Built on SQLAlchemy 2.0 with `asyncpg` and `QueuePool` connection pooling (`pool_size=10`, `max_overflow=20`, `pool_pre_ping=True`).
   - Declarative models: `conversations`, `messages`, `escalations`, `users`, `tickets`, `orders`.
   - Dual-support: connects to PostgreSQL when `DATABASE_URL` is configured, with graceful fallback to `aiosqlite` for local dev.

2. **Distributed Semantic Cache (`services/cache.py`)**:
   - Caches high-confidence LLM responses by normalized query hash in Redis.
   - Drops response time from ~800ms down to **<15ms** for recurring inquiries (e.g. return policy, shipping cutoff).
   - In-memory thread-safe LRU fallback when Redis is offline.
   - Automatic cache invalidation when Knowledge Base articles are modified or re-indexed.

3. **Token Bucket Rate Limiting (`services/limiter.py`)**:
   - Protects `/ask` (30 req / 60s) and `/auth/login` (10 req / 60s) against brute-force and DoS.
   - Distributed atomics via Redis pipeline, with in-memory sliding window fallback.
   - Injects standard `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `Retry-After` headers.

4. **Distributed Tracing (`services/tracing.py`)**:
   - OpenTelemetry-compatible tracing across request lifecycles: `cache.lookup` → `rag.retrieval` → `llm.generation` → `tool.execution` → `crm.persistence`.
   - Trace IDs propagated via `X-Trace-Id` headers.
   - Inspect live trace spans directly via `GET /traces`.

---

## 🧪 Automated Tests

Run the full platform test suite covering RAG, business tools, shipment tracking, tickets, RBAC auth, telemetry, notifications, semantic cache, rate limiter, OpenTelemetry, and Vercel structure:

```bash
python test_agent.py
```

---

## 📡 API Reference

| Endpoint | Method | Role | Description |
|---|---|---|---|
| `/` | `GET` | Public | Single-page Luxury Obsidian Web UI Dashboard |
| `/ask` | `POST` | Public/Customer | Customer query intake with semantic cache, rate limit, and trace ID |
| `/auth/login` | `POST` | Public | Authenticate credentials with rate limit protection |
| `/auth/demo-users` | `GET` | Public | Quick-switch personas for demo testing |
| `/escalations` | `GET` | Agent / Admin | List pending or resolved escalations |
| `/escalations/{id}/respond` | `POST` | Agent / Admin | Resolve ticket with agent reply |
| `/tickets` | `GET` / `POST` | Customer / Agent | List or file internal support tickets |
| `/kb` | `GET` / `POST` | Admin | Manage articles and live re-index (purges cache) |
| `/conversations` | `GET` | Agent / Admin | Search interaction history in CRM |
| `/traces` | `GET` | Public | Inspect distributed OpenTelemetry trace spans |
| `/health` | `GET` | Public | System health, environment, cache, and telemetry |
| `/metrics` | `GET` | Public | Operational telemetry (JSON or Prometheus format) |
| `/docs` | `GET` | Public | Interactive Swagger UI API documentation |

