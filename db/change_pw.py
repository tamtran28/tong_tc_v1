import streamlit as st
from db.auth_jwt import get_current_user
from db.security import verify_password
from db.auth_db import update_password
from db.user_logs import log_user_action


def change_password_popup():
    user = get_current_user()
    if not user:
        st.error("Bạn chưa đăng nhập!")
        return

    st.subheader("🔐 Đổi mật khẩu")

    old_pw = st.text_input("Mật khẩu cũ", type="password")
    new_pw = st.text_input("Mật khẩu mới", type="password")
    new_pw2 = st.text_input("Nhập lại mật khẩu mới", type="password")

    if st.button("Cập nhật mật khẩu"):
        if not verify_password(old_pw, user["password_hash"]):
            st.error("❌ Mật khẩu cũ không đúng!")
            return

        if new_pw != new_pw2:
            st.error("❌ Mật khẩu mới không khớp!")
            return

        if not update_password(user["username"], new_pw):
            st.error("⚠️ Không tìm thấy tài khoản để cập nhật mật khẩu.")
            return

        log_user_action(user["username"], "Đổi mật khẩu thành công")
        st.success("✅ Đổi mật khẩu thành công! Hãy đăng nhập lại.")
        st.session_state.clear()
        st.rerun()
