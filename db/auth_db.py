import os
import sqlite3

from db.security import hash_password, verify_password

# 📌 Lưu database vào thư mục persistent của Streamlit Cloud
DB_PATH = os.path.join(".streamlit", "users.db")


def init_db():
    """Tạo bảng user nếu chưa tồn tại"""
    os.makedirs(".streamlit", exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            full_name TEXT,
            role TEXT,
            password_hash TEXT
        )
    """)

    conn.commit()
    conn.close()


def get_user_by_username(username):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT username, full_name, role, password_hash FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()

    if row:
        return {
            "username": row[0],
            "full_name": row[1],
            "role": row[2],
            "password_hash": row[3],
        }
    return None


def authenticate_user(username, password):
    """Kiểm tra thông tin đăng nhập và trả về user nếu hợp lệ"""
    user = get_user_by_username(username)

    if not user:
        return None

    if verify_password(password, user["password_hash"]):
        return user

    return None


def insert_user(username, full_name, role, password):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO users (username, full_name, role, password_hash) VALUES (?, ?, ?, ?)",
        (username, full_name, role, hash_password(password)),
    )
    conn.commit()
    conn.close()


def get_all_users():
    """Lấy toàn bộ user để hiển thị ở màn reset mật khẩu admin."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT username, full_name, role FROM users ORDER BY username ASC")
    users = [
        {"username": row[0], "full_name": row[1], "role": row[2]}
        for row in c.fetchall()
    ]
    conn.close()
    return users

#them
def create_user(username, full_name, role, password):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # check trùng username
    c.execute("SELECT 1 FROM users WHERE username=?", (username,))
    if c.fetchone():
        conn.close()
        return False, "Username đã tồn tại!"

    hashed = hash_password(password)

    c.execute(
        "INSERT INTO users(username, full_name, role, password_hash) VALUES (?, ?, ?, ?)",
        (username, full_name, role, hashed)
    )
    conn.commit()
    conn.close()
    return True, "Tạo user thành công!"
def update_password(username, new_password):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "UPDATE users SET password_hash = ? WHERE username = ?",
        (hash_password(new_password), username),
    )
    updated = c.rowcount
    conn.commit()
    conn.close()
    return updated > 0

# import sqlite3
# from db.security import hash_password, verify_password

# DB_PATH = "db/users.db"

# def init_db():
#     conn = sqlite3.connect(DB_PATH)
#     c = conn.cursor()
#     c.execute("""
#         CREATE TABLE IF NOT EXISTS users (
#             username TEXT PRIMARY KEY,
#             full_name TEXT,
#             role TEXT,
#             password_hash TEXT
#         )
#     """)
#     conn.commit()
#     conn.close()

# def get_user_by_username(username):
#     conn = sqlite3.connect(DB_PATH)
#     c = conn.cursor()
#     c.execute("SELECT username, full_name, role, password_hash FROM users WHERE username=?", (username,))
#     row = c.fetchone()
#     conn.close()

#     if row:
#         return {
#             "username": row[0],
#             "full_name": row[1],
#             "role": row[2],
#             "password_hash": row[3],
#         }
#     return None

# def authenticate_user(username, password):
#     user = get_user_by_username(username)
#     if not user:
#         return None

#     if verify_password(password, user["password_hash"]):
#         return user
#     return None

# #them
# def create_user(username, full_name, role, password):
#     conn = sqlite3.connect(DB_PATH)
#     c = conn.cursor()

#     # check trùng username
#     c.execute("SELECT 1 FROM users WHERE username=?", (username,))
#     if c.fetchone():
#         conn.close()
#         return False, "Username đã tồn tại!"

#     hashed = hash_password(password)

#     c.execute(
#         "INSERT INTO users(username, full_name, role, password_hash) VALUES (?, ?, ?, ?)",
#         (username, full_name, role, hashed)
#     )
#     conn.commit()
#     conn.close()
#     return True, "Tạo user thành công!"

# #
# def update_password(username, new_password):
#     conn = sqlite3.connect(DB_PATH)
#     c = conn.cursor()
#     new_hash = hash_password(new_password)
#     c.execute(
#         "UPDATE users SET password_hash = ? WHERE username = ?",
#         (new_hash, username)
#     )
#     conn.commit()
#     conn.close()
#     return True
# # def verify_password(username, password):
# #     conn = sqlite3.connect(DB_PATH)
# #     c = conn.cursor()

# #     c.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
# #     row = c.fetchone()
# #     conn.close()

# #     if not row:
# #         return False

# #     return verify_hash(password, row[0])


# # def update_password(username, new_hash):
# #     conn = sqlite3.connect(DB_PATH)
# #     c = conn.cursor()

# #     c.execute(
# #         "UPDATE users SET password_hash = ? WHERE username = ?",
# #         (new_hash, username),
# #     )
# #     conn.commit()
# #     conn.close()
