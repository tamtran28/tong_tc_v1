# module_the.py
import io
from datetime import datetime, date

import numpy as np
import pandas as pd
import streamlit as st

from module.error_utils import UserFacingError, _should_reraise


# =========================================================
# HÀM PHỤ – XUẤT EXCEL RA BYTES
# =========================================================
def df_to_excel_bytes(df: pd.DataFrame, sheet_name: str = "THE_1600"):
    """
    Xuất DataFrame ra Excel (1 sheet) để dùng cho st.download_button
    """
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    buffer.seek(0)
    return buffer


# =========================================================
# HÀM XỬ LÝ CHÍNH – THẺ (MỤC 1.3.2)
# =========================================================
def process_the(
    file_muc26,
    file_code_ttd_policy,
    files_du_no_m,
    files_du_no_m1,
    files_du_no_m2,
    files_crm4,
    files_ckh,
    file_muc17,
    chi_nhanh: str,
):
    """
    Nhận toàn bộ file upload liên quan THẺ, xử lý & trả về:
      - df_card: bảng kết quả thẻ (đủ các tiêu chí bạn đang dùng)
    """

    chi_nhanh_upper = chi_nhanh.strip().upper()

    # -------------------------------
    # MỤC 26 – DANH SÁCH THẺ
    # -------------------------------
    df_muc26 = pd.read_excel(file_muc26, dtype=str)

    cols_keep = [
        "CUSTSEQ",
        "BRCD",
        "PPSCRLMT",
        "FULLNM",
        "CUSTNAMNE",
        "ID_CARD",
        "IDCARD",
        "EXPDT",
        "NGAY_KICH_HOAT",
        "ODACCOUNT",
        "NGAY_MO",
        "TRANGTHAITHE",
        "POLICY_CODE",
        "POLICY_NAME",
        "DU_NO",
    ]
    cols_exist = [c for c in cols_keep if c in df_muc26.columns]
    df_processed = df_muc26[cols_exist].copy()

    # Chuẩn hóa kiểu dữ liệu cơ bản
    for c in ["CUSTSEQ", "IDCARD", "ID_CARD", "ODACCOUNT"]:
        if c in df_processed.columns:
            df_processed[c] = df_processed[c].astype("string")

    for c in ["NGAY_MO", "NGAY_KICH_HOAT", "EXPDT"]:
        if c in df_processed.columns:
            df_processed[c] = pd.to_datetime(df_processed[c], errors="coerce")

    # -------------------------------
    # CODE TÌNH TRẠNG THẺ & POLICY
    # -------------------------------
    df_code_tinh_trang_the = pd.read_excel(
        file_code_ttd_policy, sheet_name="Code Tình trạng thẻ"
    )
    df_code_policy = pd.read_excel(file_code_ttd_policy, sheet_name="Code Policy")

    # -------------------------------
    # EL – DƯ NỢ THẺ M, M-1, M-2
    # -------------------------------
    df_du_no_m = pd.concat(
        [pd.read_excel(f) for f in files_du_no_m], ignore_index=True
    )
    df_du_no_m1 = pd.concat(
        [pd.read_excel(f) for f in files_du_no_m1], ignore_index=True
    )
    df_du_no_m2 = pd.concat(
        [pd.read_excel(f) for f in files_du_no_m2], ignore_index=True
    )

    # -------------------------------
    # CRM4 & CKH & Mục 17 (chỉ dùng cho THẺ)
    # -------------------------------
    df_crm4 = pd.concat(
        [pd.read_excel(f, dtype=str) for f in files_crm4], ignore_index=True
    )
    df_hdv_ckh = pd.concat([pd.read_excel(f) for f in files_ckh], ignore_index=True)
    df_muc17 = pd.read_excel(file_muc17, dtype=str)

    # Lọc CRM4 & CKH theo chi nhánh
    df_crm4_loc = df_crm4[
        df_crm4["BRANCH_VAY"].astype(str).str.upper().str.contains(chi_nhanh_upper)
    ].copy()

    df_hdv_ckh_loc = df_hdv_ckh[
        df_hdv_ckh["BRCD"].astype(str).str.upper().str.contains(chi_nhanh_upper)
    ].copy()

    # ========================================================
    # (1) TÌNH TRẠNG THẺ
    # ========================================================
    if (
        "TRANGTHAITHE" in df_processed.columns
        and "Code" in df_code_tinh_trang_the.columns
        and "Tình trạng thẻ" in df_code_tinh_trang_the.columns
    ):
        df_code_tinh_trang_the["Code_policy"] = df_code_tinh_trang_the["Code"].astype(
            str
        )

        df_processed["TRANGTHAITHE_is_blank_orig"] = (
            df_processed["TRANGTHAITHE"].isna()
            | df_processed["TRANGTHAITHE"].astype(str).str.strip().eq("")
        )
        df_processed["TRANGTHAITHE_for_merge"] = df_processed["TRANGTHAITHE"].astype(
            str
        )

        df_processed = pd.merge(
            df_processed,
            df_code_tinh_trang_the[["Code_policy", "Tình trạng thẻ"]].rename(
                columns={"Tình trạng thẻ": "POLICY_TinhTrang"}
            ),
            left_on="TRANGTHAITHE_for_merge",
            right_on="Code_policy",
            how="left",
        )

        cond_a_blank = df_processed["TRANGTHAITHE_is_blank_orig"]
        cond_c_no_match = (~df_processed["TRANGTHAITHE_is_blank_orig"]) & (
            df_processed["Code_policy"].isna()
        )

        df_processed["TÌNH TRẠNG THẺ"] = np.select(
            [cond_a_blank, cond_c_no_match],
            ["Hoạt động bình thường", "Khác"],
            default=df_processed["POLICY_TinhTrang"],
        )

        cols_to_drop = [
            "Code_policy",
            "POLICY_TinhTrang",
            "TRANGTHAITHE_is_blank_orig",
            "TRANGTHAITHE_for_merge",
            "Description",
            "Unnamed: 3",
        ]
        df_processed.drop(
            columns=[c for c in cols_to_drop if c in df_processed.columns],
            inplace=True,
            errors="ignore",
        )
    else:
        df_processed["TÌNH TRẠNG THẺ"] = "Lỗi dữ liệu nguồn"

    # ========================================================
    # GỘP POLICY → PHÂN LOẠI CẤP HM THẺ
    # ========================================================
    df_processed["POLICY_CODE"] = df_processed["POLICY_CODE"].astype(str).str.strip()
    df_code_policy["CODE"] = df_code_policy["CODE"].astype(str).str.strip()

    df_processed = df_processed.merge(
        df_code_policy[["CODE", "PHÂN LOẠI ĐỐI TƯỢNG MỞ THẺ"]],
        left_on="POLICY_CODE",
        right_on="CODE",
        how="left",
    )

    df_processed["PHÂN LOẠI CẤP HM THẺ"] = df_processed[
        "PHÂN LOẠI ĐỐI TƯỢNG MỞ THẺ"
    ].fillna("Khác")

    # ========================================================
    # (3) DƯ NỢ THẺ 02 THÁNG TRƯỚC (M-2)
    # ========================================================
    if (
        "ODACCOUNT" in df_processed.columns
        and "OD_ACCOUNT" in df_du_no_m2.columns
        and "DU_NO_QUY_DOI" in df_du_no_m2.columns
    ):
        df_du_no_m2["OD_ACCOUNT"] = df_du_no_m2["OD_ACCOUNT"].astype(str)
        df_processed = pd.merge(
            df_processed,
            df_du_no_m2[["OD_ACCOUNT", "DU_NO_QUY_DOI"]],
            left_on="ODACCOUNT",
            right_on="OD_ACCOUNT",
            how="left",
        )
        df_processed.rename(
            columns={"DU_NO_QUY_DOI": "DƯ NỢ THẺ 02 THÁNG TRƯỚC"}, inplace=True
        )
        df_processed["DƯ NỢ THẺ 02 THÁNG TRƯỚC"].fillna("KPS", inplace=True)
        df_processed.drop(columns=["OD_ACCOUNT"], inplace=True, errors="ignore")
    else:
        df_processed["DƯ NỢ THẺ 02 THÁNG TRƯỚC"] = "KPS"

    # ========================================================
    # (4) DƯ NỢ THẺ 01 THÁNG TRƯỚC (M-1)
    # ========================================================
    if (
        "ODACCOUNT" in df_processed.columns
        and "OD_ACCOUNT" in df_du_no_m1.columns
        and "DU_NO_QUY_DOI" in df_du_no_m1.columns
    ):
        df_du_no_m1["OD_ACCOUNT"] = df_du_no_m1["OD_ACCOUNT"].astype(str)
        df_processed = pd.merge(
            df_processed,
            df_du_no_m1[["OD_ACCOUNT", "DU_NO_QUY_DOI"]],
            left_on="ODACCOUNT",
            right_on="OD_ACCOUNT",
            how="left",
        )
        df_processed.rename(
            columns={"DU_NO_QUY_DOI": "DƯ NỢ THẺ 01 THÁNG TRƯỚC"}, inplace=True
        )
        df_processed["DƯ NỢ THẺ 01 THÁNG TRƯỚC"].fillna("KPS", inplace=True)
        df_processed.drop(columns=["OD_ACCOUNT"], inplace=True, errors="ignore")
    else:
        df_processed["DƯ NỢ THẺ 01 THÁNG TRƯỚC"] = "KPS"

    # ========================================================
    # (5) DƯ NỢ THẺ HIỆN TẠI (M)
    # ========================================================
    if (
        "ODACCOUNT" in df_processed.columns
        and "OD_ACCOUNT" in df_du_no_m.columns
        and "DU_NO_QUY_DOI" in df_du_no_m.columns
    ):
        df_du_no_m["OD_ACCOUNT"] = df_du_no_m["OD_ACCOUNT"].astype(str)
        df_processed = pd.merge(
            df_processed,
            df_du_no_m[["OD_ACCOUNT", "DU_NO_QUY_DOI"]],
            left_on="ODACCOUNT",
            right_on="OD_ACCOUNT",
            how="left",
        )
        df_processed.rename(
            columns={"DU_NO_QUY_DOI": "DƯ NỢ THẺ HIỆN TẠI"}, inplace=True
        )
        df_processed["DƯ NỢ THẺ HIỆN TẠI"].fillna("KPS", inplace=True)
        df_processed.drop(columns=["OD_ACCOUNT"], inplace=True, errors="ignore")
    else:
        df_processed["DƯ NỢ THẺ HIỆN TẠI"] = "KPS"

    # ========================================================
    # (6) NHÓM NỢ HIỆN TẠI CỦA THẺ (NHOM_NO_OD_ACCOUNT)
    # ========================================================
    if (
        "ODACCOUNT" in df_processed.columns
        and "OD_ACCOUNT" in df_du_no_m.columns
        and "NHOM_NO_OD_ACCOUNT" in df_du_no_m.columns
    ):
        temp = df_du_no_m[["OD_ACCOUNT", "NHOM_NO_OD_ACCOUNT"]].copy()
        temp.rename(
            columns={"NHOM_NO_OD_ACCOUNT": "NHÓM NỢ HIỆN TẠI CỦA THẺ"}, inplace=True
        )
        temp["OD_ACCOUNT"] = temp["OD_ACCOUNT"].astype(str)

        df_processed = pd.merge(
            df_processed, temp, left_on="ODACCOUNT", right_on="OD_ACCOUNT", how="left"
        )
        df_processed["NHÓM NỢ HIỆN TẠI CỦA THẺ"].fillna("KPS", inplace=True)
        df_processed.drop(columns=["OD_ACCOUNT"], inplace=True, errors="ignore")
    else:
        df_processed["NHÓM NỢ HIỆN TẠI CỦA THẺ"] = "KPS"

    # ========================================================
    # (7) NHÓM NỢ HIỆN TẠI CỦA KH (NHOM_NO)
    # ========================================================
    if (
        "ODACCOUNT" in df_processed.columns
        and "OD_ACCOUNT" in df_du_no_m.columns
        and "NHOM_NO" in df_du_no_m.columns
    ):
        temp = df_du_no_m[["OD_ACCOUNT", "NHOM_NO"]].copy()
        temp.rename(columns={"NHOM_NO": "NHÓM NỢ HIỆN TẠI CỦA KH"}, inplace=True)
        temp["OD_ACCOUNT"] = temp["OD_ACCOUNT"].astype(str)

        df_processed = pd.merge(
            df_processed, temp, left_on="ODACCOUNT", right_on="OD_ACCOUNT", how="left"
        )
        df_processed["NHÓM NỢ HIỆN TẠI CỦA KH"].fillna("KPS", inplace=True)
        df_processed.drop(columns=["OD_ACCOUNT"], inplace=True, errors="ignore")
    else:
        df_processed["NHÓM NỢ HIỆN TẠI CỦA KH"] = "KPS"

    # ========================================================
    # (8) DƯ NỢ VAY CỦA KH (từ CRM4 – khoản Cho vay)
    # ========================================================
    if (
        "CUSTSEQ" in df_processed.columns
        and "CIF_KH_VAY" in df_crm4_loc.columns
        and "DU_NO_PHAN_BO_QUY_DOI" in df_crm4_loc.columns
        and "LOAI" in df_crm4_loc.columns
    ):
        df_crm4_loc["CIF_KH_VAY"] = df_crm4_loc["CIF_KH_VAY"].astype(str)
        df_crm4_cho_vay = df_crm4_loc[df_crm4_loc["LOAI"] == "Cho vay"].copy()

        df_crm4_cho_vay["DU_NO_PHAN_BO_QUY_DOI"] = pd.to_numeric(
            df_crm4_cho_vay["DU_NO_PHAN_BO_QUY_DOI"], errors="coerce"
        ).fillna(0)

        df_tong_du_no_vay_kh = (
            df_crm4_cho_vay.groupby("CIF_KH_VAY")["DU_NO_PHAN_BO_QUY_DOI"]
            .sum()
            .reset_index()
            .rename(columns={"DU_NO_PHAN_BO_QUY_DOI": "DƯ NỢ VAY CỦA KH"})
        )

        df_processed["CUSTSEQ"] = df_processed["CUSTSEQ"].astype(str)

        df_processed = pd.merge(
            df_processed,
            df_tong_du_no_vay_kh,
            left_on="CUSTSEQ",
            right_on="CIF_KH_VAY",
            how="left",
        )

        df_processed["DƯ NỢ VAY CỦA KH"].fillna("KPS", inplace=True)
        df_processed.drop(columns=["CIF_KH_VAY"], inplace=True, errors="ignore")
    else:
        df_processed["DƯ NỢ VAY CỦA KH"] = "KPS"

    # ========================================================
    # (9) SỐ LƯỢNG TSBĐ – MỤC 17
    # ========================================================
    if (
        "CUSTSEQ" in df_processed.columns
        and "C04" in df_muc17.columns
        and "C01" in df_muc17.columns
    ):
        df_muc17_copy = df_muc17.copy()
        df_muc17_copy["C04"] = df_muc17_copy["C04"].astype(str)
        df_processed["CUSTSEQ"] = df_processed["CUSTSEQ"].astype(str)

        df_so_luong_tsbd = (
            df_muc17_copy.groupby("C04")["C01"].nunique().reset_index()
        )
        df_so_luong_tsbd.rename(columns={"C01": "SỐ LƯỢNG TSBĐ"}, inplace=True)

        df_processed = pd.merge(
            df_processed, df_so_luong_tsbd, left_on="CUSTSEQ", right_on="C04", how="left"
        )

        df_processed["SỐ LƯỢNG TSBĐ"] = df_processed["SỐ LƯỢNG TSBĐ"].fillna("KPS")

        df_processed.drop(columns=["C04"], inplace=True, errors="ignore")
    else:
        df_processed["SỐ LƯỢNG TSBĐ"] = "KPS"

    # ========================================================
    # (10) TRỊ GIÁ TSBĐ – CRM4 (SECU_VALUE)
    # ========================================================
    if (
        "CUSTSEQ" in df_processed.columns
        and "CIF_KH_VAY" in df_crm4_loc.columns
        and "SECU_VALUE" in df_crm4_loc.columns
    ):
        df_crm4_loc_copy = df_crm4_loc.copy()
        df_crm4_loc_copy["CIF_KH_VAY"] = df_crm4_loc_copy["CIF_KH_VAY"].astype(str)
        df_crm4_loc_copy["SECU_VALUE"] = pd.to_numeric(
            df_crm4_loc_copy["SECU_VALUE"], errors="coerce"
        ).fillna(0)

        df_tri_gia_tsbd = (
            df_crm4_loc_copy.groupby("CIF_KH_VAY", as_index=False)["SECU_VALUE"]
            .sum()
            .rename(columns={"SECU_VALUE": "TRỊ GIÁ TSBĐ"})
        )

        df_processed = pd.merge(
            df_processed,
            df_tri_gia_tsbd,
            left_on="CUSTSEQ",
            right_on="CIF_KH_VAY",
            how="left",
        )

        df_processed["TRỊ GIÁ TSBĐ"] = df_processed["TRỊ GIÁ TSBĐ"].fillna("KPS")
        df_processed.drop(columns=["CIF_KH_VAY"], inplace=True, errors="ignore")
    else:
        df_processed["TRỊ GIÁ TSBĐ"] = "KPS"

    # ========================================================
    # (11) & (12) SỐ LƯỢNG / SỐ DƯ TKTG CKH
    # ========================================================
    df_processed["CUSTSEQ"] = df_processed["CUSTSEQ"].astype(str)
    df_hdv_ckh_loc["CUSTSEQ"] = df_hdv_ckh_loc["CUSTSEQ"].astype(str)

    # Số lượng TKTG CKH
    if "IDXACNO" in df_hdv_ckh_loc.columns:
        tktg_ckh_counts = (
            df_hdv_ckh_loc.groupby("CUSTSEQ")["IDXACNO"].count().reset_index()
        )
        tktg_ckh_counts.columns = ["CUSTSEQ", "SO_LUONG_TKTG_CKH"]

        df_processed = df_processed.merge(tktg_ckh_counts, on="CUSTSEQ", how="left")
        df_processed["SỐ LƯỢNG TKTG CKH"] = df_processed["SO_LUONG_TKTG_CKH"].fillna(
            "KPS"
        )
        df_processed.drop(columns=["SO_LUONG_TKTG_CKH"], inplace=True)
    else:
        df_processed["SỐ LƯỢNG TKTG CKH"] = "KPS"

    # Số dư TKTG CKH
    if "CURBAL_VN" in df_hdv_ckh_loc.columns:
        sodu_ckh = (
            df_hdv_ckh_loc.groupby("CUSTSEQ")["CURBAL_VN"].sum().reset_index()
        )
        sodu_ckh.columns = ["CUSTSEQ", "SỐ DƯ TÀI KHOẢN"]

        df_processed = df_processed.merge(sodu_ckh, on="CUSTSEQ", how="left")
        df_processed["SỐ DƯ TÀI KHOẢN"] = df_processed["SỐ DƯ TÀI KHOẢN"].fillna("KPS")
    else:
        df_processed["SỐ DƯ TÀI KHOẢN"] = "KPS"

    # ========================================================
    # (13) THẺ CÓ HẠN MỨC CAO (> 30 TRĐ)
    # ========================================================
    if "PPSCRLMT" in df_processed.columns:
        df_processed["PPSCRLMT_numeric"] = pd.to_numeric(
            df_processed["PPSCRLMT"], errors="coerce"
        )
        df_processed["THẺ CÓ HẠN MỨC CAO (> 30 TRĐ)"] = np.where(
            df_processed["PPSCRLMT_numeric"] > 30_000_000, "X", ""
        )
        df_processed.drop(columns=["PPSCRLMT_numeric"], inplace=True)
    else:
        df_processed["THẺ CÓ HẠN MỨC CAO (> 30 TRĐ)"] = ""

    # ========================================================
    # (14) & (15) TỈ LỆ DƯ NỢ / HẠN MỨC
    # ========================================================
    df_processed["DƯ NỢ THẺ HIỆN TẠI"] = pd.to_numeric(
        df_processed["DƯ NỢ THẺ HIỆN TẠI"], errors="coerce"
    )
    df_processed["PPSCRLMT"] = pd.to_numeric(
        df_processed["PPSCRLMT"], errors="coerce"
    )

    df_processed["THẺ TD CÓ TL DƯ NỢ/HM CAO (>= 90%)"] = np.where(
        (df_processed["PPSCRLMT"] > 0)
        & (df_processed["DƯ NỢ THẺ HIỆN TẠI"] / df_processed["PPSCRLMT"] >= 0.9),
        "X",
        "",
    )

    df_processed["THẺ TD CÓ DƯ NỢ > HM"] = np.where(
        (df_processed["PPSCRLMT"] > 0)
        & (df_processed["DƯ NỢ THẺ HIỆN TẠI"] / df_processed["PPSCRLMT"] > 1),
        "X",
        "",
    )

    # ========================================================
    # (16) THẺ CHƯA ĐÓNG
    # ========================================================
    df_processed["TÌNH TRẠNG THẺ"] = (
        df_processed["TÌNH TRẠNG THẺ"].astype(str).str.strip()
    )
    df_processed["THẺ CHƯA ĐÓNG"] = np.where(
        ~df_processed["TÌNH TRẠNG THẺ"].isin(["Chấm dứt sử dụng", "Yêu cầu đóng thẻ"]),
        "X",
        "",
    )

    # ========================================================
    # (17) THẺ MỞ THEO THU NHẬP/TÍN CHẤP CÓ HM CAO
    # ========================================================
    df_processed["PHÂN LOẠI ĐỐI TƯỢNG MỞ THẺ"] = df_processed[
        "PHÂN LOẠI ĐỐI TƯỢNG MỞ THẺ"
    ].astype(str).str.strip()
    df_processed["THẺ CÓ HẠN MỨC CAO (> 30 TRĐ)"] = df_processed[
        "THẺ CÓ HẠN MỨC CAO (> 30 TRĐ)"
    ].astype(str).str.strip()

    dk_17 = (
        df_processed["PHÂN LOẠI ĐỐI TƯỢNG MỞ THẺ"].isin(
            ["Theo thu nhập/tín chấp", "Theo điều kiện về TKTG CKH"]
        )
        & (df_processed["THẺ CÓ HẠN MỨC CAO (> 30 TRĐ)"] == "X")
    )

    df_processed["THẺ MỞ THEO THU NHẬP/TÍN CHẤP CÓ HM CAO"] = ""
    df_processed.loc[dk_17, "THẺ MỞ THEO THU NHẬP/TÍN CHẤP CÓ HM CAO"] = "X"

    # ========================================================
    # (18) KH KHÔNG CÓ/KHÔNG CÒN TSBĐ + biến thể
    # ========================================================
    df_processed["KH KHÔNG CÓ/KHÔNG CÒN TSBĐ"] = df_processed["SỐ LƯỢNG TSBĐ"].apply(
        lambda x: "X" if str(x).strip() in ["0", "KPS"] or x == 0 else ""
    )

    df_processed["KH GIẢI CHẤP TSBĐ NHƯNG THẺ CHƯA ĐÓNG"] = df_processed.apply(
        lambda row: "X"
        if (
            row["PHÂN LOẠI CẤP HM THẺ"] == "Theo khoản vay/Có TSBĐ"
            and row["KH KHÔNG CÓ/KHÔNG CÒN TSBĐ"] == "X"
            and row["THẺ CHƯA ĐÓNG"] == "X"
        )
        else "",
        axis=1,
    )

    # (20) KH GIẢI CHẤP TSBĐ NHƯNG THẺ CHƯA ĐÓNG VÀ CÓ DƯ NỢ
    df_processed["DƯ NỢ THẺ HIỆN TẠI"] = pd.to_numeric(
        df_processed["DƯ NỢ THẺ HIỆN TẠI"], errors="coerce"
    )

    dk_20 = (
        (df_processed["KH GIẢI CHẤP TSBĐ NHƯNG THẺ CHƯA ĐÓNG"] == "X")
        & (df_processed["DƯ NỢ THẺ HIỆN TẠI"].notnull())
        & (df_processed["DƯ NỢ THẺ HIỆN TẠI"] != 0)
    )

    df_processed[
        "KH GIẢI CHẤP TSBĐ NHƯNG THẺ CHƯA ĐÓNG VÀ CÓ DƯ NỢ"
    ] = ""
    df_processed.loc[
        dk_20, "KH GIẢI CHẤP TSBĐ NHƯNG THẺ CHƯA ĐÓNG VÀ CÓ DƯ NỢ"
    ] = "X"

    # ========================================================
    # (19) THẺ QUÁ HẠN / KH QUÁ HẠN
    # ========================================================
    df_processed["NHÓM NỢ HIỆN TẠI CỦA THẺ"] = pd.to_numeric(
        df_processed["NHÓM NỢ HIỆN TẠI CỦA THẺ"], errors="coerce"
    )
    df_processed["NHÓM NỢ HIỆN TẠI CỦA KH"] = pd.to_numeric(
        df_processed["NHÓM NỢ HIỆN TẠI CỦA KH"], errors="coerce"
    )

    df_processed["THẺ QUÁ HẠN"] = np.where(
        df_processed["NHÓM NỢ HIỆN TẠI CỦA THẺ"].isin([2, 3, 4, 5]), "X", ""
    )
    df_processed["KH QUÁ HẠN"] = np.where(
        df_processed["NHÓM NỢ HIỆN TẠI CỦA KH"].isin([2, 3, 4, 5]), "X", ""
    )

    # ========================================================
    # (21) KH KHÔNG CÓ/TẤT TOÁN TKTG CKH NHƯNG THẺ CHƯA ĐÓNG
    # ========================================================
    cond_a_21 = (
        df_processed["PHÂN LOẠI ĐỐI TƯỢNG MỞ THẺ"] == "Theo điều kiện về TKTG CKH"
    )
    cond_b_21 = df_processed["SỐ LƯỢNG TKTG CKH"].astype(str).isin(["0", "KPS"])
    cond_c_21 = df_processed["THẺ CHƯA ĐÓNG"] == "X"

    df_processed[
        "KH KHÔNG CÓ/TẤT TOÁN TKTG CKH NHƯNG THẺ CHƯA ĐÓNG"
    ] = np.where(
        cond_a_21 & cond_b_21 & cond_c_21,
        "X",
        "",
    )

    # ========================================================
    # (22) SỐ DƯ TKTG CKH < HẠN MỨC
    # ========================================================
    df_processed["PPSCRLMT"] = pd.to_numeric(df_processed["PPSCRLMT"], errors="coerce")
    df_processed["SỐ DƯ TÀI KHOẢN"] = pd.to_numeric(
        df_processed["SỐ DƯ TÀI KHOẢN"], errors="coerce"
    )

    df_processed["SỐ DƯ TKTG CKH < HẠN MỨC"] = df_processed.apply(
        lambda row: "X"
        if (
            row["PHÂN LOẠI ĐỐI TƯỢNG MỞ THẺ"] == "Theo điều kiện về TKTG CKH"
            and row["THẺ CHƯA ĐÓNG"] == "X"
            and (
                pd.isna(row["SỐ DƯ TÀI KHOẢN"])
                or row["SỐ DƯ TÀI KHOẢN"] < row["PPSCRLMT"]
            )
        )
        else "",
        axis=1,
    )

    return df_processed


# =========================================================
# HÀM PUBLIC – GỌI TỪ app.py
# =========================================================
def run_module_the():
    try:
        _run_module_the()
    except UserFacingError:
        raise
    except Exception as exc:
        if _should_reraise(exc):
            raise

        raise UserFacingError(
            "Đã xảy ra lỗi khi xử lý Tiêu chí thẻ. Vui lòng kiểm tra file đầu vào."
        ) from exc


def _run_module_the():

    st.markdown(
        """
Ứng dụng này xử lý **toàn bộ tiêu chí THẺ (1.3.2)**, dùng các nguồn:
- Mục 26 – Danh sách thẻ  
- EL dư nợ M, M-1, M-2  
- CRM4 – Dư nợ & TSBĐ  
- HDV_CHITIET_CKH – TKTG CKH  
- Mục 17 – TSTC  
- Code TTD-NEW (Code Tình trạng thẻ + Code Policy)
"""
    )

    # =========================
    # THAM SỐ CHUNG
    # =========================
    col_param1, col_param2 = st.columns(2)

    with col_param1:
        chi_nhanh = st.text_input(
            "Nhập tên chi nhánh hoặc mã SOL (VD: HANOI, 007)",
            value="",
        ).strip()

    with col_param2:
        st.caption("Tiêu chí thẻ không phụ thuộc trực tiếp ngày kiểm toán, bạn có thể bỏ qua.")

    st.markdown("---")

    # =========================
    # NHÓM UPLOAD – THẺ
    # =========================
    st.subheader("💳 Upload nhóm file THẺ")

    st.markdown("**Vui lòng upload đầy đủ các file sau (chấp nhận cả .xls và .xlsx):**")

    col_t1, col_t2 = st.columns(2)

    with col_t1:
        file_muc26 = st.file_uploader(
            "1️⃣ Mục 26 – Danh sách thẻ",
            type=["xls", "xlsx"],
            key="muc26",
        )

        file_code_ttd_policy = st.file_uploader(
            "2️⃣ Code TTD-NEW (chứa cả sheet 'Code Tình trạng thẻ' và 'Code Policy')",
            type=["xls", "xlsx"],
            key="code_ttd",
        )

        files_du_no_m = st.file_uploader(
            "3️⃣ Dư nợ THẺ tháng M (OD_ACCOUNT, DU_NO_QUY_DOI, NHOM_NO, NHOM_NO_OD_ACCOUNT)",
            type=["xls", "xlsx"],
            accept_multiple_files=True,
            key="el_m",
        )

        files_du_no_m1 = st.file_uploader(
            "4️⃣ Dư nợ THẺ tháng M-1",
            type=["xls", "xlsx"],
            accept_multiple_files=True,
            key="el_m1",
        )

        files_du_no_m2 = st.file_uploader(
            "5️⃣ Dư nợ THẺ tháng M-2",
            type=["xls", "xlsx"],
            accept_multiple_files=True,
            key="el_m2",
        )

    with col_t2:
        files_crm4 = st.file_uploader(
            "6️⃣ CRM4_Du_no_theo_tai_san_dam_bao_ALL (có thể nhiều file)",
            type=["xls", "xlsx"],
            accept_multiple_files=True,
            key="crm4",
        )

        files_ckh = st.file_uploader(
            "7️⃣ HDV_CHITIET_CKH_* (chi tiết TKTG CKH – nhiều file)",
            type=["xls", "xlsx"],
            accept_multiple_files=True,
            key="ckh",
        )

        file_muc17 = st.file_uploader(
            "8️⃣ Mục 17 – TSTC (Muc17_Lop2_TSTC...)",
            type=["xls", "xlsx"],
            key="muc17",
        )

    st.markdown("---")

    # =========================
    # NÚT CHẠY & XỬ LÝ
    # =========================
    run_button = st.button("🚀 Chạy xử lý TIÊU CHÍ THẺ")

    if run_button:
        missing = []

        if not chi_nhanh:
            missing.append("Chi nhánh")

        if file_muc26 is None:
            missing.append("Mục 26")
        if file_code_ttd_policy is None:
            missing.append("Code TTD-NEW")
        if not files_du_no_m:
            missing.append("Dư nợ tháng M")
        if not files_du_no_m1:
            missing.append("Dư nợ tháng M-1")
        if not files_du_no_m2:
            missing.append("Dư nợ tháng M-2")
        if not files_crm4:
            missing.append("CRM4")
        if not files_ckh:
            missing.append("HDV_CHITIET_CKH")
        if file_muc17 is None:
            missing.append("Mục 17")

        if missing:
            st.error("❌ Thiếu dữ liệu: " + ", ".join(missing))
            return

        with st.spinner("⏳ Đang xử lý dữ liệu THẺ..."):
            df_card = process_the(
                file_muc26=file_muc26,
                file_code_ttd_policy=file_code_ttd_policy,
                files_du_no_m=files_du_no_m,
                files_du_no_m1=files_du_no_m1,
                files_du_no_m2=files_du_no_m2,
                files_crm4=files_crm4,
                files_ckh=files_ckh,
                file_muc17=file_muc17,
                chi_nhanh=chi_nhanh,
            )
            st.session_state["df_card"] = df_card

        st.success("✅ Đã xử lý xong! Xem kết quả & tải Excel bên dưới.")

    # =========================
    # HIỂN THỊ & DOWNLOAD
    # =========================
    tab1, tab2 = st.tabs(
        [
            "💳 Kết quả Thẻ (1.3.2)",
            "⬇️ Tải file Excel",
        ]
    )

    with tab1:
        st.subheader("💳 Bảng kết quả THẺ – Mục 1.3.2")
        if "df_card" in st.session_state:
            df_card = st.session_state["df_card"]
            st.write(f"Số dòng: **{len(df_card)}**")
            st.dataframe(df_card.head(100), use_container_width=True)

            with st.expander("📑 Xem danh sách cột"):
                st.write(list(df_card.columns))
        else:
            st.info("Chưa có dữ liệu. Hãy upload file & bấm **Chạy xử lý TIÊU CHÍ THẺ**.")

    with tab2:
        st.subheader("⬇️ Tải file Excel kết quả")
        if "df_card" in st.session_state:
            df_card = st.session_state["df_card"]
            excel_bytes = df_to_excel_bytes(df_card, sheet_name="THE_1600")

            st.download_button(
                label="📥 Tải file **KQ_Tieu_chi_the.xlsx**",
                data=excel_bytes,
                file_name="KQ_Tieu_chi_the.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            st.info("Chưa có dữ liệu để tải. Hãy chạy xử lý trước.")
