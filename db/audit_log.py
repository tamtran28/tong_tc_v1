import os
import sqlite3
from datetime import datetime

from db.auth_db import DB_PATH, init_db


def _ensure_table():
    init_db()
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            username TEXT,
            action TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def log_action(action: str, username="admin"):
    _ensure_table()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO audit_log (timestamp, username, action) VALUES (?, ?, ?)",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), username, action),
    )
    conn.commit()
    conn.close()


def get_logs():
    _ensure_table()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT timestamp, username, action FROM audit_log ORDER BY id DESC")
    logs = c.fetchall()
    conn.close()
    return logs
