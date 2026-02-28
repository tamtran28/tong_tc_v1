import streamlit as st
from db.auth_db import authenticate_user
from db.auth_jwt import login_user, is_authenticated

#log
from db.login_logs import log_login


def show_login_page():
    st.title("🔐 ĐĂNG NHẬP CHƯƠNG TRÌNH")

    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Tên đăng nhập")
        password = st.text_input("Mật khẩu", type="password")
        submitted = st.form_submit_button("Đăng nhập")

    if submitted:
        if not username or not password:
            st.error("Vui lòng nhập đầy đủ tên đăng nhập và mật khẩu")
            return

        user = authenticate_user(username, password)

        if user:
            st.success("Đăng nhập thành công!")
            log_login(user["username"])
            login_user(user)
            st.rerun()

        else:
            st.error("Sai tên đăng nhập hoặc mật khẩu!")

def logout_button():
    if st.button("Đăng xuất"):
        from db.auth_jwt import logout
        logout()
        st.rerun()
