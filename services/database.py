"""Enterprise Database Service with SQLAlchemy 2.0 & Connection Pooling.

Supports PostgreSQL via asyncpg for high-concurrency cloud deployments (Kubernetes, AWS RDS)
with graceful SQLite/aiosqlite fallback for standalone development environments.
"""

import json
import logging
import os
import time
from typing import AsyncGenerator, Dict, List, Optional
from pathlib import Path

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Text,
    select,
    update,
    delete,
    func
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import QueuePool, NullPool

logger = logging.getLogger("support_agent.database")

Base = declarative_base()


# --------------------------------------------------------------------------
# Declarative Models
# --------------------------------------------------------------------------

class ConversationModel(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(128), index=True)
    ts = Column(Float, index=True)
    channel = Column(String(32), default="web")
    customer = Column(String(255), index=True)
    question = Column(Text)
    answer = Column(Text)
    confidence = Column(Float)
    escalated = Column(Integer, default=0)
    sources = Column(Text)  # JSON-encoded array
    tool_calls = Column(Text)  # JSON-encoded array
    feedback = Column(String(32), nullable=True)


class MessageModel(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(128), index=True)
    role = Column(String(32))
    content = Column(Text)
    ts = Column(Float)


class EscalationModel(Base):
    __tablename__ = "escalations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, index=True, nullable=True)
    session_id = Column(String(128), index=True, nullable=True)
    ts = Column(Float, index=True)
    customer = Column(String(255), index=True)
    question = Column(Text)
    draft_answer = Column(Text, nullable=True)
    human_response = Column(Text, nullable=True)
    confidence = Column(Float, default=0.0)
    status = Column(String(32), default="open", index=True)


class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    salt = Column(String(255), nullable=False)
    role = Column(String(32), default="customer")
    name = Column(String(255), default="User")
    created_at = Column(Float)


class TicketModel(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_ref = Column(String(64), unique=True, index=True, nullable=False)
    customer_email = Column(String(255), index=True, nullable=False)
    issue_description = Column(Text, nullable=False)
    priority = Column(String(32), default="normal")
    status = Column(String(32), default="open", index=True)
    created_at = Column(Float)
    resolved_at = Column(Float, nullable=True)


class OrderModel(Base):
    __tablename__ = "orders"

    order_id = Column(String(64), primary_key=True)
    customer_email = Column(String(255), index=True)
    status = Column(String(64))
    order_date = Column(String(64))
    items = Column(Text)  # JSON-encoded array
    total_amount = Column(Float)
    currency = Column(String(8), default="USD")


# --------------------------------------------------------------------------
# Connection Pooling & Engine Initialization
# --------------------------------------------------------------------------

class AsyncDatabaseManager:
    def __init__(self, database_url: Optional[str] = None):
        if not database_url:
            raw_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./crm.db")
            # Convert standard postgresql:// to async postgresql+asyncpg:// if needed
            if raw_url.startswith("postgresql://") and not raw_url.startswith("postgresql+asyncpg://"):
                raw_url = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
            elif raw_url.startswith("sqlite://") and not raw_url.startswith("sqlite+aiosqlite://"):
                raw_url = raw_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
            self.database_url = raw_url
        else:
            self.database_url = database_url

        self.is_postgres = "postgresql" in self.database_url
        self.engine = self._build_engine()
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            class_=AsyncSession
        )

    def _build_engine(self):
        if self.is_postgres:
            logger.info("Initializing PostgreSQL async engine with QueuePool (pool_size=10, max_overflow=20)")
            return create_async_engine(
                self.database_url,
                poolclass=QueuePool,
                pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
                max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=False
            )
        else:
            logger.info("Initializing SQLite async engine (aiosqlite)")
            return create_async_engine(
                self.database_url,
                poolclass=NullPool,
                echo=False
            )

    async def init_schema(self):
        """Create tables if they do not exist."""
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info(f"Database schema initialized successfully on {self.database_url}")
            await self._seed_default_orders()
        except Exception as err:
            logger.error(f"Failed to initialize database schema: {err}", exc_info=True)

    async def _seed_default_orders(self):
        """Seed initial mock orders for tool calling demonstrations if empty."""
        async with self.session_factory() as session:
            result = await session.execute(select(func.count(OrderModel.order_id)))
            count = result.scalar()
            if count == 0:
                demo_orders = [
                    OrderModel(
                        order_id="ORD-9021",
                        customer_email="customer@example.com",
                        status="Delivered",
                        order_date="2026-10-18",
                        items=json.dumps([{"sku": "RSX-PRO-01", "name": "ResolveX Spatial Audio ANC Pro", "qty": 1, "price": 149.99}]),
                        total_amount=149.99,
                        currency="USD"
                    ),
                    OrderModel(
                        order_id="ORD-5542",
                        customer_email="customer@example.com",
                        status="Shipped",
                        order_date="2026-10-22",
                        items=json.dumps([{"sku": "RSX-CHG-02", "name": "ResolveX HyperCharge GaN 100W", "qty": 2, "price": 39.99}]),
                        total_amount=79.98,
                        currency="USD"
                    ),
                    OrderModel(
                        order_id="ORD-1004",
                        customer_email="customer@example.com",
                        status="Processing",
                        order_date="2026-10-24",
                        items=json.dumps([{"sku": "RSX-HUB-03", "name": "ResolveX Nexus 8-in-1 USB4 Hub", "qty": 1, "price": 69.50}]),
                        total_amount=69.50,
                        currency="USD"
                    )
                ]
                session.add_all(demo_orders)
                await session.commit()
                logger.info("Seeded initial mock enterprise orders for tool calling.")

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Async context manager session provider."""
        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def close(self):
        """Dispose of the connection pool."""
        await self.engine.dispose()
        logger.info("Database connection pool disposed.")


# Global default async database manager instance
db_manager = AsyncDatabaseManager()
