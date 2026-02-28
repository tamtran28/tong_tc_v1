import streamlit as st

from db.auth_db import create_user, get_all_users, update_password
from db.audit_log import log_action


# ========== FORM TẠO USER MỚI ==========
def create_user_form():
    st.subheader("👤 Thêm user mới")

    username = st.text_input("Tên đăng nhập mới")
    full_name = st.text_input("Họ tên")
    role = st.selectbox("Quyền:", ["user", "pos", "admin"])
    password = st.text_input("Mật khẩu", type="password")

    if st.button("➕ Tạo user"):
        if create_user(username, full_name, role, password):
            st.success(f"Đã tạo user: {username}")
            log_action(f"Tạo user mới: {username}")
        else:
            st.error("❌ Không thể tạo user. Username có thể đã tồn tại.")


# ========== FORM RESET MẬT KHẨU ==========
def reset_password_form():
    st.subheader("🔄 Reset mật khẩu user")

    users = [u["username"] for u in get_all_users()]
    selected_user = st.selectbox("Chọn user:", users)
    new_pw = st.text_input("Mật khẩu mới", type="password")
    confirm_pw = st.text_input("Nhập lại mật khẩu mới", type="password")

    if st.button("Đổi mật khẩu"):
        if not new_pw:
            st.error("⚠️ Vui lòng nhập mật khẩu mới.")
            return

        if new_pw != confirm_pw:
            st.error("⚠️ Mật khẩu nhập lại không khớp.")
            return

        if update_password(selected_user, new_pw):
            log_action(f"Reset mật khẩu cho user {selected_user}")
            st.success(f"Đã đặt lại mật khẩu cho {selected_user}")
        else:
            st.error("❌ Không thể cập nhật mật khẩu. Vui lòng thử lại.")

