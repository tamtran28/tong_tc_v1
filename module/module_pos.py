# =========================================================
# module_pos.py — Xử lý POS (6, 7, 8)
# =========================================================

import streamlit as st
import pandas as pd

from module.error_utils import UserFacingError, _should_reraise
import numpy as np
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import io
from db.security import require_role


# ------------------------------
# Xuất file excel
# ------------------------------
def df_to_excel_bytes(df, sheet="DATA"):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name=sheet[:31], index=False)
    buffer.seek(0)
    return buffer


# ------------------------------
# Chuẩn hóa 6.2a
# ------------------------------
def standardize_6_2a_two_files(file_before, file_after):

    # --- Đọc file trước 23/05 ---
    df_before = pd.read_excel(file_before, dtype=str)

    # --- Đọc file sau 23/05 ---
    df_after = pd.read_excel(file_after, dtype=str)

    # Mapping cho file cũ
    map_before = {
        "MACN_POS": "BRANCH_CODE",
        "IDPOS": "MERCHANT_ID",
        "TENPOS": "MERCHANT_NAME",
        "TRANDT": "TRANS_DATE",
        "TRANAMT_QD": "TRANS_AMT",
    }

    # Mapping file mới
    map_after = {
        "BRANCH_CODE": "BRANCH_CODE",
        "MERCHANT_ID": "MERCHANT_ID",
        "MERCHANT_NAME": "MERCHANT_NAME",
        "TRANS_DATE": "TRANS_DATE",
        "TRANS_AMT": "TRANS_AMT",
    }

    # Lấy đúng cột
    df1 = df_before[[c for c in map_before if c in df_before.columns]].rename(columns=map_before)
    df2 = df_after[[c for c in map_after if c in df_after.columns]].rename(columns=map_after)

    # Ghép
    df = pd.concat([df1, df2], ignore_index=True)

    # Chuẩn hóa ngày
    df["TRANS_DATE"] = pd.to_datetime(df["TRANS_DATE"], errors="coerce")

    # Chuẩn hóa số doanh số
    df["TRANS_AMT"] = (
        df["TRANS_AMT"]
        .astype(str)
        .str.replace(r"[^\d\.-]", "", regex=True)
        .replace("", "0")
        .astype(float)
    )

    df["MERCHANT_ID"] = df["MERCHANT_ID"].astype(str)

    return df


# ------------------------------
# XỬ LÝ POS CHÍNH
# ------------------------------
def process_pos_only(file_before_2305, file_after_2305, file_6_2b,
                     start_audit, end_audit):

    # 6.2a – doanh số POS
    df_trans = standardize_6_2a_two_files(file_before_2305, file_after_2305)

    # 6.2b – danh sách MID
    df_pos = pd.read_excel(file_6_2b, dtype=str)

    # Chuẩn hóa
    if "MID" not in df_pos.columns:
        raise Exception("❌ File 6.2b bị thiếu cột MID!")

    df_pos["MID"] = df_pos["MID"].astype(str)
    df_trans["MERCHANT_ID"] = df_trans["MERCHANT_ID"].astype(str)

    # Chuyển Device status (nếu có)
    if "DEVICE_STATUS" in df_pos.columns:
        df_pos["DEVICE_STATUS"] = df_pos["DEVICE_STATUS"].astype(str)
    else:
        df_pos["DEVICE_STATUS"] = "Unknown"

    # -----------------------------------------------
    # Hàm tính doanh số theo khoảng thời gian
    # -----------------------------------------------
    def cal_rev(df_trans_local, df_pos_local, d1, d2):
        mask = (df_trans_local["TRANS_DATE"] >= d1) & (df_trans_local["TRANS_DATE"] <= d2)
        g = (
            df_trans_local.loc[mask]
            .groupby("MERCHANT_ID")["TRANS_AMT"]
            .sum()
            .reset_index()
            .rename(columns={"MERCHANT_ID": "MID", "TRANS_AMT": "REV"})
        )

        # Merge đúng key MID
        merged = df_pos_local[["MID"]].merge(g, on="MID", how="left")

        return merged["REV"].fillna(0).astype(float)

    # Lấy năm từ end_audit
    y = end_audit.year

    # Tính doanh số T-2, T-1, T
    df_pos["DS_T2"] = cal_rev(df_trans, df_pos, datetime(y - 2, 1, 1), datetime(y - 2, 12, 31))
    df_pos["DS_T1"] = cal_rev(df_trans, df_pos, datetime(y - 1, 1, 1), datetime(y - 1, 12, 31))
    df_pos["DS_T"] = cal_rev(df_trans, df_pos, datetime(y, 1, 1), datetime(y, 12, 31))

    df_pos["TONG_3N"] = df_pos["DS_T2"] + df_pos["DS_T1"] + df_pos["DS_T"]

    # -----------------------------------------
    # 3 tháng gần nhất
    # -----------------------------------------
    start_3m = (end_audit.replace(day=1) - relativedelta(months=2)).replace(day=1)
    df_pos["DS_3T"] = cal_rev(df_trans, df_pos, start_3m, end_audit)
    df_pos["DSBQ_3T"] = (df_pos["DS_3T"] / 3).round(2)

    # -----------------------------------------
    # Tiêu chí POS ĐANG HOẠT ĐỘNG
    # -----------------------------------------
    df_pos["POS_ACTIVE"] = np.where(df_pos["DEVICE_STATUS"] == "Device OK", "X", "")

    # -----------------------------------------
    # TOP POS doanh số cao nhất
    # -----------------------------------------
    df_active = df_pos[df_pos["POS_ACTIVE"] == "X"]

    if not df_active.empty:
        top10_total = df_active.nlargest(10, "TONG_3N")["MID"]
        top10_3T = df_active.nlargest(10, "DS_3T")["MID"]
    else:
        top10_total = pd.Series([], dtype=str)
        top10_3T = pd.Series([], dtype=str)

    df_pos["TOP_3NAM"] = df_pos["MID"].apply(lambda x: "X" if x in top10_total.values else "")
    df_pos["TOP_3THANG"] = df_pos["MID"].apply(lambda x: "X" if x in top10_3T.values else "")

    # -----------------------------------------
    # POS KPS doanh số 3 tháng
    # -----------------------------------------
    df_pos["POS_KPS_3T"] = np.where(
        (df_pos["POS_ACTIVE"] == "X") & (df_pos["DS_3T"] == 0),
        "X",
        "",
    )

    # POS doanh số thấp
    df_pos["POS_DS_THAP"] = np.where(
        (df_pos["POS_ACTIVE"] == "X") & (df_pos["DSBQ_3T"] < 20_000_000),
        "X",
        "",
    )

    return df_pos


# =========================================================
# MODULE STREAMLIT
# =========================================================
def run_module_pos():
    try:
        _run_module_pos()
    except UserFacingError:
        raise
    except Exception as exc:
        if _should_reraise(exc):
            raise

        raise UserFacingError(
            "Đã xảy ra lỗi khi xử lý Tiêu chí máy POS. Vui lòng kiểm tra file đầu vào và thử lại."
        ) from exc


def _run_module_pos():
    
    
    st.markdown("**Upload 3 file:6.2a trước 23/05, 6.2a sau 23/05, 6.2b (MUC51)**")

    start_date = st.date_input("Ngày bắt đầu THKT", value=date(2025, 1, 1))
    end_date = st.date_input("Ngày kết thúc THKT", value=date(2025, 10, 31))

    col1, col2 = st.columns(2)
    with col1:
        file_old = st.file_uploader("📂 6.2a – File TRƯỚC 23/05", type=["xls", "xlsx"])
    with col2:
        file_new = st.file_uploader("📂 6.2a – File SAU 23/05", type=["xls", "xlsx"])

    file_6_2b = st.file_uploader("📂 6.2b – MUC51_sol", type=["xls", "xlsx"])

    run_button = st.button("🚀 Chạy POS")

    if run_button:
        if not file_old or not file_new or not file_6_2b:
            st.error("❌ Thiếu file POS!")
            return

        with st.spinner("⏳ Đang xử lý…"):
            df_pos = process_pos_only(
                file_old,
                file_new,
                file_6_2b,
                start_audit=datetime.combine(start_date, datetime.min.time()),
                end_audit=datetime.combine(end_date, datetime.min.time())
            )

        st.success("✔ Xử lý hoàn tất!")

        st.subheader("📊 Kết quả POS")
        st.dataframe(df_pos, use_container_width=True)

        st.subheader("📥 Tải xuống Excel")
        st.download_button(
            "⬇ Tải file KQ_POS.xlsx",
            data=df_to_excel_bytes(df_pos, "POS"),
            file_name="KQ_POS.xlsx"
        )
