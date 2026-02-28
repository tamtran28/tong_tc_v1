import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(".streamlit", "app.db")

# Tạo bảng log nếu chưa tồn tại
def init_login_log_table():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS login_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            login_time TEXT,
            ip TEXT,
            user_agent TEXT
        )
    """)
    conn.commit()
    conn.close()


def log_login(username, ip="Unknown", user_agent="Unknown"):
    init_login_log_table()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO login_logs (username, login_time, ip, user_agent)
        VALUES (?, ?, ?, ?)
    """, (username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ip, user_agent))
    conn.commit()
    conn.close()


def get_user_logs(username):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT login_time, ip, user_agent 
        FROM login_logs
        WHERE username = ?
        ORDER BY login_time DESC
        LIMIT 100
    """, (username,))
    rows = c.fetchall()
    conn.close()
    return rows


def get_all_logs():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT username, login_time, ip, user_agent
        FROM login_logs
        ORDER BY login_time DESC
        LIMIT 500
    """)
    rows = c.fetchall()
    conn.close()
    return rows
