
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "tickets.db")))

CATEGORIES = {
    "network": ["network", "wifi", "internet", "vpn", "connection"],
    "access": ["password", "login", "locked", "access", "mfa"],
    "hardware": ["laptop", "keyboard", "monitor", "printer", "hardware"],
    "software": ["application", "software", "crash", "error", "install"],
}

PRIORITY_KEYWORDS = {
    "critical": ["outage", "all users", "production down"],
    "high": ["urgent", "cannot work", "business stopped"],
    "medium": ["slow", "intermittent", "degraded"],
}

VALID_STATUSES = ("open", "in_progress", "resolved", "closed")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def get_connection():
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                requester TEXT NOT NULL,
                category TEXT NOT NULL,
                priority TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="AI Ops Automation API",
    description="IT Operations Ticket Management and Automation API",
    version="1.1.0",
    lifespan=lifespan,
)


class TicketCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=5, max_length=5000)
    requester: str = Field(min_length=2, max_length=200)


class TicketUpdate(BaseModel):
    status: Literal["open", "in_progress", "resolved", "closed"]


class TicketPriorityUpdate(BaseModel):
    priority: Literal["low", "medium", "high", "critical"]


def classify_ticket(title: str, description: str):
    text = f"{title} {description}".lower()

    category = "general"

    for candidate, keywords in CATEGORIES.items():
        if any(keyword in text for keyword in keywords):
            category = candidate
            break

    priority = "low"

    for candidate, keywords in PRIORITY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            priority = candidate
            break

    return {
        "category": category,
        "priority": priority
    }


def get_ticket_or_404(ticket_id: int):
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM tickets WHERE id = ?",
            (ticket_id,)
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Ticket not found"
        )

    return dict(row)


def generate_ai_suggestion(ticket: dict):
    category = ticket["category"]
    priority = ticket["priority"]

    suggestions = {
        "network": (
            "Check network connectivity, verify VPN settings, "
            "test DNS, and review network logs."
        ),

        "access": (
            "Verify user identity, account status, password expiry, "
            "account lockout, and MFA settings."
        ),

        "hardware": (
            "Check power, cables, ports, and device status. "
            "Run hardware diagnostics."
        ),

        "software": (
            "Check application logs, recent changes, installation, "
            "configuration, and error messages."
        ),

        "general": (
            "Collect the error message, identify affected users, "
            "reproduce the issue safely, and review system logs."
        )
    }

    suggestion = suggestions.get(
        category,
        suggestions["general"]
    )

    if priority in ("critical", "high"):
        suggestion += (
            " Escalate immediately according to your "
            "organization's incident response procedure."
        )
    else:
        suggestion += (
            " Document troubleshooting results and update the ticket."
        )

    return {
        "ticket_id": ticket["id"],
        "category": category,
        "priority": priority,
        "suggestion": suggestion,
        "generated_by": "local_rules",
        "note": "Rule-based suggestion, not a live AI model."
    }


@app.get("/")
def root():
    return {
        "status": "running",
        "service": "AI Ops Automation API",
        "version": app.version,
        "docs": "/docs"
    }


@app.get("/health")
def health():
    try:
        with get_connection() as connection:
            connection.execute("SELECT 1").fetchone()

        return {
            "status": "healthy",
            "database": "connected"
        }

    except sqlite3.Error:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable"
        )


@app.post("/tickets", status_code=201)
def create_ticket(ticket: TicketCreate):
    now = utc_now()

    classification = classify_ticket(
        ticket.title,
        ticket.description
    )

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO tickets (
                title,
                description,
                requester,
                category,
                priority,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'open', ?, ?)
            """,
            (
                ticket.title.strip(),
                ticket.description.strip(),
                ticket.requester.strip(),
                classification["category"],
                classification["priority"],
                now,
                now
            )
        )

        ticket_id = cursor.lastrowid

    return get_ticket_or_404(ticket_id)


@app.get("/tickets")
def list_tickets(
    status: Literal[
        "open", "in_progress", "resolved", "closed"
    ] | None = None,

    priority: Literal[
        "low", "medium", "high", "critical"
    ] | None = None,

    limit: int = Query(default=50, ge=1, le=100)
):
    conditions = []
    params = []

    if status:
        conditions.append("status = ?")
        params.append(status)

    if priority:
        conditions.append("priority = ?")
        params.append(priority)

    sql = "SELECT * FROM tickets"

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with get_connection() as connection:
        rows = connection.execute(
            sql,
            params
        ).fetchall()

    return [dict(row) for row in rows]


@app.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: int):
    return get_ticket_or_404(ticket_id)


@app.patch("/tickets/{ticket_id}")
def update_ticket(
    ticket_id: int,
    update: TicketUpdate
):
    get_ticket_or_404(ticket_id)

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE tickets
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                update.status,
                utc_now(),
                ticket_id
            )
        )

    return get_ticket_or_404(ticket_id)


@app.patch("/tickets/{ticket_id}/priority")
def update_ticket_priority(
    ticket_id: int,
    update: TicketPriorityUpdate
):
    get_ticket_or_404(ticket_id)

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE tickets
            SET priority = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                update.priority,
                utc_now(),
                ticket_id
            )
        )

    return get_ticket_or_404(ticket_id)


@app.post("/tickets/{ticket_id}/reclassify")
def reclassify_ticket(ticket_id: int):
    ticket = get_ticket_or_404(ticket_id)

    classification = classify_ticket(
        ticket["title"],
        ticket["description"]
    )

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE tickets
            SET category = ?, priority = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                classification["category"],
                classification["priority"],
                utc_now(),
                ticket_id
            )
        )

    return get_ticket_or_404(ticket_id)


@app.post("/tickets/{ticket_id}/ai-suggestion")
def ticket_ai_suggestion(ticket_id: int):
    ticket = get_ticket_or_404(ticket_id)

    return generate_ai_suggestion(ticket)


@app.get("/reports/summary")
def report_summary():
    with get_connection() as connection:

        total = connection.execute(
            "SELECT COUNT(*) AS count FROM tickets"
        ).fetchone()["count"]

        by_status = connection.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM tickets
            GROUP BY status
            """
        ).fetchall()

        by_priority = connection.execute(
            """
            SELECT priority, COUNT(*) AS count
            FROM tickets
            GROUP BY priority
            """
        ).fetchall()

        by_category = connection.execute(
            """
            SELECT category, COUNT(*) AS count
            FROM tickets
            GROUP BY category
            """
        ).fetchall()

    return {
        "total_tickets": total,

        "by_status": {
            row["status"]: row["count"]
            for row in by_status
        },

        "by_priority": {
            row["priority"]: row["count"]
            for row in by_priority
        },

        "by_category": {
            row["category"]: row["count"]
            for row in by_category
        }
    }
