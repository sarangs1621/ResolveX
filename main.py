"""AI Customer Support Agent — FastAPI service.

Flow: inbound message -> agent loop (Claude + search_kb tool over local KB)
-> confidence gate -> reply or human escalation queue -> everything logged to CRM (SQLite).
"""

import json
import math
import os
import re
import sqlite3
import time
import urllib.request
from collections import Counter
from pathlib import Path

import anthropic
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

MODEL = os.environ.get("SUPPORT_MODEL", "claude-opus-4-8")
CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.7"))
KB_DIR = Path(__file__).parent / "kb"
DB_PATH = Path(__file__).parent / "crm.db"

# ---------------------------------------------------------------- RAG (BM25)
# ponytail: BM25 over markdown chunks, no embedding API needed; swap in real
# embeddings if retrieval quality measurably falls short.


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def load_chunks(kb_dir: Path = KB_DIR, max_len: int = 1200) -> list[dict]:
    chunks = []
    for f in sorted(kb_dir.glob("*.md")):
        buf = ""
        for para in f.read_text().split("\n\n"):
            if len(buf) + len(para) > max_len and buf:
                chunks.append({"source": f.name, "text": buf.strip()})
                buf = ""
            buf += para + "\n\n"
        if buf.strip():
            chunks.append({"source": f.name, "text": buf.strip()})
    return chunks


class BM25:
    def __init__(self, docs: list[dict], k1: float = 1.5, b: float = 0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.tfs = [Counter(tokenize(d["text"])) for d in docs]
        self.lens = [sum(tf.values()) for tf in self.tfs]
        self.avgdl = (sum(self.lens) / len(self.lens)) if docs else 1
        self.df: Counter = Counter()
        for tf in self.tfs:
            self.df.update(tf.keys())
        self.n = len(docs)

    def search(self, query: str, k: int = 4) -> list[dict]:
        scores = []
        for i, tf in enumerate(self.tfs):
            s = 0.0
            for t in tokenize(query):
                if t not in tf:
                    continue
                idf = math.log(1 + (self.n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                norm = tf[t] + self.k1 * (1 - self.b + self.b * self.lens[i] / self.avgdl)
                s += idf * tf[t] * (self.k1 + 1) / norm
            if s > 0:
                scores.append((s, i))
        scores.sort(reverse=True)
        return [{**self.docs[i], "score": round(s, 2)} for s, i in scores[:k]]


index = BM25(load_chunks()) if KB_DIR.exists() else BM25([])

# ---------------------------------------------------------------- CRM (SQLite)

db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.execute("""CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY, ts REAL, channel TEXT, customer TEXT,
    question TEXT, answer TEXT, confidence REAL, escalated INTEGER,
    sources TEXT, tool_calls TEXT)""")
db.execute("""CREATE TABLE IF NOT EXISTS escalations (
    id INTEGER PRIMARY KEY, conversation_id INTEGER, ts REAL,
    question TEXT, draft_answer TEXT, confidence REAL, status TEXT)""")
db.commit()


def notify_slack(text: str) -> None:
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        return
    req = urllib.request.Request(
        url, json.dumps({"text": text}).encode(), {"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except OSError:
        pass  # notification is best-effort; escalation is already in the queue

# ---------------------------------------------------------------- Agent

SYSTEM = """You are a customer support agent. Answer customer questions using ONLY \
information retrieved from the knowledge base via the search_kb tool — always search \
before answering, and search again with different terms if the first results are weak.

Rate your confidence honestly: if the knowledge base does not clearly answer the \
question, or the customer asks for something requiring account access, refunds \
outside policy, or human judgment, set confidence low so the case escalates to a human. \
Never invent policies, prices, or features. Cite the source files you relied on."""

TOOLS = [{
    "name": "search_kb",
    "description": "Search the company knowledge base (product docs, policies, FAQs). "
                   "Call this before answering any customer question.",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Search query"}},
        "required": ["query"],
        "additionalProperties": False,
    },
    "strict": True,
}]

if os.environ.get("NOTION_TOKEN"):
    TOOLS.append({
        "name": "notion_search",
        "description": "Search the company's Notion workspace for internal docs "
                       "not in the knowledge base.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
        "strict": True,
    })

OUTPUT_FORMAT = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "answer": {"type": "string", "description": "Reply to send the customer"},
            "confidence": {"type": "number", "description": "0.0-1.0, honesty over optimism"},
            "sources": {"type": "array", "items": {"type": "string"},
                        "description": "KB source files the answer is based on"},
        },
        "required": ["answer", "confidence", "sources"],
        "additionalProperties": False,
    },
}


def exec_tool(name: str, tool_input: dict) -> str:
    if name == "search_kb":
        results = index.search(tool_input["query"])
        if not results:
            return "No knowledge base results for that query."
        return json.dumps(results)
    if name == "notion_search":
        req = urllib.request.Request(
            "https://api.notion.com/v1/search",
            json.dumps({"query": tool_input["query"], "page_size": 5}).encode(),
            {
                "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.read().decode()
        except OSError as e:
            return f"Notion search failed: {e}"
    return f"Unknown tool: {name}"


client = anthropic.AsyncAnthropic()


async def run_agent(question: str) -> tuple[dict, list[dict]]:
    """Agent loop: Claude plans, calls tools, returns structured answer."""
    messages = [{"role": "user", "content": question}]
    tool_log: list[dict] = []
    for _ in range(8):
        resp = await client.messages.create(
            model=MODEL,
            max_tokens=8192,
            system=SYSTEM,
            thinking={"type": "adaptive"},
            tools=TOOLS,
            output_config={"format": OUTPUT_FORMAT},
            messages=messages,
        )
        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if block.type == "tool_use":
                    out = exec_tool(block.name, block.input)
                    tool_log.append({"tool": block.name, "input": block.input,
                                     "result_preview": out[:300]})
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": out})
            messages.append({"role": "user", "content": results})
            continue
        break

    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        # refusal / truncation — treat as zero-confidence so it escalates
        result = {"answer": text or "I couldn't process this request.",
                  "confidence": 0.0, "sources": []}
    return result, tool_log


def should_escalate(confidence: float, threshold: float = CONFIDENCE_THRESHOLD) -> bool:
    return confidence < threshold

# ---------------------------------------------------------------- API

app = FastAPI(title="AI Customer Support Agent")


class AskRequest(BaseModel):
    message: str
    customer_email: str = "anonymous"
    channel: str = "web"  # web | slack | gmail — all inbound funnels through here


@app.post("/ask")
async def ask(req: AskRequest):
    try:
        result, tool_log = await run_agent(req.message)
    except (TypeError, anthropic.AuthenticationError) as e:
        raise HTTPException(503, f"Anthropic auth not configured: set ANTHROPIC_API_KEY. ({e})")
    except anthropic.APIStatusError as e:
        raise HTTPException(502, f"Upstream model error {e.status_code}: {e.message}")
    confidence = float(result.get("confidence", 0.0))
    escalated = should_escalate(confidence)

    cur = db.execute(
        "INSERT INTO conversations (ts, channel, customer, question, answer, confidence,"
        " escalated, sources, tool_calls) VALUES (?,?,?,?,?,?,?,?,?)",
        (time.time(), req.channel, req.customer_email, req.message, result["answer"],
         confidence, int(escalated), json.dumps(result.get("sources", [])),
         json.dumps(tool_log)),
    )
    conversation_id = cur.lastrowid

    if escalated:
        db.execute(
            "INSERT INTO escalations (conversation_id, ts, question, draft_answer,"
            " confidence, status) VALUES (?,?,?,?,?,'open')",
            (conversation_id, time.time(), req.message, result["answer"], confidence),
        )
        notify_slack(f":rotating_light: Support escalation #{conversation_id} "
                     f"from {req.customer_email}: {req.message[:200]}")
    db.commit()

    return {
        "conversation_id": conversation_id,
        "answer": result["answer"] if not escalated else
                  "Thanks for reaching out — I've passed this to our support team, "
                  "and a human will get back to you shortly.",
        "draft_answer": result["answer"] if escalated else None,
        "confidence": confidence,
        "escalated": escalated,
        "sources": result.get("sources", []),
    }


@app.get("/escalations")
def list_escalations(status: str = "open"):
    rows = db.execute(
        "SELECT id, conversation_id, ts, question, draft_answer, confidence, status"
        " FROM escalations WHERE status = ? ORDER BY ts DESC", (status,)).fetchall()
    keys = ["id", "conversation_id", "ts", "question", "draft_answer", "confidence", "status"]
    return [dict(zip(keys, r)) for r in rows]


@app.post("/escalations/{escalation_id}/resolve")
def resolve_escalation(escalation_id: int):
    cur = db.execute("UPDATE escalations SET status='resolved' WHERE id=?", (escalation_id,))
    db.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "escalation not found")
    return {"id": escalation_id, "status": "resolved"}


@app.get("/conversations")
def list_conversations(limit: int = 50):
    rows = db.execute(
        "SELECT id, ts, channel, customer, question, answer, confidence, escalated,"
        " sources, tool_calls FROM conversations ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    keys = ["id", "ts", "channel", "customer", "question", "answer", "confidence",
            "escalated", "sources", "tool_calls"]
    return [dict(zip(keys, r)) for r in rows]


@app.get("/health")
def health():
    return {"status": "ok", "kb_chunks": index.n, "model": MODEL}
