import json
import os
import sqlite3
import time

DB_PATH = os.path.join(os.getcwd(), "data", "recovery.db")

_conn_cache = None

def get_conn() -> sqlite3.Connection:
    global _conn_cache
    if _conn_cache is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _conn_cache = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn_cache.execute("PRAGMA journal_mode=WAL")
        _conn_cache.execute("PRAGMA synchronous=NORMAL")
        _init_tables(_conn_cache)
    return _conn_cache

def _init_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS seen_messages (
            message_id TEXT PRIMARY KEY
        );
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            data TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS payment_intents (
            conversation_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            hold_id TEXT,
            charge_id TEXT,
            ticket_id TEXT,
            state TEXT NOT NULL DEFAULT 'holding',
            updated_at REAL NOT NULL,
            PRIMARY KEY (conversation_id, run_id)
        );
    """)
    conn.commit()

def mark_seen(message_id: str) -> bool:
    """Returns True if this is a NEW message, False if already seen."""
    conn = get_conn()
    try:
        conn.execute("INSERT INTO seen_messages (message_id) VALUES (?)", (message_id,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def save_run(run: dict) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO runs (run_id, conversation_id, status, data, created_at) VALUES (?, ?, ?, ?, ?)",
        (run["run_id"], run["conversation_id"], run["status"], json.dumps(run), time.time())
    )
    conn.commit()

def save_payment_intent(conversation_id: str, run_id: str, hold_id: str = None,
                         charge_id: str = None, ticket_id: str = None, state: str = "holding") -> None:
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO payment_intents (conversation_id, run_id, hold_id, charge_id, ticket_id, state, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (conversation_id, run_id, hold_id, charge_id, ticket_id, state, time.time())
    )
    conn.commit()

def update_payment_state(conversation_id: str, run_id: str, **updates) -> None:
    conn = get_conn()
    sets = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [time.time(), conversation_id, run_id]
    conn.execute(f"UPDATE payment_intents SET {sets}, updated_at = ? WHERE conversation_id = ? AND run_id = ?", vals)
    conn.commit()

def get_incomplete_payments() -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT conversation_id, run_id, hold_id, charge_id, ticket_id, state FROM payment_intents WHERE state NOT IN ('done', 'failed')"
    ).fetchall()
    return [{"conversation_id": r[0], "run_id": r[1], "hold_id": r[2], "charge_id": r[3], "ticket_id": r[4], "state": r[5]} for r in rows]

def complete_payment(conversation_id: str, run_id: str, ticket_id: str = None) -> None:
    update_payment_state(conversation_id, run_id, state="done", ticket_id=ticket_id)

def fail_payment(conversation_id: str, run_id: str) -> None:
    update_payment_state(conversation_id, run_id, state="failed")
