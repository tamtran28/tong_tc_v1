# db/admin_create_user.py
import streamlit as st
from db.auth_db import create_user
from db.auth_jwt import get_current_user

def admin_create_user_page():
    user = get_current_user()
    if not user or user["role"] != "admin":
        st.error("🚫 Bạn không có quyền truy cập trang này!")
        return

    st.subheader("➕ Tạo tài khoản người dùng mới")

    username = st.text_input("Tên đăng nhập (username)")
    full_name = st.text_input("Họ và tên")
    role = st.selectbox("Quyền truy cập", ["user", "pos", "admin"])
    password = st.text_input("Mật khẩu", type="password")
    password2 = st.text_input("Nhập lại mật khẩu", type="password")

    if st.button("🚀 Tạo User"):
        if password != password2:
            st.error("❌ Mật khẩu nhập lại không đúng!")
            return
        
        ok, msg = create_user(username, full_name, role, password)
        if ok:
            st.success("✅ " + msg)
        else:
            st.error("❌ " + msg)
