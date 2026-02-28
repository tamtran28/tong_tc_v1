import streamlit as st
from db.audit_log import get_logs

def view_audit_logs():
    st.subheader("📜 Nhật ký hoạt động hệ thống")

    logs = get_logs()
    if not logs:
        st.info("Chưa có log.")
        return

    st.table(
        [
            {"Thời gian": t, "User": u, "Hoạt động": a}
            for (t, u, a) in logs
        ]
    )
