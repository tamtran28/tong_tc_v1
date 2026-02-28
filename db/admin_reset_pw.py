import streamlit as st

from db.auth_db import get_all_users, update_password
from db.audit_log import log_action


def admin_reset_password():
    st.subheader("🔄 Reset mật khẩu user")

    users = get_all_users()
    if not users:
        st.info("Chưa có tài khoản nào trong hệ thống.")
        return

    selected = st.selectbox(
        "Chọn user:",
        options=[u["username"] for u in users],
        format_func=lambda uname: next(
            (f"{uname} — {u['full_name']} ({u['role']})" for u in users if u["username"] == uname),
            uname,
        ),
    )

    new_pw = st.text_input("Mật khẩu mới", type="password")
    new_pw_confirm = st.text_input("Nhập lại mật khẩu mới", type="password")

    if st.button("Đổi mật khẩu"):
        if not new_pw:
            st.error("⚠️ Vui lòng nhập mật khẩu mới.")
            return

        if new_pw != new_pw_confirm:
            st.error("⚠️ Mật khẩu nhập lại không khớp.")
            return

        if update_password(selected, new_pw):
            log_action(f"Admin reset mật khẩu cho user {selected}")
            st.success(f"✅ Đã đặt lại mật khẩu cho {selected}. Mật khẩu sẽ được lưu và dùng lại sau khi reboot.")
        else:
            st.error("❌ Không tìm thấy user để cập nhật mật khẩu.")
