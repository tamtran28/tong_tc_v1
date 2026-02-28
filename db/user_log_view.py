import streamlit as st
from db.login_logs import get_user_logs

def show_user_log(username):
    st.subheader("📜 Lịch sử đăng nhập của bạn")

    logs = get_user_logs(username)

    if not logs:
        st.info("⚠ Chưa có log đăng nhập nào.")
        return

    data = []
    for time, ip, ua in logs:
        data.append({
            "Thời gian": time,
            "IP": ip,
            "Thiết bị": ua[:50] + "..."
        })

    st.table(data)
