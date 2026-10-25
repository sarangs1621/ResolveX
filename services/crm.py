from __future__ import annotations
import json
import os
import sqlite3
import time
from pathlib import Path


class CRMService:
    def __init__(self, db_path: Path):
        import tempfile
        is_serverless = bool(
            os.getenv("VERCEL") == "1"
            or os.getenv("VERCEL_ENV")
            or os.getenv("NOW_REGION")
            or not os.access(db_path.parent, os.W_OK)
        )
        if is_serverless:
            self.db_path = Path(tempfile.gettempdir()) / "crm.db"
        else:
            self.db_path = db_path

        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self.db.row_factory = sqlite3.Row
            self._init_db()
        except Exception:
            # Absolute fallback to in-memory SQLite if filesystem is fully locked
            self.db_path = Path(":memory:")
            self.db = sqlite3.connect(":memory:", check_same_thread=False)
            self.db.row_factory = sqlite3.Row
            self._init_db()

    def _init_db(self):
        cur = self.db.cursor()
        # Conversations (Interaction level)
        cur.execute("""CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            ts REAL,
            channel TEXT,
            customer TEXT,
            question TEXT,
            answer TEXT,
            confidence REAL,
            escalated INTEGER,
            sources TEXT,
            tool_calls TEXT,
            feedback TEXT
        )""")

        # Migration check for existing SQLite databases created with older schema
        cur.execute("PRAGMA table_info(conversations)")
        conv_cols = {row["name"] for row in cur.fetchall()}
        for col_name, col_type in [("session_id", "TEXT"), ("feedback", "TEXT"), ("tool_calls", "TEXT")]:
            if col_name not in conv_cols:
                try:
                    cur.execute(f"ALTER TABLE conversations ADD COLUMN {col_name} {col_type}")
                except Exception:
                    pass

        # Multi-turn messages
        cur.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            ts REAL
        )""")

        # Escalation queue
        cur.execute("""CREATE TABLE IF NOT EXISTS escalations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER,
            session_id TEXT,
            ts REAL,
            customer TEXT,
            question TEXT,
            draft_answer TEXT,
            human_response TEXT,
            confidence REAL,
            status TEXT
        )""")

        cur.execute("PRAGMA table_info(escalations)")
        esc_cols = {row["name"] for row in cur.fetchall()}
        for col_name, col_type in [("session_id", "TEXT"), ("human_response", "TEXT"), ("draft_answer", "TEXT"), ("confidence", "REAL")]:
            if col_name not in esc_cols:
                try:
                    cur.execute(f"ALTER TABLE escalations ADD COLUMN {col_name} {col_type}")
                except Exception:
                    pass

        # Users and RBAC Table
        cur.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE COLLATE NOCASE,
            password_hash TEXT,
            salt TEXT,
            role TEXT,
            name TEXT,
            created_at REAL
        )""")

        # Support Tickets Table
        cur.execute("""CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_ref TEXT UNIQUE,
            customer_email TEXT,
            issue_description TEXT,
            priority TEXT,
            status TEXT,
            created_at REAL,
            resolved_at REAL
        )""")

        # Mock Business Orders table for tool execution
        cur.execute("""CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            customer_email TEXT,
            item_name TEXT,
            amount REAL,
            status TEXT,
            tracking_code TEXT,
            order_date TEXT,
            days_ago INTEGER
        )""")

        # Mock Customer Accounts table for tool execution
        cur.execute("""CREATE TABLE IF NOT EXISTS accounts (
            customer_email TEXT PRIMARY KEY,
            customer_name TEXT,
            plan_tier TEXT,
            requests_used INTEGER,
            max_requests INTEGER,
            renewal_date TEXT,
            status TEXT
        )""")

        # Seed sample business data if empty
        cur.execute("SELECT count(*) as count FROM orders")
        if cur.fetchone()["count"] == 0:
            sample_orders = [
                ("ORD-9021", "jane@x.com", "Pro Annual Subscription", 290.00, "active", "N/A", "2026-10-20", 5),
                ("ORD-8114", "user@example.com", "Enterprise Add-on (10 Seats)", 500.00, "delivered", "TRACK-USPS-8841", "2026-10-22", 3),
                ("ORD-7201", "alex@company.org", "Custom Integration Hardware Kit", 149.00, "in_transit", "FEDEX-992147", "2026-10-24", 1),
                ("ORD-6003", "oldcustomer@domain.com", "Legacy Starter Pack", 49.00, "delivered", "TRACK-UPS-1102", "2026-03-10", 220),
            ]
            cur.executemany(
                "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)", sample_orders
            )

        cur.execute("SELECT count(*) as count FROM accounts")
        if cur.fetchone()["count"] == 0:
            sample_accounts = [
                ("jane@x.com", "Jane Doe", "Pro", 4200, 10000, "2026-11-20", "active"),
                ("user@example.com", "Demo User", "Enterprise", 48200, 100000, "2026-12-01", "active"),
                ("alex@company.org", "Alex Chen", "Free", 95, 100, "2026-11-01", "approaching_limit"),
                ("test@example.com", "Test Account", "Pro", 120, 10000, "2026-11-15", "active"),
            ]
            cur.executemany(
                "INSERT INTO accounts VALUES (?,?,?,?,?,?,?)", sample_accounts
            )

        # Seed default RBAC users
        cur.execute("SELECT count(*) as count FROM users")
        if cur.fetchone()["count"] == 0:
            import hashlib
            import secrets

            def _hash(pwd: str, s: str = None) -> tuple[str, str]:
                salt = s or secrets.token_hex(16)
                h = hashlib.pbkdf2_hmac("sha256", pwd.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
                return h, salt

            default_users = [
                ("admin@resolvex.ai", "admin123", "admin", "System Administrator"),
                ("agent@resolvex.ai", "agent123", "agent", "Support Agent Jane"),
                ("customer@example.com", "customer123", "customer", "Valued Customer"),
            ]
            for email, pwd, role, name in default_users:
                phash, salt = _hash(pwd)
                cur.execute(
                    "INSERT INTO users (email, password_hash, salt, role, name, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (email, phash, salt, role, name, time.time())
                )

        # Seed sample support tickets
        cur.execute("SELECT count(*) as count FROM tickets")
        if cur.fetchone()["count"] == 0:
            sample_tickets = [
                ("TICK-1001", "jane@x.com", "Request for annual invoice PDF breakdown with VAT ID", "medium", "open", time.time() - 3600, None),
                ("TICK-1002", "user@example.com", "Webhook connection timeouts on EU-Central gateway", "urgent", "in_progress", time.time() - 7200, None),
            ]
            cur.executemany(
                "INSERT INTO tickets (ticket_ref, customer_email, issue_description, priority, status, created_at, resolved_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                sample_tickets
            )

        self.db.commit()

    def record_conversation(self, session_id: str, channel: str, customer: str,
                            question: str, answer: str, confidence: float,
                            escalated: bool, sources: list, tool_calls: list) -> int:
        cur = self.db.cursor()
        cur.execute(
            "INSERT INTO conversations (session_id, ts, channel, customer, question, answer, confidence, "
            "escalated, sources, tool_calls) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (session_id, time.time(), channel, customer, question, answer,
             confidence, int(escalated), json.dumps(sources), json.dumps(tool_calls))
        )
        conv_id = cur.lastrowid

        # Also log to multi-turn messages
        cur.execute("INSERT INTO messages (session_id, role, content, ts) VALUES (?,?,?,?)",
                    (session_id, "user", question, time.time()))
        cur.execute("INSERT INTO messages (session_id, role, content, ts) VALUES (?,?,?,?)",
                    (session_id, "assistant", answer, time.time()))

        if escalated:
            cur.execute(
                "INSERT INTO escalations (conversation_id, session_id, ts, customer, question, "
                "draft_answer, status, confidence) VALUES (?,?,?,?,?,?, 'open', ?)",
                (conv_id, session_id, time.time(), customer, question, answer, confidence)
            )

        self.db.commit()
        return conv_id

    def list_conversations(self, limit: int = 50, search: str = None) -> list[dict]:
        cur = self.db.cursor()
        if search:
            q = f"%{search}%"
            rows = cur.execute(
                "SELECT * FROM conversations WHERE question LIKE ? OR customer LIKE ? OR answer LIKE ? "
                "ORDER BY ts DESC LIMIT ?", (q, q, q, limit)
            ).fetchall()
        else:
            rows = cur.execute(
                "SELECT * FROM conversations ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_conversation(self, conv_id: int) -> dict:
        cur = self.db.cursor()
        row = cur.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
        return dict(row) if row else None

    def set_feedback(self, conv_id: int, feedback: str):
        cur = self.db.cursor()
        cur.execute("UPDATE conversations SET feedback = ? WHERE id = ?", (feedback, conv_id))
        self.db.commit()

    def get_session_messages(self, session_id: str, limit: int = 20) -> list[dict]:
        cur = self.db.cursor()
        rows = cur.execute(
            "SELECT role, content, ts FROM messages WHERE session_id = ? ORDER BY ts ASC LIMIT ?",
            (session_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def list_escalations(self, status: str = "open") -> list[dict]:
        cur = self.db.cursor()
        if status == "all":
            rows = cur.execute("SELECT * FROM escalations ORDER BY ts DESC").fetchall()
        else:
            rows = cur.execute("SELECT * FROM escalations WHERE status = ? ORDER BY ts DESC", (status,)).fetchall()
        return [dict(r) for r in rows]

    def resolve_escalation(self, escalation_id: int, human_response: str = None) -> dict:
        cur = self.db.cursor()
        cur.execute(
            "UPDATE escalations SET status = 'resolved', human_response = ? WHERE id = ?",
            (human_response, escalation_id)
        )
        self.db.commit()
        return {"id": escalation_id, "status": "resolved", "human_response": human_response}

    def get_order(self, order_id: str = None, customer_email: str = None) -> list[dict]:
        cur = self.db.cursor()
        if order_id:
            rows = cur.execute("SELECT * FROM orders WHERE order_id = ? COLLATE NOCASE", (order_id,)).fetchall()
        elif customer_email:
            rows = cur.execute("SELECT * FROM orders WHERE customer_email = ? COLLATE NOCASE", (customer_email,)).fetchall()
        else:
            rows = cur.execute("SELECT * FROM orders LIMIT 10").fetchall()
        return [dict(r) for r in rows]

    def get_account(self, customer_email: str) -> dict:
        cur = self.db.cursor()
        row = cur.execute("SELECT * FROM accounts WHERE customer_email = ? COLLATE NOCASE", (customer_email,)).fetchone()
        return dict(row) if row else None

    def get_analytics(self) -> dict:
        cur = self.db.cursor()
        total_conv = cur.execute("SELECT COUNT(*) as c FROM conversations").fetchone()["c"]
        escalated_count = cur.execute("SELECT COUNT(*) as c FROM conversations WHERE escalated = 1").fetchone()["c"]
        resolved_esc = cur.execute("SELECT COUNT(*) as c FROM escalations WHERE status = 'resolved'").fetchone()["c"]
        avg_conf = cur.execute("SELECT AVG(confidence) as a FROM conversations").fetchone()["a"] or 0.0

        channels_rows = cur.execute("SELECT channel, COUNT(*) as c FROM conversations GROUP BY channel").fetchall()
        channel_dist = {r["channel"]: r["c"] for r in channels_rows}

        recent = cur.execute("SELECT id, ts, customer, question, confidence, escalated FROM conversations ORDER BY ts DESC LIMIT 10").fetchall()

        return {
            "total_conversations": total_conv,
            "escalated_count": escalated_count,
            "resolved_escalations": resolved_esc,
            "automation_rate": round(((total_conv - escalated_count) / total_conv * 100), 1) if total_conv > 0 else 100.0,
            "escalation_rate": round((escalated_count / total_conv * 100), 1) if total_conv > 0 else 0.0,
            "avg_confidence": round(avg_conf, 2),
            "channel_distribution": channel_dist,
            "recent_activity": [dict(r) for r in recent],
        }

    # ---------------------------------------------------------------- User & Auth Methods
    def create_user(self, email: str, password_hash: str, salt: str, role: str = "customer", name: str = None) -> dict:
        cur = self.db.cursor()
        cur.execute(
            "INSERT INTO users (email, password_hash, salt, role, name, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (email.strip().lower(), password_hash, salt, role, name or email.split("@")[0], time.time())
        )
        self.db.commit()
        return {"id": cur.lastrowid, "email": email, "role": role, "name": name}

    def get_user_by_email(self, email: str) -> dict:
        cur = self.db.cursor()
        row = cur.execute("SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email.strip(),)).fetchone()
        return dict(row) if row else None

    def list_users(self) -> list[dict]:
        cur = self.db.cursor()
        rows = cur.execute("SELECT id, email, role, name, created_at FROM users ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------- Support Ticket Methods
    def create_ticket(self, customer_email: str, issue_description: str, priority: str = "medium") -> dict:
        import random
        cur = self.db.cursor()
        ticket_ref = f"TICK-{random.randint(1000, 9999)}"
        ts = time.time()
        cur.execute(
            "INSERT INTO tickets (ticket_ref, customer_email, issue_description, priority, status, created_at) "
            "VALUES (?, ?, ?, ?, 'open', ?)",
            (ticket_ref, customer_email.strip(), issue_description.strip(), priority.lower(), ts)
        )
        self.db.commit()
        return {
            "id": cur.lastrowid,
            "ticket_ref": ticket_ref,
            "customer_email": customer_email,
            "issue_description": issue_description,
            "priority": priority,
            "status": "open",
            "created_at": ts,
        }

    def list_tickets(self, status: str = None, limit: int = 50) -> list[dict]:
        cur = self.db.cursor()
        if status and status != "all":
            rows = cur.execute(
                "SELECT * FROM tickets WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit)
            ).fetchall()
        else:
            rows = cur.execute(
                "SELECT * FROM tickets ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_ticket(self, ticket_ref_or_id: str) -> dict:
        cur = self.db.cursor()
        if str(ticket_ref_or_id).isdigit():
            row = cur.execute("SELECT * FROM tickets WHERE id = ?", (int(ticket_ref_or_id),)).fetchone()
        else:
            row = cur.execute("SELECT * FROM tickets WHERE ticket_ref = ? COLLATE NOCASE", (str(ticket_ref_or_id),)).fetchone()
        return dict(row) if row else None

    def update_ticket_status(self, ticket_ref_or_id: str, status: str) -> dict:
        cur = self.db.cursor()
        resolved_ts = time.time() if status == "resolved" else None
        if str(ticket_ref_or_id).isdigit():
            cur.execute(
                "UPDATE tickets SET status = ?, resolved_at = ? WHERE id = ?",
                (status, resolved_ts, int(ticket_ref_or_id))
            )
        else:
            cur.execute(
                "UPDATE tickets SET status = ?, resolved_at = ? WHERE ticket_ref = ? COLLATE NOCASE",
                (status, resolved_ts, str(ticket_ref_or_id))
            )
        self.db.commit()
        return {"ticket": ticket_ref_or_id, "status": status}

