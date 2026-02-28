import streamlit as st
from db.user_logs import get_user_logs


def view_my_activity(username):
    """Hiển thị lịch sử hoạt động của chính user đang đăng nhập"""

    st.subheader("🧾 Lịch sử hoạt động của bạn")

    user_logs = get_user_logs(username)

    if not user_logs:
        st.info("⛔ Bạn chưa có hoạt động nào được ghi lại.")
        return

    # Hiển thị dạng bảng
    st.table(
        {
            "Người dùng": [log[0] for log in user_logs],
            "Hoạt động": [log[1] for log in user_logs],
            "Thời gian": [log[2] for log in user_logs],
        }
    )
