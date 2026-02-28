# ==========================================================
# module/hdv.py
# HDV – 3 TIÊU CHÍ (TC1–TC3) + VALIDATE SOL/CHI NHÁNH
# ==========================================================

import re
import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

from module.error_utils import ensure_required_columns, render_error, UserFacingError,validate_sol_only


# ==========================================================
# UTILITIES
# ==========================================================

def download_excel(df: pd.DataFrame, filename: str):
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="data")
    buffer.seek(0)

    st.download_button(
        label="📥 Tải xuống " + filename,
        data=buffer.getvalue(),
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"download_{filename}",
    )


# def validate_sol_or_branch(raw: str, field_label: str = "mã SOL / tên chi nhánh") -> str:
#     """
#     Accept:
#       - SOL: đúng 3 chữ số (001, 123...)
#       - Tên chi nhánh: chữ + khoảng trắng (có dấu)
#     Return:
#       - Chuỗi chuẩn hoá để dùng filter (uppercase + strip)
#     Raise:
#       - UserFacingError nếu không hợp lệ
#     """
#     if raw is None:
#         raise UserFacingError(f"Vui lòng nhập {field_label}.")

#     s = str(raw).strip()
#     if s == "":
#         raise UserFacingError(f"Vui lòng nhập {field_label} (ví dụ: 1000).")

#     # Nếu là SOL: chỉ số và đúng 3 ký tự
#     if s.isdigit():
#         if len(s) != 4:
#             raise UserFacingError("Mã SOL phải gồm đúng 4 chữ số (ví dụ: 1000).")
#         return s  # giữ nguyên 3 số

#     # Nếu là tên chi nhánh: chỉ chữ và khoảng trắng (hỗ trợ tiếng Việt có dấu)
#     if not re.fullmatch(r"[A-Za-zÀ-ỹ\s]+", s):
#         raise UserFacingError(
#             "Tên chi nhánh chỉ được chứa chữ cái và khoảng trắng (không dùng số/ký tự đặc biệt)."
#         )

#     return s.upper()


def filter_by_sol_contains(df: pd.DataFrame, col: str, pattern: str) -> pd.DataFrame:
    """
    Lọc contains (case-insensitive). pattern đã được validate trước.
    """
    if pattern is None or str(pattern).strip() == "":
        return df
    return df[df[col].astype(str).str.upper().str.contains(str(pattern).upper(), na=False)]


# ==========================================================
# MAIN
# ==========================================================

def run_hdv():
    st.markdown(
        """
Các file uplod gồm:
- **TC1**: HDV CKH + so sánh FTP + LS thực trả  
- **TC2**: Xếp hạng KH theo số dư  
- **TC3**: Giao dịch tiền gửi rút – mở/rút trong ngày  
"""
    )

    tab1, tab2, tab3 = st.tabs(["📌 TIÊU CHÍ 1", "📌 TIÊU CHÍ 2", "📌 TIÊU CHÍ 3"])

    # ================================================================
    #                        TIÊU CHÍ 1
    # ================================================================
    # =========================
# TIÊU CHÍ 1 – HDV CKH + FTP + LS THỰC TRẢ
# =========================

    with tab1:
        st.subheader("📌 TIÊU CHÍ 1 – HDV CKH + FTP + LS THỰC TRẢ")
    
        hdv_files = st.file_uploader(
            "📁 Tải các file HDV CKH (*.xls, *.xlsx)",
            type=["xls", "xlsx"],
            accept_multiple_files=True,
            key="tc1_hdv_files",
        )
    
        ftp_files = st.file_uploader(
            "📁 Tải các file FTP (*.xls, *.xlsx)",
            type=["xls", "xlsx"],
            accept_multiple_files=True,
            key="tc1_ftp_files",
        )
    
        tt_file = st.file_uploader(
            "📁 Tải file Lãi suất thực trả",
            type=["xls", "xlsx"],
            key="tc1_tt_file",
        )
    
        st.info("✅ Nhập mã SOL (VD: 1000)")
        chi_nhanh_tc1_raw = st.text_input(
            "🔍 Nhập mã SOL",
            value="",
            key="tc1_sol_input",
        )
    
        run_tc1 = st.button("🚀 Chạy TIÊU CHÍ 1", key="tc1_run_btn")
    
        if run_tc1:
            if not (hdv_files and ftp_files and tt_file):
                st.error("⚠ Vui lòng tải đầy đủ 3 loại file!")
            else:
                try:
                    # =========================
                    # VALIDATE SOL
                    # =========================
                    chi_nhanh_tc1 = validate_sol_only(chi_nhanh_tc1_raw)
    
                    # =========================
                    # REQUIRED COLUMNS
                    # =========================
                    cols_ckh = [
                        "BRCD", "DEPTCD", "CUST_TYPE", "NMLOC", "CUSTSEQ", "BIRTH_DAY",
                        "IDXACNO", "SCHM_NAME", "TERM_DAYS", "GL_SUB", "CCYCD",
                        "CURBAL_NT", "CURBAL_VN", "OPNDT_FIRST", "OPNDT_EFFECT",
                        "MATDT", "LS_GHISO", "LS_CONG_BO", "PROMO_CD", "KH_VIP",
                        "CIF_OPNDT", "DP_MTHS", "DP_DAYS", "PROMO_NM", "PHANKHUC_KH"
                    ]
    
                    cols_ftp_use = ["IDXACNO", "LS_FTP"]
    
                    # =========================
                    # READ CKH (KHÓA CỘT)
                    # =========================
                    df_ckh = pd.concat(
                        [
                            pd.read_excel(f, dtype=str, usecols=cols_ckh)
                            for f in hdv_files
                        ],
                        ignore_index=True
                    )
                    ensure_required_columns(df_ckh, cols_ckh)
                    df_ckh = df_ckh.loc[:, cols_ckh]
    
                    # =========================
                    # READ FTP (KHÓA CỘT NGAY TỪ ĐẦU)
                    # =========================
                    df_ftp = pd.concat(
                        [
                            pd.read_excel(f, dtype=str, usecols=cols_ftp_use)
                            for f in ftp_files
                        ],
                        ignore_index=True
                    )
                    ensure_required_columns(df_ftp, cols_ftp_use)
                    df_ftp = df_ftp.loc[:, cols_ftp_use].drop_duplicates()
    
                    # =========================
                    # FILTER BY SOL
                    # =========================
                    df_filtered = filter_by_sol_contains(df_ckh, "BRCD", chi_nhanh_tc1)
    
                    # =========================
                    # READ LS THỰC TRẢ (CHỈ LẤY 2 CỘT)
                    # =========================
                    df_tt_raw = pd.read_excel(tt_file, dtype=str)
                    ensure_required_columns(df_tt_raw, ["Số tài khoản", "Lãi suất thực trả"])
    
                    df_tt = (
                        df_tt_raw.rename(
                            columns={
                                "Số tài khoản": "IDXACNO",
                                "Lãi suất thực trả": "LS_THUC_TRA",
                            }
                        )
                        .loc[:, ["IDXACNO", "LS_THUC_TRA"]]
                        .drop_duplicates()
                    )
    
                    # =========================
                    # MERGE (KHÔNG BAO GIỜ DƯ CỘT)
                    # =========================
                    df_merge = df_filtered.merge(
                        df_ftp,
                        on="IDXACNO",
                        how="left"
                    )
    
                    df_merge = df_merge.merge(
                        df_tt,
                        on="IDXACNO",
                        how="left"
                    )
    
                    # =========================
                    # CONVERT TO NUMERIC
                    # =========================
                    for c in ["LS_GHISO", "LS_CONG_BO", "LS_FTP", "LS_THUC_TRA"]:
                        df_merge[c] = pd.to_numeric(df_merge[c], errors="coerce")
    
                    # =========================
                    # BUSINESS RULES
                    # =========================
                    df_merge["LSGS ≠ LSCB"] = (
                        df_merge["LS_GHISO"] != df_merge["LS_CONG_BO"]
                    ).map({True: "X", False: ""})
    
                    df_merge["Không có LS trình duyệt"] = (
                        df_merge["LS_THUC_TRA"].isna()
                    ).map({True: "X", False: ""})
    
                    df_merge["LSGS > FTP"] = (
                        df_merge["LS_GHISO"] > df_merge["LS_FTP"]
                    ).map({True: "X", False: ""})
    
                    # =========================
                    # FINAL COLUMN LOCK (CHỐNG DƯ CỘT TUYỆT ĐỐI)
                    # =========================
                    final_cols = cols_ckh + [
                        "LS_FTP",
                        "LS_THUC_TRA",
                        "LSGS ≠ LSCB",
                        "Không có LS trình duyệt",
                        "LSGS > FTP",
                    ]
    
                    df_merge = df_merge.loc[:, final_cols]
    
                    # =========================
                    # OUTPUT
                    # =========================
                    st.success("✔ Tiêu chí 1 hoàn tất!")
                    st.dataframe(df_merge, use_container_width=True)
                    download_excel(df_merge, "TC1.xlsx")
    
                except UserFacingError as exc:
                    render_error(str(exc))
                except Exception as exc:
                    render_error(
                        "❌ Không thể xử lý Tiêu chí 1. Vui lòng kiểm tra file đầu vào.",
                        exc,
                    )

    # with tab1:
    #     st.subheader("📌 TIÊU CHÍ 1 – HDV CKH + FTP + LS THỰC TRẢ")

    #     hdv_files = st.file_uploader(
    #         "📁 Tải các file HDV CKH (*.xls, *.xlsx)",
    #         type=["xls", "xlsx"],
    #         accept_multiple_files=True,
    #         key="tc1_hdv_files",
    #     )
    #     ftp_files = st.file_uploader(
    #         "📁 Tải các file FTP (*.xls, *.xlsx)",
    #         type=["xls", "xlsx"],
    #         accept_multiple_files=True,
    #         key="tc1_ftp_files",
    #     )
    #     tt_file = st.file_uploader(
    #         "📁 Tải file Lãi suất thực trả",
    #         type=["xls", "xlsx"],
    #         key="tc1_tt_file",
    #     )
    #     st.info("✅ Nhập mã SOL (VD: 1000)")
    #     chi_nhanh_tc1_raw = st.text_input(
    #         "🔍 Nhập mã SOL",
    #         value="",
    #         key="tc1_sol_input",
    #     )

    #     run_tc1 = st.button("🚀 Chạy TIÊU CHÍ 1", key="tc1_run_btn")

    #     if run_tc1:
    #         if not (hdv_files and ftp_files and tt_file):
    #             st.error("⚠ Vui lòng tải đầy đủ 3 loại file!")
    #         else:
    #             try:
    #                 chi_nhanh_tc1 = validate_sol_only(chi_nhanh_tc1_raw)

    #                 cols_ckh = [
    #                     "BRCD", "DEPTCD", "CUST_TYPE", "NMLOC", "CUSTSEQ", "BIRTH_DAY", "IDXACNO",
    #                     "SCHM_NAME", "TERM_DAYS", "GL_SUB", "CCYCD", "CURBAL_NT", "CURBAL_VN",
    #                     "OPNDT_FIRST", "OPNDT_EFFECT", "MATDT", "LS_GHISO", "LS_CONG_BO",
    #                     "PROMO_CD", "KH_VIP", "CIF_OPNDT", "DP_MTHS", "DP_DAYS", "PROMO_NM", "PHANKHUC_KH"
    #                 ]

    #                 df_ckh = pd.concat([pd.read_excel(f, dtype=str) for f in hdv_files], ignore_index=True)
    #                 ensure_required_columns(df_ckh, cols_ckh)
    #                 df_ckh = df_ckh[cols_ckh]

    #                 cols_ftp = ["CUSTSEQ", "NMLOC", "IDXACNO", "KY_HAN", "LS_FTP"]
    #                 df_ftp = pd.concat([pd.read_excel(f, dtype=str) for f in ftp_files], ignore_index=True)
    #                 ensure_required_columns(df_ftp, cols_ftp)
    #                 df_ftp = df_ftp[cols_ftp]

    #                 # Lọc theo SOL/chi nhánh
    #                 df_filtered = filter_by_sol_contains(df_ckh, "BRCD", chi_nhanh_tc1)

    #                 df_tt_raw = pd.read_excel(tt_file, dtype=str)
    #                 ensure_required_columns(df_tt_raw, ["Số tài khoản", "Lãi suất thực trả"])

    #                 df_tt = df_tt_raw.rename(
    #                     columns={"Số tài khoản": "IDXACNO", "Lãi suất thực trả": "LS_THUC_TRA"}
    #                 )

    #                 df_merge = df_filtered.merge(
    #                     df_ftp[["IDXACNO", "LS_FTP"]].drop_duplicates(),
    #                     on="IDXACNO",
    #                     how="left",
    #                 )
    #                 df_merge = df_merge.merge(df_tt, on="IDXACNO", how="left")

    #                 df_merge["LS_GHISO"] = pd.to_numeric(df_merge["LS_GHISO"], errors="coerce")
    #                 df_merge["LS_CONG_BO"] = pd.to_numeric(df_merge["LS_CONG_BO"], errors="coerce")
    #                 df_merge["LS_THUC_TRA"] = pd.to_numeric(df_merge["LS_THUC_TRA"], errors="coerce")
    #                 df_merge["LS_FTP"] = pd.to_numeric(df_merge["LS_FTP"], errors="coerce")

    #                 df_merge["LSGS ≠ LSCB"] = (df_merge["LS_GHISO"] != df_merge["LS_CONG_BO"]).map({True: "X", False: ""})
    #                 df_merge["Không có LS trình duyệt"] = df_merge["LS_THUC_TRA"].isna().map({True: "X", False: ""})
    #                 df_merge["LSGS > FTP"] = (df_merge["LS_GHISO"] > df_merge["LS_FTP"]).map({True: "X", False: ""})

    #                 st.success("✔ Tiêu chí 1 hoàn tất!")
    #                 st.dataframe(df_merge, use_container_width=True)
    #                 download_excel(df_merge, "TC1.xlsx")

    #             except UserFacingError as exc:
    #                 render_error(str(exc))
    #             except Exception as exc:
    #                 render_error(
    #                     "Không thể xử lý Tiêu chí 1. Vui lòng kiểm tra định dạng và cột dữ liệu trong các file CKH/FTP/LS.",
    #                     exc,
    #                 )

    # ================================================================
    #                        TIÊU CHÍ 2
    # ================================================================
    with tab2:
        st.subheader("📌 TIÊU CHÍ 2 – Xếp hạng KH theo số dư")
      

        ckh_tc2 = st.file_uploader(
            "📁 Tải file HDV CHI TIẾT CKH",
            type=["xls", "xlsx"],
            accept_multiple_files=True,
            key="tc2_ckh_files",
        )
        kkh_tc2 = st.file_uploader(
            "📁 Tải file HDV CHI TIẾT KKH",
            type=["xls", "xlsx"],
            accept_multiple_files=True,
            key="tc2_kkh_files",
        )
        st.info("✅ Nhập mã SOL** (VD: 1000)")
        chi_nhanh_tc2_raw = st.text_input(
            "🔍 Nhập mã SOL",
            value="",
            key="tc2_sol_input",
        )

        run_tc2 = st.button("🚀 Chạy TIÊU CHÍ 2", key="tc2_run_btn")

        if run_tc2:
            if not (ckh_tc2 and kkh_tc2):
                st.error("⚠ Vui lòng tải file CKH và KKH!")
            else:
                try:
                    chi_nhanh_tc2 = validate_sol_only(chi_nhanh_tc2_raw)

                    cols = [
                        "BRCD", "DEPTCD", "CUST_TYPE", "CUSTSEQ", "NMLOC", "BIRTH_DAY", "IDXACNO",
                        "SCHM_NAME", "TERM_DAYS", "GL_SUB", "CCYCD", "CURBAL_NT", "CURBAL_VN",
                        "OPNDT_FIRST", "OPNDT_EFFECT", "MATDT", "LS_GHISO", "LS_CONG_BO", "PROMO_CD",
                        "KH_VIP", "CIF_OPNDT"
                    ]

                    df_ckh2 = pd.concat([pd.read_excel(f, dtype=str) for f in ckh_tc2], ignore_index=True)
                    df_kkh2 = pd.concat([pd.read_excel(f, dtype=str) for f in kkh_tc2], ignore_index=True)

                    ensure_required_columns(df_ckh2, cols)
                    ensure_required_columns(df_kkh2, cols)

                    df_all = pd.concat([df_ckh2[cols], df_kkh2[cols]], ignore_index=True)
                    df_filtered = filter_by_sol_contains(df_all, "BRCD", chi_nhanh_tc2)

                    df_filtered["CURBAL_VN"] = pd.to_numeric(df_filtered["CURBAL_VN"], errors="coerce")

                    df_sum = (
                        df_filtered.groupby("CUSTSEQ", as_index=False)["CURBAL_VN"]
                        .sum()
                        .rename(columns={"CURBAL_VN": "SỐ DƯ"})
                    )
                    df_tonghop = df_filtered.drop_duplicates("CUSTSEQ").merge(df_sum, on="CUSTSEQ", how="left")

                    today = pd.Timestamp.today().normalize()
                    df_tonghop["BIRTH_DAY"] = pd.to_datetime(df_tonghop["BIRTH_DAY"], errors="coerce")

                    mask = df_tonghop["CUST_TYPE"] == "KHCN"
                    df_tonghop.loc[mask, "ĐỘ TUỔI"] = df_tonghop.loc[mask, "BIRTH_DAY"].apply(
                        lambda x: today.year - x.year - ((today.month, today.day) < (x.month, x.day)) if pd.notnull(x) else None
                    )

                    df_tonghop["RANK_RAW"] = df_tonghop.groupby("CUST_TYPE")["SỐ DƯ"].rank(method="min", ascending=False)

                    for t in ["KHDN", "KHCN"]:
                        for n in [10, 15, 20]:
                            df_tonghop[f"TOP{n}_{t}"] = df_tonghop.apply(
                                lambda x: "X" if x["CUST_TYPE"] == t and x["RANK_RAW"] <= n else "",
                                axis=1,
                            )

                    df_tonghop["RANK"] = df_tonghop["RANK_RAW"].apply(lambda x: int(x) if x <= 20 else "")

                    df_final = df_tonghop.rename(
                        columns={
                            "BRCD": "SOL",
                            "CUST_TYPE": "LOAI KH",
                            "CUSTSEQ": "CIF",
                            "NMLOC": "HO TEN",
                            "BIRTH_DAY": "NGAY SINH/NGAY TL",
                            "KH_VIP": "KH VIP",
                        }
                    )

                    st.success("✔ Tiêu chí 2 hoàn tất!")
                    st.dataframe(df_final, use_container_width=True)
                    download_excel(df_final, "TC2.xlsx")

                except UserFacingError as exc:
                    render_error(str(exc))
                except Exception as exc:
                    render_error(
                        "Không thể xử lý Tiêu chí 2. Vui lòng kiểm tra định dạng và cột dữ liệu trong file CKH/KKH.",
                        exc,
                    )

    # ================================================================
    #                        TIÊU CHÍ 3
    # ================================================================
    with tab3:
        st.subheader("📌 TIÊU CHÍ 3 – Giao dịch tiền gửi rút")
       
        tc3_file = st.file_uploader(
            "📁 Tải file giao dịch (Mục 11)",
            type=["xls", "xlsx"],
            key="tc3_file_muc11",
        )
        st.info("✅ Nhập mã SOL (VD: 1000).")
        chi_nhanh_tc3_raw = st.text_input(
            "🔍 Nhập mã SOL",
            value="",
            key="tc3_sol_input",
        )

        run_tc3 = st.button("🚀 Chạy TIÊU CHÍ 3", key="tc3_run_btn")

        if run_tc3:
            if not tc3_file:
                st.error("⚠ Vui lòng tải file TC3!")
            else:
                try:
                    chi_nhanh_tc3 = validate_sol_only(chi_nhanh_tc3_raw)

                    df = pd.read_excel(tc3_file, dtype=str)
                    ensure_required_columns(
                        df,
                        ["NGAY_HACH_TOAN", "ACCT_OPN_DATE", "PART_CLOSE_AMT", "SOL_ID"],
                    )

                    df["NGAY_HACH_TOAN"] = pd.to_datetime(df["NGAY_HACH_TOAN"], errors="coerce")
                    df["ACCT_OPN_DATE"] = pd.to_datetime(df["ACCT_OPN_DATE"], errors="coerce")
                    df["PART_CLOSE_AMT"] = pd.to_numeric(df["PART_CLOSE_AMT"], errors="coerce")

                    df = filter_by_sol_contains(df, "SOL_ID", chi_nhanh_tc3)

                    df["CHENH_LECH_NGAY"] = (df["NGAY_HACH_TOAN"] - df["ACCT_OPN_DATE"]).dt.days

                    df["MO_RUT_CUNG_NGAY"] = df["CHENH_LECH_NGAY"].apply(lambda x: "X" if x == 0 else "")
                    df["MO_RUT_1_3_NGAY"] = df["CHENH_LECH_NGAY"].apply(lambda x: "X" if 0 < x <= 3 else "")
                    df["MO_RUT_4_7_NGAY"] = df["CHENH_LECH_NGAY"].apply(lambda x: "X" if 4 <= x <= 7 else "")
                    df["GD_LON_HON_1TY"] = df["PART_CLOSE_AMT"].apply(
                        lambda x: "X" if pd.notna(x) and x > 1_000_000_000 else ""
                    )

                    today = pd.Timestamp.today().normalize()
                    df["TRONG_THOI_HIEU_CAMERA"] = df["NGAY_HACH_TOAN"].apply(
                        lambda x: "X" if pd.notna(x) and (today - x).days <= 90 else ""
                    )

                    st.success("✔ Tiêu chí 3 hoàn tất!")
                    st.dataframe(df, use_container_width=True)
                    download_excel(df, "TC3.xlsx")

                except UserFacingError as exc:
                    render_error(str(exc))
                except Exception as exc:
                    render_error(
                        "Không thể xử lý Tiêu chí 3. Vui lòng kiểm tra định dạng file Mục 11 và các cột ngày/số tiền.",
                        exc,
                    )

# import streamlit as st
# import pandas as pd
# import numpy as np
# from io import BytesIO
# import datetime

# from module.error_utils import ensure_required_columns, render_error, UserFacingError

# # ==========================================================
# #      MODULE XỬ LÝ HDV – 3 TIÊU CHÍ
# # ==========================================================

# def download_excel(df, filename):
#     buffer = BytesIO()
#     df.to_excel(buffer, index=False)
#     buffer.seek(0)
#     st.download_button(
#         label="📥 Tải xuống " + filename,
#         data=buffer,
#         file_name=filename,
#         mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
#     )

# def run_hdv():

#     st.header("💳 PHÂN HỆ HDV – 3 TIÊU CHÍ")

#     st.markdown("""
#     Gồm:
#     - **TC1**: HDV CKH + so sánh FTP + LS thực trả  
#     - **TC2**: Xếp hạng KH theo số dư  
#     - **TC3**: Giao dịch tiền gửi rút – mở/rút trong ngày  
#     """)

#     tab1, tab2, tab3 = st.tabs(["📌 TIÊU CHÍ 1", "📌 TIÊU CHÍ 2", "📌 TIÊU CHÍ 3"])

#     # ================================================================
#     #                        TIÊU CHÍ 1
#     # ================================================================
#     with tab1:
#         st.subheader("📌 TIÊU CHÍ 1 – HDV CKH + FTP + LS THỰC TRẢ")

#         hdv_files = st.file_uploader("📁 Tải các file HDV CKH (*.xls, *.xlsx)", type=['xls', 'xlsx'], accept_multiple_files=True)
#         ftp_files = st.file_uploader("📁 Tải các file FTP (*.xls, *.xlsx)", type=['xls','xlsx'], accept_multiple_files=True)
#         tt_file = st.file_uploader("📁 Tải file Lãi suất thực trả", type=['xls','xlsx'])

#         chi_nhanh_tc1 = st.text_input("🔍 Nhập mã SOL", "").upper().strip()

#         if st.button("🚀 Chạy TIÊU CHÍ 1"):
#             if not (hdv_files and ftp_files and tt_file):
#                 st.error("⚠ Vui lòng tải đầy đủ 3 loại file!")
#             else:
#                 try:
#                     # Các cột cần dùng
#                     cols_ckh = [
#                         'BRCD','DEPTCD','CUST_TYPE','NMLOC','CUSTSEQ','BIRTH_DAY','IDXACNO',
#                         'SCHM_NAME','TERM_DAYS','GL_SUB','CCYCD','CURBAL_NT','CURBAL_VN',
#                         'OPNDT_FIRST','OPNDT_EFFECT','MATDT','LS_GHISO','LS_CONG_BO',
#                         'PROMO_CD','KH_VIP','CIF_OPNDT','DP_MTHS','DP_DAYS','PROMO_NM','PHANKHUC_KH'
#                     ]

#                     df_ckh = pd.concat([pd.read_excel(f, dtype=str) for f in hdv_files], ignore_index=True)
#                     ensure_required_columns(df_ckh, cols_ckh)
#                     df_ckh = df_ckh[cols_ckh]

#                     cols_ftp = ['CUSTSEQ','NMLOC','IDXACNO','KY_HAN','LS_FTP']
#                     df_ftp = pd.concat([pd.read_excel(f, dtype=str) for f in ftp_files], ignore_index=True)
#                     ensure_required_columns(df_ftp, cols_ftp)
#                     df_ftp = df_ftp[cols_ftp]

#                     # Lọc đúng chi nhánh
#                     df_filtered = df_ckh[df_ckh['BRCD'].str.upper().str.contains(chi_nhanh_tc1)]

#                     df_tt_raw = pd.read_excel(tt_file, dtype=str)
#                     ensure_required_columns(
#                         df_tt_raw,
#                         [
#                             'Số tài khoản',
#                             'Lãi suất thực trả',
#                         ],
#                     )

#                     df_tt = df_tt_raw.rename(
#                         columns={'Số tài khoản':'IDXACNO','Lãi suất thực trả':'LS_THUC_TRA'}
#                     )

#                     df_merge = df_filtered.merge(
#                         df_ftp[['IDXACNO','LS_FTP']].drop_duplicates(),
#                         on="IDXACNO",
#                         how="left"
#                     )
#                     df_merge = df_merge.merge(df_tt, on="IDXACNO", how="left")

#                     df_merge["LS_GHISO"] = pd.to_numeric(df_merge["LS_GHISO"], errors="coerce")
#                     df_merge["LS_CONG_BO"] = pd.to_numeric(df_merge["LS_CONG_BO"], errors="coerce")
#                     df_merge["LS_THUC_TRA"] = pd.to_numeric(df_merge["LS_THUC_TRA"], errors="coerce")
#                     df_merge["LS_FTP"] = pd.to_numeric(df_merge["LS_FTP"], errors="coerce")

#                     df_merge["LSGS ≠ LSCB"] = (df_merge["LS_GHISO"] != df_merge["LS_CONG_BO"]).map({True:"X",False:""})
#                     df_merge["Không có LS trình duyệt"] = df_merge["LS_THUC_TRA"].isna().map({True:"X",False:""})

#                     df_merge["LSGS > FTP"] = (
#                         df_merge["LS_GHISO"] > df_merge["LS_FTP"]
#                     ).map({True:"X",False:""})

#                     st.success("✔ Tiêu chí 1 hoàn tất!")
#                     st.dataframe(df_merge, use_container_width=True)

#                     download_excel(df_merge, "TC1.xlsx")
#                 except UserFacingError as exc:
#                     render_error(str(exc))
#                 except Exception as exc:
#                     render_error(
#                         "Không thể xử lý Tiêu chí 1. Vui lòng kiểm tra định dạng và cột dữ liệu trong các file CKH/FTP/LS.",
#                         exc,
#                     )

#     # ================================================================
#     #                        TIÊU CHÍ 2
#     # ================================================================
#     with tab2:
#         st.subheader("📌 TIÊU CHÍ 2 – Xếp hạng KH theo số dư")

#         ckh_tc2 = st.file_uploader("📁 Tải file HDV CHI TIẾT CKH", type=['xls','xlsx'], accept_multiple_files=True)
#         kkh_tc2 = st.file_uploader("📁 Tải file HDV CHI TIẾT KKH", type=['xls','xlsx'], accept_multiple_files=True)

#         chi_nhanh_tc2 = st.text_input("🔍 Nhập mã SOL", "").upper().strip()

#         if st.button("🚀 Chạy TIÊU CHÍ 2"):
#             if not (ckh_tc2 and kkh_tc2):
#                 st.error("⚠ Vui lòng tải file CKH và KKH!")
#             else:
#                 try:
#                     cols = [
#                         'BRCD','DEPTCD','CUST_TYPE','CUSTSEQ','NMLOC','BIRTH_DAY','IDXACNO',
#                         'SCHM_NAME','TERM_DAYS','GL_SUB','CCYCD','CURBAL_NT','CURBAL_VN',
#                         'OPNDT_FIRST','OPNDT_EFFECT','MATDT','LS_GHISO','LS_CONG_BO','PROMO_CD',
#                         'KH_VIP','CIF_OPNDT'
#                     ]

#                     df_ckh2 = pd.concat([pd.read_excel(f, dtype=str) for f in ckh_tc2], ignore_index=True)
#                     df_kkh2 = pd.concat([pd.read_excel(f, dtype=str) for f in kkh_tc2], ignore_index=True)

#                     ensure_required_columns(df_ckh2, cols)
#                     ensure_required_columns(df_kkh2, cols)

#                     df_ckh2 = df_ckh2[cols]
#                     df_kkh2 = df_kkh2[cols]

#                     df_all = pd.concat([df_ckh2, df_kkh2], ignore_index=True)
#                     df_filtered = df_all[df_all["BRCD"].str.upper().str.contains(chi_nhanh_tc2)]

#                     df_filtered["CURBAL_VN"] = pd.to_numeric(df_filtered["CURBAL_VN"], errors='coerce')

#                     df_sum = df_filtered.groupby("CUSTSEQ", as_index=False)["CURBAL_VN"].sum().rename(columns={"CURBAL_VN":"SỐ DƯ"})
#                     df_tonghop = df_filtered.drop_duplicates("CUSTSEQ").merge(df_sum, on="CUSTSEQ", how="left")

#                     today = pd.Timestamp.today().normalize()
#                     df_tonghop["BIRTH_DAY"] = pd.to_datetime(df_tonghop["BIRTH_DAY"], errors='coerce')

#                     mask = df_tonghop["CUST_TYPE"]=="KHCN"
#                     df_tonghop.loc[mask,"ĐỘ TUỔI"] = df_tonghop.loc[mask,"BIRTH_DAY"].apply(
#                         lambda x: today.year - x.year - ((today.month, today.day) < (x.month, x.day)) if pd.notnull(x) else None
#                     )

#                     df_tonghop["RANK_RAW"] = df_tonghop.groupby("CUST_TYPE")["SỐ DƯ"].rank(method="min", ascending=False)

#                     for t in ["KHDN","KHCN"]:
#                         for n in [10,15,20]:
#                             df_tonghop[f"TOP{n}_{t}"] = df_tonghop.apply(
#                                 lambda x: "X" if x["CUST_TYPE"]==t and x["RANK_RAW"]<=n else "", axis=1
#                             )

#                     df_tonghop["RANK"] = df_tonghop["RANK_RAW"].apply(lambda x: int(x) if x<=20 else "")

#                     df_final = df_tonghop.rename(columns={
#                         "BRCD":"SOL","CUST_TYPE":"LOAI KH","CUSTSEQ":"CIF","NMLOC":"HO TEN",
#                         "BIRTH_DAY":"NGAY SINH/NGAY TL","KH_VIP":"KH VIP"
#                     })

#                     st.success("✔ Tiêu chí 2 hoàn tất!")
#                     st.dataframe(df_final, use_container_width=True)

#                     download_excel(df_final, "TC2.xlsx")
#                 except UserFacingError as exc:
#                     render_error(str(exc))
#                 except Exception as exc:
#                     render_error(
#                         "Không thể xử lý Tiêu chí 2. Vui lòng kiểm tra định dạng và cột dữ liệu trong file CKH/KKH.",
#                         exc,
#                     )

#     # ================================================================
#     #                        TIÊU CHÍ 3
#     # ================================================================
#     with tab3:
#     st.subheader("📌 TIÊU CHÍ 3 – Giao dịch tiền gửi rút")

#     tc3_file = st.file_uploader(
#         "📁 Tải file giao dịch (Mục 11)",
#         type=["xls", "xlsx"],
#         key="tc3_file_muc11",
#     )

#     chi_nhanh_tc3 = st.text_input(
#         "🔍 Nhập mã SOL",
#         value="",
#         key="tc3_sol_input",
#     ).upper().strip()

#     run_tc3 = st.button("🚀 Chạy TIÊU CHÍ 3", key="tc3_run_btn")

#     if run_tc3:
#         if not tc3_file:
#             st.error("⚠ Vui lòng tải file TC3!")
#         else:
#             try:
#                 df = pd.read_excel(tc3_file, dtype=str)

#                 ensure_required_columns(
#                     df,
#                     ["NGAY_HACH_TOAN", "ACCT_OPN_DATE", "PART_CLOSE_AMT", "SOL_ID"],
#                 )

#                 df["NGAY_HACH_TOAN"] = pd.to_datetime(df["NGAY_HACH_TOAN"], errors="coerce")
#                 df["ACCT_OPN_DATE"] = pd.to_datetime(df["ACCT_OPN_DATE"], errors="coerce")
#                 df["PART_CLOSE_AMT"] = pd.to_numeric(df["PART_CLOSE_AMT"], errors="coerce")

#                 # Lọc SOL (nếu user có nhập)
#                 if chi_nhanh_tc3:
#                     df = df[df["SOL_ID"].astype(str).str.upper().str.contains(chi_nhanh_tc3, na=False)]

#                 df["CHENH_LECH_NGAY"] = (df["NGAY_HACH_TOAN"] - df["ACCT_OPN_DATE"]).dt.days

#                 df["MO_RUT_CUNG_NGAY"] = df["CHENH_LECH_NGAY"].apply(lambda x: "X" if x == 0 else "")
#                 df["MO_RUT_1_3_NGAY"] = df["CHENH_LECH_NGAY"].apply(lambda x: "X" if 0 < x <= 3 else "")
#                 df["MO_RUT_4_7_NGAY"] = df["CHENH_LECH_NGAY"].apply(lambda x: "X" if 4 <= x <= 7 else "")
#                 df["GD_LON_HON_1TY"] = df["PART_CLOSE_AMT"].apply(lambda x: "X" if pd.notna(x) and x > 1_000_000_000 else "")

#                 today = pd.Timestamp.today().normalize()
#                 df["TRONG_THOI_HIEU_CAMERA"] = df["NGAY_HACH_TOAN"].apply(
#                     lambda x: "X" if pd.notna(x) and (today - x).days <= 90 else ""
#                 )

#                 st.success("✔ Tiêu chí 3 hoàn tất!")
#                 st.dataframe(df, use_container_width=True)

#                 download_excel(df, "TC3.xlsx")

#             except UserFacingError as exc:
#                 render_error(str(exc))
#             except Exception as exc:
#                 render_error(
#                     "Không thể xử lý Tiêu chí 3. Vui lòng kiểm tra định dạng file Mục 11 và các cột ngày/số tiền.",
#                     exc,
#                 )


#     # with tab3:
#     #     st.subheader("📌 TIÊU CHÍ 3 – Giao dịch tiền gửi rút")

#     #     tc3_file = st.file_uploader("📁 Tải file giao dịch (Mục 11)", type=['xls','xlsx'],key="tc3_file_muc11")
#     #     #chi_nhanh_tc3 = st.text_input("🔍 Nhập mã SOL", "").upper().strip()
#     #     chi_nhanh_tc3 = st.text_input("🔍 Nhập mã SOL", "").upper().strip()
#     #     if st.button("🚀 Chạy TIÊU CHÍ 3"):
#     #         if not tc3_file:
#     #             st.error("⚠ Vui lòng tải file TC3!")
#     #         else:
#     #             try:
#     #                 df = pd.read_excel(tc3_file, dtype=str)
#     #                 ensure_required_columns(
#     #                     df,
#     #                     [
#     #                         "NGAY_HACH_TOAN",
#     #                         "ACCT_OPN_DATE",
#     #                         "PART_CLOSE_AMT",
#     #                         "SOL_ID",
#     #                     ],
#     #                 )

#     #                 df["NGAY_HACH_TOAN"] = pd.to_datetime(df["NGAY_HACH_TOAN"], errors='coerce')
#     #                 df["ACCT_OPN_DATE"] = pd.to_datetime(df["ACCT_OPN_DATE"], errors='coerce')
#     #                 df["PART_CLOSE_AMT"] = pd.to_numeric(df["PART_CLOSE_AMT"], errors='coerce')

#     #                 df = df[df["SOL_ID"].str.upper().str.contains(chi_nhanh_tc3)]

#     #                 df["CHENH_LECH_NGAY"] = (df["NGAY_HACH_TOAN"] - df["ACCT_OPN_DATE"]).dt.days

#     #                 df["MO_RUT_CUNG_NGAY"] = df["CHENH_LECH_NGAY"].apply(lambda x: "X" if x==0 else "")
#     #                 df["MO_RUT_1_3_NGAY"] = df["CHENH_LECH_NGAY"].apply(lambda x: "X" if 0<x<=3 else "")
#     #                 df["MO_RUT_4_7_NGAY"] = df["CHENH_LECH_NGAY"].apply(lambda x: "X" if 4<=x<=7 else "")
#     #                 df["GD_LON_HON_1TY"] = df["PART_CLOSE_AMT"].apply(lambda x: "X" if x>1_000_000_000 else "")

#     #                 today = pd.Timestamp.today().normalize()
#     #                 df["TRONG_THOI_HIEU_CAMERA"] = df["NGAY_HACH_TOAN"].apply(lambda x: "X" if (today-x).days<=90 else "")

#     #                 st.success("✔ Tiêu chí 3 hoàn tất!")
#     #                 st.dataframe(df, use_container_width=True)

#     #                 download_excel(df, "TC3.xlsx")
#     #             except UserFacingError as exc:
#     #                 render_error(str(exc))
#     #             except Exception as exc:
#     #                 render_error(
#     #                     "Không thể xử lý Tiêu chí 3. Vui lòng kiểm tra định dạng file Mục 11 và các cột ngày/số tiền.",
#     #                     exc,
#     #                 )

