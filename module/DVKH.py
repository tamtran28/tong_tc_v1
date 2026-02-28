# module/DVKH.py
"""
Module DVKH cho Streamlit
Bao gồm:
- Tab A: Tiêu chí 1-3 (Ủy quyền + SMS + SCM010)
- Tab B: Tiêu chí 4 (HDV KKH + chargelevel + nhân sự) và Tiêu chí 5 (Mapping/1405)

Tính năng:
- Hỗ trợ upload đơn file Excel hoặc ZIP (với nhiều Excel bên trong) cho CKH/KKH, SMS zip chứa .txt.
- Audit log vào dvkh_audit.csv (append).
- Xuất Excel nhiều sheet (ví dụ: Tieu_chi_4 + Tieu_chi_5).
"""

import streamlit as st
import pandas as pd
import numpy as np
import io
import re
import zipfile
import os
from datetime import datetime
from typing import List, Optional, Tuple

from module.error_utils import UserFacingError, _should_reraise

# Cố gắng lấy user hiện tại từ hệ thống auth (nếu project của bạn có)
try:
    from db.auth_jwt import get_current_user
except Exception:
    def get_current_user():
        return {"username": "unknown", "full_name": "unknown", "role": "unknown"}


# ---------------------------
# Cấu hình & Audit
# ---------------------------
AUDIT_FILE = "dvkh_audit.csv"


def audit_log(action: str, note: str = "", user: Optional[dict] = None):
    """Ghi log hoạt động (append CSV)."""
    ts = datetime.now().isoformat(sep=" ", timespec="seconds")
    if user is None:
        user = get_current_user() if callable(get_current_user) else {"username": "unknown"}
    username = user.get("username", "unknown") if isinstance(user, dict) else str(user)
    row = {"timestamp": ts, "username": username, "action": action, "note": note}
    df_row = pd.DataFrame([row])
    header = not os.path.exists(AUDIT_FILE)
    df_row.to_csv(AUDIT_FILE, mode="a", header=header, index=False, encoding="utf-8-sig")


# ---------------------------
# Utilities đọc/ghi
# ---------------------------
@st.cache_data(show_spinner=False)
def read_excel_file_bytesio(uploaded_file) -> pd.DataFrame:
    """Đọc file Excel từ UploadedFile / BytesIO; trả DataFrame dtype=str"""
    # streamlit uploaded_file has .read() but pandas accepts file-like; pass-through
    try:
        return pd.read_excel(uploaded_file, dtype=str)
    except Exception as e:
        # thử read bằng io.BytesIO nếu uploaded_file là UploadedFile và đã được .read() trước
        try:
            raw = uploaded_file.read()
            return pd.read_excel(io.BytesIO(raw), dtype=str)
        except Exception:
            raise


@st.cache_data(show_spinner=False)
def read_text_file_bytesio(uploaded_file, sep: str = "\t") -> pd.DataFrame:
    """Đọc file text (tab-separated) từ UploadedFile / BytesIO"""
    try:
        return pd.read_csv(uploaded_file, sep=sep, dtype=str, on_bad_lines="skip")
    except Exception:
        try:
            raw = uploaded_file.read()
            return pd.read_csv(io.BytesIO(raw), sep=sep, dtype=str, on_bad_lines="skip")
        except Exception:
            raise


def safe_to_datetime(series):
    return pd.to_datetime(series, errors="coerce")


def to_excel_bytes(dfs: dict) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, df in dfs.items():
            sheet = name[:31]
            df.to_excel(writer, sheet_name=sheet, index=False)
    output.seek(0)
    return output.getvalue()


def ensure_columns(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df


# ---------------------------
# ZIP helpers
# ---------------------------
def extract_excel_from_zip_bytes(zip_uploaded) -> List[Tuple[str, io.BytesIO]]:
    """
    Trả về list các tuple (filename, BytesIO) của file xls/xlsx trong zip_uploaded.
    zip_uploaded: streamlit UploadedFile hoặc BytesIO
    """
    try:
        raw = zip_uploaded.read() if hasattr(zip_uploaded, "read") else zip_uploaded
        z = zipfile.ZipFile(io.BytesIO(raw))
        res = []
        for name in z.namelist():
            if name.lower().endswith((".xls", ".xlsx")):
                res.append((name, io.BytesIO(z.read(name))))
        return res
    except Exception:
        return []


def extract_text_from_zip_bytes(zip_uploaded) -> Tuple[Optional[io.BytesIO], Optional[str]]:
    """
    Trả về (BytesIO, filename) của file .txt đầu tiên trong zip.
    """
    try:
        raw = zip_uploaded.read() if hasattr(zip_uploaded, "read") else zip_uploaded
        z = zipfile.ZipFile(io.BytesIO(raw))
        for name in z.namelist():
            if name.lower().endswith(".txt"):
                return io.BytesIO(z.read(name)), name
        return None, None
    except Exception:
        return None, None


# ---------------------------
# XỬ LÝ TIÊU CHÍ 1-3 (Ủy quyền + SMS + SCM010)
# ---------------------------
def process_uyquyen_sms_scm(
    uploaded_ckh_files: List,
    uploaded_kkh_files: List,
    uploaded_muc30_file,
    uploaded_sms_txt_file,
    uploaded_scm10_xlsx_file,
    filter_chi_nhanh: Optional[str] = None
):
    """
    Trả về (merged, df_tc3)
    - merged: bảng Uy quyền gốc + các cột bổ sung
    - df_tc3: bảng final dùng để hiển thị cho tiêu chí 3 (có cột '1 người nhận UQ của nhiều người')
    uploaded_sms_txt_file có thể là: UploadedFile (.txt), BytesIO (nội dung txt), hoặc tên file-like
    uploaded_ckh_files / uploaded_kkh_files: list of UploadedFile OR list of BytesIO
    """
    # --- 1. Ghép CKH + KKH ---
    df_b_CKH = pd.DataFrame()
    df_b_KKH = pd.DataFrame()
    if uploaded_ckh_files:
        frames = []
        for f in uploaded_ckh_files:
            # f may be UploadedFile or (name, BytesIO)
            try:
                frames.append(read_excel_file_bytesio(f))
            except Exception:
                # nếu f là tuple (name, BytesIO)
                if isinstance(f, tuple) and hasattr(f[1], "read"):
                    frames.append(read_excel_file_bytesio(f[1]))
                else:
                    raise
        if frames:
            df_b_CKH = pd.concat(frames, ignore_index=True)

    if uploaded_kkh_files:
        frames = []
        for f in uploaded_kkh_files:
            try:
                frames.append(read_excel_file_bytesio(f))
            except Exception:
                if isinstance(f, tuple) and hasattr(f[1], "read"):
                    frames.append(read_excel_file_bytesio(f[1]))
                else:
                    raise
        if frames:
            df_b_KKH = pd.concat(frames, ignore_index=True)

    # df_b combine
    if not df_b_CKH.empty and not df_b_KKH.empty:
        df_b = pd.concat([df_b_CKH, df_b_KKH], ignore_index=True)
    elif not df_b_CKH.empty:
        df_b = df_b_CKH.copy()
    elif not df_b_KKH.empty:
        df_b = df_b_KKH.copy()
    else:
        df_b = pd.DataFrame()

    # --- 2. Đọc MUC30 (df_a) ---
    df_a = read_excel_file_bytesio(uploaded_muc30_file)

    # lọc DESCRIPTION chứa chu ky
    df_a = df_a[df_a.get("DESCRIPTION", "").astype(str).str.contains(r"chu\s*ky|chuky|cky", case=False, na=False)].copy()

    # parse ngày an toàn
    df_a["EXPIRYDATE_dt"] = safe_to_datetime(df_a.get("EXPIRYDATE", pd.Series(dtype=str)))
    df_a["EFFECTIVEDATE_dt"] = safe_to_datetime(df_a.get("EFFECTIVEDATE", pd.Series(dtype=str)))
    df_a["EXPIRYDATE_str"] = df_a["EXPIRYDATE_dt"].dt.strftime("%m/%d/%Y")
    df_a["EFFECTIVEDATE_str"] = df_a["EFFECTIVEDATE_dt"].dt.strftime("%m/%d/%Y")

    # loại doanh nghiệp
    keywords = ["CONG TY", "CTY", "CONGTY", "CÔNG TY", "CÔNGTY"]
    df_a = df_a[~df_a.get("NGUOI_UY_QUYEN", "").astype(str).str.upper().str.contains("|".join(keywords), na=False)].copy()

    # tách NGUOI_DUOC_UY_QUYEN
    def extract_name(value):
        parts = re.split(r"[-,]", str(value))
        for part in parts:
            name = part.strip()
            if re.fullmatch(r"[A-Z ]{3,}", name):
                return name
        return value

    if "NGUOI_DUOC_UY_QUYEN" in df_a.columns:
        df_a["NGUOI_DUOC_UY_QUYEN"] = df_a["NGUOI_DUOC_UY_QUYEN"].apply(extract_name)
    else:
        df_a["NGUOI_DUOC_UY_QUYEN"] = ""

    # drop duplicates
    dedup_cols = [c for c in ["PRIMARY_SOL_ID", "TK_DUOC_UY_QUYEN", "NGUOI_DUOC_UY_QUYEN"] if c in df_a.columns]
    if dedup_cols:
        df_a = df_a.drop_duplicates(subset=dedup_cols, keep="first")

    # --- 3. Merge TK_DUOC_UY_QUYEN vs df_b IDXACNO -> get CUSTSEQ (CIF) ---
    if not df_b.empty and "IDXACNO" in df_b.columns and "TK_DUOC_UY_QUYEN" in df_a.columns:
        df_a["TK_DUOC_UY_QUYEN"] = df_a["TK_DUOC_UY_QUYEN"].astype(str)
        df_b["IDXACNO"] = df_b["IDXACNO"].astype(str)
        merged = df_a.merge(df_b[["IDXACNO", "CUSTSEQ"]], left_on="TK_DUOC_UY_QUYEN", right_on="IDXACNO", how="left")
    else:
        merged = df_a.copy()
        merged["CUSTSEQ"] = np.nan

    # CIF người ủy quyền => string (or 'NA')
    def norm_custseq(x):
        try:
            if pd.isna(x):
                return "NA"
            sx = str(x).strip()
            if sx == "" or sx.lower() == "nan":
                return "NA"
            # convert floats like '123.0' -> '123'
            if re.match(r"^\d+(\.0+)?$", sx):
                return str(int(float(sx)))
            return sx
        except:
            return "NA"

    merged["CIF_NGUOI_UY_QUYEN"] = merged.get("CUSTSEQ", pd.Series(dtype=str)).apply(norm_custseq)

    # Bổ sung CIF nếu cùng NGUOI_UY_QUYEN
    cif_updated = merged["CIF_NGUOI_UY_QUYEN"].copy()
    if "NGUOI_UY_QUYEN" in merged.columns:
        for nguoi, group in merged.groupby("NGUOI_UY_QUYEN"):
            if len(group) >= 2:
                vals = group["CIF_NGUOI_UY_QUYEN"].unique().tolist()
                actuals = [v for v in vals if v != "NA"]
                if actuals:
                    fill = actuals[0]
                    idxs = group[group["CIF_NGUOI_UY_QUYEN"] == "NA"].index
                    cif_updated.loc[idxs] = fill
    merged["CIF_NGUOI_UY_QUYEN"] = cif_updated

    # remove helper cols if exist
    for c in ["IDXACNO", "CUSTSEQ"]:
        if c in merged.columns:
            merged.drop(columns=[c], inplace=True, errors="ignore")

    # classify account type using CKH/KKH sets
    set_ckh = set(df_b_CKH["CUSTSEQ"].astype(str).dropna()) if not df_b_CKH.empty and "CUSTSEQ" in df_b_CKH.columns else set()
    set_kkh = set(df_b_KKH["IDXACNO"].astype(str).dropna()) if not df_b_KKH.empty and "IDXACNO" in df_b_KKH.columns else set()

    def phan_loai_tk(tk):
        s = str(tk)
        if s in set_ckh:
            return "CKH"
        if s in set_kkh:
            return "KKH"
        return "NA"

    merged["LOAI_TK"] = merged.get("TK_DUOC_UY_QUYEN", pd.Series(dtype=str)).astype(str).apply(phan_loai_tk)

    # time calculations
    merged["EXPIRYDATE_dt"] = safe_to_datetime(merged.get("EXPIRYDATE_str") if "EXPIRYDATE_str" in merged.columns else merged.get("EXPIRYDATE"))
    merged["EFFECTIVEDATE_dt"] = safe_to_datetime(merged.get("EFFECTIVEDATE_str") if "EFFECTIVEDATE_str" in merged.columns else merged.get("EFFECTIVEDATE"))
    merged["YEAR_DIFF"] = merged["EXPIRYDATE_dt"].dt.year - merged["EFFECTIVEDATE_dt"].dt.year
    merged["KHONG_NHAP_TGIAN_UQ"] = ""
    merged.loc[merged["YEAR_DIFF"].fillna(-1) == 99, "KHONG_NHAP_TGIAN_UQ"] = "X"
    merged["UQ_TREN_50_NAM"] = ""
    merged.loc[merged["YEAR_DIFF"].fillna(-1) >= 50, "UQ_TREN_50_NAM"] = "X"
    merged.drop(columns=["EXPIRYDATE_dt", "EFFECTIVEDATE_dt", "YEAR_DIFF"], inplace=True, errors="ignore")

    # --- 4. SMS + SCM010 ---
    # uploaded_sms_txt_file may be BytesIO or UploadedFile or BytesIO from zip
    if uploaded_sms_txt_file is None:
        df_sms_raw = pd.DataFrame()
    else:
        # If uploaded_sms_txt_file is BytesIO -> pass through read_text_file_bytesio
        if isinstance(uploaded_sms_txt_file, io.BytesIO):
            df_sms_raw = read_text_file_bytesio(uploaded_sms_txt_file)
        else:
            # if it's UploadedFile or other
            try:
                df_sms_raw = read_text_file_bytesio(uploaded_sms_txt_file)
            except Exception:
                # try reading bytes then parse
                try:
                    raw = uploaded_sms_txt_file.read()
                    df_sms_raw = read_text_file_bytesio(io.BytesIO(raw))
                except Exception:
                    df_sms_raw = pd.DataFrame()

    df_sms = df_sms_raw.copy() if not df_sms_raw.empty else pd.DataFrame()
    # normalize columns used
    for col in ["FORACID", "ORGKEY", "C_MOBILE_NO", "CRE_DATE", "CUSTTPCD"]:
        if col in df_sms.columns:
            df_sms[col] = df_sms[col].astype(str)

    if "CRE_DATE" in df_sms.columns:
        df_sms["CRE_DATE_parsed"] = safe_to_datetime(df_sms["CRE_DATE"])
        df_sms["CRE_DATE_str"] = df_sms["CRE_DATE_parsed"].dt.strftime("%m/%d/%Y")

    # filter by FORACID numeric and KHDN
    if "FORACID" in df_sms.columns:
        df_sms = df_sms[df_sms["FORACID"].str.match(r"^\d+$", na=False)]
    if "CUSTTPCD" in df_sms.columns:
        df_sms = df_sms[df_sms["CUSTTPCD"].astype(str).str.upper() != "KHDN"]

    # SCM010
    df_scm10 = pd.DataFrame()
    try:
        df_scm10 = read_excel_file_bytesio(uploaded_scm10_xlsx_file)
        df_scm10 = df_scm10.rename(columns=lambda x: x.strip())
    except Exception:
        df_scm10 = pd.DataFrame()

    if "CIF_ID" in df_scm10.columns:
        df_scm10["CIF_ID"] = df_scm10["CIF_ID"].astype(str)

    # combine
    if not df_sms.empty:
        df_sms["PL DICH VU"] = "SMS"
    if not df_scm10.empty:
        df_scm10["ORGKEY"] = df_scm10.get("CIF_ID", pd.Series(dtype=str))
        df_scm10["PL DICH VU"] = "SCM010"

    if not df_sms.empty and not df_scm10.empty:
        df_merged_sms_scm10 = pd.concat([df_sms, df_scm10[["ORGKEY", "PL DICH VU"]].drop_duplicates()], ignore_index=True, axis=0)
    elif not df_sms.empty:
        df_merged_sms_scm10 = df_sms.copy()
    elif not df_scm10.empty:
        df_merged_sms_scm10 = df_scm10.copy()
    else:
        df_merged_sms_scm10 = pd.DataFrame()

    df_sms_only = df_merged_sms_scm10[df_merged_sms_scm10.get("PL DICH VU", "") == "SMS"] if not df_merged_sms_scm10.empty else pd.DataFrame()
    tk_sms_set = set(df_sms_only["FORACID"].astype(str).dropna()) if not df_sms_only.empty and "FORACID" in df_sms_only.columns else set()

    df_scm10_only = df_merged_sms_scm10[df_merged_sms_scm10.get("PL DICH VU", "") == "SCM010"] if not df_merged_sms_scm10.empty else pd.DataFrame()
    cif_scm10_set = set(df_scm10_only["ORGKEY"].astype(str).dropna()) if not df_scm10_only.empty and "ORGKEY" in df_scm10_only.columns else set()

    merged["TK có đăng ký SMS"] = merged.get("TK_DUOC_UY_QUYEN", pd.Series(dtype=str)).astype(str).apply(lambda x: "X" if str(x) in tk_sms_set else "")
    merged["CIF có đăng ký SCM010"] = merged.get("CIF_NGUOI_UY_QUYEN", pd.Series(dtype=str)).astype(str).apply(lambda x: "X" if str(x) in cif_scm10_set else "")

    # --- 5. 1 người nhận nhiều UQ (tiêu chí 3) ---
    df_tc3 = merged.copy()
    if "NGUOI_DUOC_UY_QUYEN" in df_tc3.columns and "NGUOI_UY_QUYEN" in df_tc3.columns:
        grouped = df_tc3.groupby("NGUOI_DUOC_UY_QUYEN")["NGUOI_UY_QUYEN"].nunique().reset_index()
        grouped = grouped[grouped["NGUOI_UY_QUYEN"] >= 2]
        nguoi_nhan_nhieu_uq = set(grouped["NGUOI_DUOC_UY_QUYEN"].astype(str).dropna())
        df_tc3["1 người nhận UQ của nhiều người"] = df_tc3["NGUOI_DUOC_UY_QUYEN"].astype(str).apply(lambda x: "X" if x in nguoi_nhan_nhieu_uq else "")
    else:
        df_tc3["1 người nhận UQ của nhiều người"] = ""

    return merged, df_tc3


def process_tieuchi_4_5(
    files_42a_upload: List,
    file_42b_upload,
    file_42c_upload,
    file_42d_upload,
    file_mapping_upload,
    chi_nhanh: str
):
    """
    Trả về:
        df_42a_final, df_mapping_final

    files_42a_upload: list[UploadedFile | (name, BytesIO)]
    """

    # =====================================================
    # 1) GHÉP + LỌC TIÊU CHÍ 4.2.a
    # =====================================================
    frames = []
    for f in files_42a_upload:
        try:
            frames.append(read_excel_file_bytesio(f))
        except Exception:
            if isinstance(f, tuple) and hasattr(f[1], "read"):
                frames.append(read_excel_file_bytesio(f[1]))
            else:
                raise

    if not frames:
        return pd.DataFrame(), pd.DataFrame()

    df_42a = pd.concat(frames, ignore_index=True)

    if "BRCD" in df_42a.columns and chi_nhanh:
        df_42a = df_42a[
            df_42a["BRCD"].astype(str).str.upper().str.contains(chi_nhanh)
        ]

    cols_42a = [
        "BRCD", "DEPTCD", "CUST_TYPE", "CUSTSEQ", "NMLOC", "BIRTH_DAY",
        "IDXACNO", "SCHM_NAME", "CCYCD", "CURBAL_VN",
        "OPNDT_FIRST", "OPNDT_EFFECT"
    ]
    df_42a = ensure_columns(df_42a, cols_42a)[cols_42a]

    # Chỉ giữ KHCN
    df_42a = df_42a[
        df_42a["CUST_TYPE"].astype(str).str.upper() == "KHCN"
    ]

    # Loại TK không hợp lệ
    exclude_keywords = ["KY QUY", "GIAI NGAN", "CHI LUONG", "TKTT THE", "TRUNG GIAN"]
    df_42a = df_42a[
        ~df_42a["SCHM_NAME"]
        .astype(str)
        .str.upper()
        .str.contains("|".join(exclude_keywords), na=False)
    ]

    # =====================================================
    # 2) TIÊU CHÍ 4.2.b – CHARGE LEVEL
    # =====================================================
    df_42b = read_excel_file_bytesio(file_42b_upload)
    df_42b = ensure_columns(
        df_42b,
        ["MACIF", "STKKH", "CHARGELEVELCODE_CIF", "CHARGELEVELCODE_TK"]
    )

    df_42a["CUSTSEQ"] = df_42a["CUSTSEQ"].astype(str)
    df_42a["IDXACNO"] = df_42a["IDXACNO"].astype(str)
    df_42b["MACIF"] = df_42b["MACIF"].astype(str)
    df_42b["STKKH"] = df_42b["STKKH"].astype(str)

    # Merge theo CIF
    df_42a = df_42a.merge(
        df_42b.drop_duplicates("MACIF")[["MACIF", "CHARGELEVELCODE_CIF"]],
        left_on="CUSTSEQ",
        right_on="MACIF",
        how="left"
    )
    df_42a.rename(
        columns={"CHARGELEVELCODE_CIF": "CHARGELEVELCODE_CUA_CIF"},
        inplace=True
    )
    df_42a.drop(columns="MACIF", inplace=True, errors="ignore")

    # Merge theo TK
    df_42a = df_42a.merge(
        df_42b.drop_duplicates("STKKH")[["STKKH", "CHARGELEVELCODE_TK"]],
        left_on="IDXACNO",
        right_on="STKKH",
        how="left"
    )
    df_42a.rename(
        columns={"CHARGELEVELCODE_TK": "CHARGELEVELCODE_CUA_TK"},
        inplace=True
    )
    df_42a.drop(columns="STKKH", inplace=True, errors="ignore")

    df_42a["TK_GAN_CODE_UU_DAI_CBNV"] = np.where(
        df_42a["CHARGELEVELCODE_CUA_TK"] == "NVEIB", "X", ""
    )

    # =====================================================
    # 3) TIÊU CHÍ 4.2.c – DANH SÁCH NHÂN SỰ
    # 👉 GIỮ CỘT "Mã số CIF"
    # =====================================================
    df_42c = read_excel_file_bytesio(file_42c_upload)
    df_42c = ensure_columns(df_42c, ["Mã số CIF", "Mã NV"])

    df_42a = df_42a.merge(
        df_42c[["Mã số CIF", "Mã NV"]],
        left_on="CUSTSEQ",
        right_on="Mã số CIF",
        how="left"
    )
    # KHÔNG DROP "Mã số CIF"

    # =====================================================
    # 4) TIÊU CHÍ 4.2.d – NHÂN SỰ NGHỈ VIỆC
    # =====================================================
    df_42d = read_excel_file_bytesio(file_42d_upload)
    df_42d = ensure_columns(df_42d, ["CIF", "Ngày thôi việc"])

    df_42a = df_42a.merge(
        df_42d[["CIF", "Ngày thôi việc"]],
        left_on="CUSTSEQ",
        right_on="CIF",
        how="left"
    )

    df_42a["CBNV_NGHI_VIEC"] = np.where(df_42a["CIF"].notna(), "X", "")
    df_42a.rename(
        columns={"Ngày thôi việc": "NGAY_NGHI_VIEC"},
        inplace=True
    )
    df_42a["NGAY_NGHI_VIEC"] = (
        safe_to_datetime(df_42a["NGAY_NGHI_VIEC"])
        .dt.strftime("%m/%d/%Y")
    )
    df_42a.drop(columns="CIF", inplace=True, errors="ignore")

    # =====================================================
    # 5) TIÊU CHÍ 5 – MAPPING THẺ
    # =====================================================
    df_map = read_excel_file_bytesio(file_mapping_upload)
    df_map.columns = df_map.columns.str.lower()

    need_cols = [
        "brcd", "semaacount", "cardnbr", "token", "relation", "uploaddt",
        "odaccount", "acctcd", "dracctno", "drratio", "adduser", "updtuser",
        "expiredate", "custnm", "cif", "xpcode", "xpcodedt", "remark", "oldxpcode"
    ]
    df_map = ensure_columns(df_map, need_cols)[need_cols]

    df_map["uploaddt"] = safe_to_datetime(df_map["uploaddt"])
    df_map["xpcodedt"] = safe_to_datetime(df_map["xpcodedt"])

    df_map["SO_NGAY_MO_THE"] = (
        df_map["xpcodedt"] - df_map["uploaddt"]
    ).dt.days

    df_map["MO_DONG_TRONG_6_THANG"] = df_map.apply(
        lambda r: "X"
        if pd.notnull(r["SO_NGAY_MO_THE"])
           and 0 <= r["SO_NGAY_MO_THE"] < 180
           and r["uploaddt"] > pd.to_datetime("2025-06-30")
        else "",
        axis=1
    )

    df_map["xpcodedt"] = df_map["xpcodedt"].dt.strftime("%m/%d/%Y")
    df_map["uploaddt"] = df_map["uploaddt"].dt.strftime("%m/%d/%Y")

    return df_42a, df_map

# ---------------------------
# STREAMLIT UI PUBLIC FUNCTION
# ---------------------------
def run_dvkh_5_tieuchi():
    try:
        _run_dvkh_5_tieuchi()
    except UserFacingError:
        raise
    except Exception as exc:
        if _should_reraise(exc):
            raise

        raise UserFacingError(
            "Đã xảy ra lỗi khi xử lý DVKH. Vui lòng kiểm tra các tệp CKH/KKH, SMS và cấu hình đầu vào."
        ) from exc


def _run_dvkh_5_tieuchi():
    #st.title("👥 DVKH — 5 tiêu chí (Ủy quyền, SMS/SCM, HDV, Mapping)")

    user = get_current_user() or {"username": "unknown"}

    tab1, tab2 = st.tabs(["Tiêu chí 1-3 (Ủy quyền + SMS/SCM)", "Tiêu chí 4-5 (42a & Mapping)"])

    with tab1:
        st.header("A. Tiêu chí 1-3: Ủy quyền + SMS + SCM010")
        st.info("Upload: CKH (nhiều), KKH (nhiều), MUC30, ZIP chứa Muc14_DKSMS.txt, SCM010.xlsx")

        uploaded_ckh_zip = st.file_uploader("HDV_CHITIET_CKH.zip (nhiều file Excel bên trong) - (hoặc upload list Excel)", type=["zip","xls","xlsx"], accept_multiple_files=False, key="dvkh_ckh_zip")
        uploaded_kkh_zip = st.file_uploader("HDV_CHITIET_KKH.zip (nhiều file Excel bên trong) - (hoặc upload list Excel)", type=["zip","xls","xlsx"], accept_multiple_files=False, key="dvkh_kkh_zip")

        # Hỗ trợ both: nếu user upload zip thì extract; nếu upload multiple excel (older UI) thì có thể thay đổi
        uploaded_ckh_files = []
        uploaded_kkh_files = []

        # nếu upload zip cho CKH
        if uploaded_ckh_zip and uploaded_ckh_zip.type == "application/x-zip-compressed" or (uploaded_ckh_zip and uploaded_ckh_zip.name.lower().endswith(".zip")):
            ckh_list = extract_excel_from_zip_bytes(uploaded_ckh_zip)
            uploaded_ckh_files = [ (name, buf) for name, buf in ckh_list ]
        else:
            # nếu user chọn một excel file (không zip), hỗ trợ upload nhiều bằng interface khác -> try to use as single Excel
            if uploaded_ckh_zip and uploaded_ckh_zip.name.lower().endswith((".xls", ".xlsx")):
                uploaded_ckh_files = [uploaded_ckh_zip]

        if uploaded_kkh_zip and uploaded_kkh_zip.type == "application/x-zip-compressed" or (uploaded_kkh_zip and uploaded_kkh_zip.name.lower().endswith(".zip")):
            kkh_list = extract_excel_from_zip_bytes(uploaded_kkh_zip)
            uploaded_kkh_files = [ (name, buf) for name, buf in kkh_list ]
        else:
            if uploaded_kkh_zip and uploaded_kkh_zip.name.lower().endswith((".xls", ".xlsx")):
                uploaded_kkh_files = [uploaded_kkh_zip]

        uploaded_muc30_file = st.file_uploader("MUC 30 (Muc30) - single", type=["xls","xlsx"], key="dvkh_muc30")
        uploaded_sms_zip = st.file_uploader("Muc14_DKSMS.zip (bên trong chứa 1 file .txt)", type=["zip"], key="dvkh_sms_zip")
        uploaded_scm10_xlsx_file = st.file_uploader("Muc14_SCM010.xlsx", type=["xls","xlsx"], key="dvkh_scm10")

        if st.button("Chạy Tiêu chí 1-3"):
            # validate
            if not uploaded_muc30_file or not uploaded_scm10_xlsx_file or not uploaded_sms_zip or (not uploaded_ckh_files) or (not uploaded_kkh_files):
                st.error("Vui lòng upload đủ: CKH (zip hoặc excel), KKH (zip hoặc excel), MUC30, ZIP chứa Muc14_DKSMS.txt, Muc14_SCM010.xlsx")
                audit_log("run_tieuchi_1_3_failed", "missing files", user)
            else:
                # giải nén SMS txt
                sms_io, sms_name = extract_text_from_zip_bytes(uploaded_sms_zip)
                if sms_io is None:
                    st.error("Không tìm thấy file .txt trong ZIP SMS. Vui lòng kiểm tra ZIP.")
                    audit_log("run_tieuchi_1_3_failed", "sms txt not found in zip", user)
                else:
                    try:
                        audit_log("run_tieuchi_1_3_start", f"CKH_files:{len(uploaded_ckh_files)} KKH_files:{len(uploaded_kkh_files)}", user)
                        merged, df_tc3 = process_uyquyen_sms_scm(
                            uploaded_ckh_files,
                            uploaded_kkh_files,
                            uploaded_muc30_file,
                            sms_io,
                            uploaded_scm10_xlsx_file
                        )
                        st.success("Xử lý xong Tiêu chí 1-3")
                        st.subheader("Preview Tiêu chí 3")
                        st.dataframe(df_tc3.head(200), use_container_width=True)

                        out_bytes = to_excel_bytes({
                            "UyQuyen": merged,
                            "UyQuyen_TC3": df_tc3
                        })
                        st.download_button("📥 Tải Excel Tiêu chí 1-3", data=out_bytes, file_name="DVKH_TC1_3.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                        audit_log("run_tieuchi_1_3_success", f"rows:{len(df_tc3)}", user)
                    except Exception as e:
                        st.error("Đã xảy ra lỗi trong quá trình xử lý Tiêu chí 1-3.")
                        st.exception(e)
                        audit_log("run_tieuchi_1_3_error", str(e), user)

    # TAB 2
    with tab2:
        st.header("B. Tiêu chí 4 & 5 (42a / Mapping)")
        st.info("Upload: HDV_CHITIET_KKH (nhiều file .xls/.xlsx), BC_LAY_CHARGELEVELCODE..., 10_Danh sach nhan su..., DS nghi viec..., Mapping_sol.xlsx")
        files_42a_upload = st.file_uploader("HDV_CHITIET_KKH_*.xls (multiple) OR upload zip containing many Excel", type=["zip","xls","xlsx"], accept_multiple_files=False, key="dvkh_tab2_42a")
        file_42b_upload = st.file_uploader("BC_LAY_CHARGELEVELCODE_THEO_KHCN (excel)", type=["xls","xlsx"], key="dvkh_tab2_42b")
        file_42c_upload = st.file_uploader("10_Danh sach nhan su_T*.xlsx", type=["xls","xlsx"], key="dvkh_tab2_42c")
        file_42d_upload = st.file_uploader("2.Danh_sach_nghi_viec.xlsx", type=["xls","xlsx"], key="dvkh_tab2_42d")
        file_mapping_upload = st.file_uploader("Mapping_sol.xlsx", type=["xls","xlsx"], key="dvkh_tab2_map")
        chi_nhanh = st.text_input("Nhập mã SOL để lọc (VD: 1405)").strip().upper()

        if st.button("Chạy Tiêu chí 4-5"):
            if not (files_42a_upload and file_42b_upload and file_42c_upload and file_42d_upload and file_mapping_upload and chi_nhanh):
                st.error("Vui lòng tải đủ các file và nhập chi_nhanh để chạy Tiêu chí 4-5.")
                audit_log("run_tieuchi_4_5_failed", "missing inputs", user)
            else:
                try:
                    # Nếu files_42a_upload là zip -> extract
                    files_42a_list = []
                    if files_42a_upload.name.lower().endswith(".zip"):
                        ex = extract_excel_from_zip_bytes(files_42a_upload)
                        files_42a_list = [(name, buf) for name, buf in ex]
                    else:
                        # nếu là 1 excel: dùng trực tiếp
                        files_42a_list = [files_42a_upload]

                    audit_log("run_tieuchi_4_5_start", f"chi_nhanh={chi_nhanh} files_42a={len(files_42a_list)}", user)
                    df_42a_final, df_mapping_final = process_tieuchi_4_5(
                        files_42a_upload=files_42a_list,
                        file_42b_upload=file_42b_upload,
                        file_42c_upload=file_42c_upload,
                        file_42d_upload=file_42d_upload,
                        file_mapping_upload=file_mapping_upload,
                        chi_nhanh=chi_nhanh
                    )

                    st.success("Xử lý xong Tiêu chí 4-5")
                    st.subheader("Preview Tiêu chí 4 (42a)")
                    st.dataframe(df_42a_final.head(200), use_container_width=True)
                    st.subheader("Preview Tiêu chí 5 (Mapping)")
                    st.dataframe(df_mapping_final.head(200), use_container_width=True)

                    out_bytes = to_excel_bytes({
                        "Tieu_chi_4": df_42a_final,
                        "Tieu_chi_5": df_mapping_final
                    })
                    st.download_button("📥 Tải Excel Tiêu chí 4-5", data=out_bytes, file_name="DVKH_TC4_5.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                    audit_log("run_tieuchi_4_5_success", f"rows4:{len(df_42a_final)} rows5:{len(df_mapping_final)}", user)
                except Exception as e:
                    st.error("Đã xảy ra lỗi trong quá trình xử lý Tiêu chí 4-5.")
                    st.exception(e)
                    audit_log("run_tieuchi_4_5_error", str(e), user)

    # # Audit viewer
    # st.markdown("---")
    # st.header("Audit & Logs")
    # st.write("Nhật ký hoạt động DVKH (local file):")
    # if os.path.exists(AUDIT_FILE):
    #     try:
    #         df_audit = pd.read_csv(AUDIT_FILE)
    #         st.dataframe(df_audit.sort_values("timestamp", ascending=False).head(200))
    #         csv_bytes = df_audit.to_csv(index=False).encode("utf-8-sig")
    #         st.download_button("Tải Log Audit (CSV)", data=csv_bytes, file_name="dvkh_audit.csv", mime="text/csv")
    #     except Exception as e:
    #         st.error("Không thể đọc file audit.")
    #         st.exception(e)
    # else:
    #     st.info("Chưa có log hoạt động (file dvkh_audit.csv chưa tồn tại).")

    # st.markdown("---")
    # st.info("Module DVKH — hoàn tất. Liên hệ admin khi cần thêm rule / cột bổ sung.")
    # =========================

    # AUDIT VIEWER (ADMIN ONLY)
    # =========================
    
    if st.session_state.get("role") == "admin":
    
        st.markdown("---")
        st.header("🔐 Audit & Logs (Admin)")
    
        st.write("Nhật ký hoạt động DVKH (local file):")
    
        if os.path.exists(AUDIT_FILE):
            try:
                df_audit = pd.read_csv(AUDIT_FILE)
                st.dataframe(
                    df_audit.sort_values("timestamp", ascending=False).head(200),
                    use_container_width=True,
                )
    
                csv_bytes = df_audit.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "📥 Tải Log Audit (CSV)",
                    data=csv_bytes,
                    file_name="dvkh_audit.csv",
                    mime="text/csv",
                )
            except Exception as e:
                st.error("❌ Không thể đọc file audit.")
                st.exception(e)
        else:
            st.info("ℹ️ Chưa có log hoạt động (file dvkh_audit.csv chưa tồn tại).")
    
    else:
        # Ẩn hoàn toàn, hoặc chỉ hiển thị thông báo nhẹ
        st.caption("🔒 Audit & Logs chỉ dành cho Admin.")


# # module/DVKH.py
# """
# Module DVKH cho Streamlit
# Bao gồm: 2 tab
# - Tab A: Tiêu chí 1,2,3 (Ủy quyền + SMS + SCM010)
# - Tab B: Tiêu chí 4 (HDV KKH + chargelevel + nhân sự) và Tiêu chí 5 (Mapping/1405)
# Ghi audit vào CSV dvkh_audit.csv trong working dir (không thay DB).
# """

# import streamlit as st
# import pandas as pd
# import numpy as np
# import io
# import re
# import glob
# import zipfile
# import os
# from datetime import datetime
# from typing import List, Optional

# # Cố gắng lấy user hiện tại từ hệ thống auth (nếu project của bạn có)
# try:
#     from db.auth_jwt import get_current_user
# except Exception:
#     def get_current_user():
#         return {"username": "unknown", "full_name": "unknown", "role": "unknown"}


# # ---------------------------
# # Utilities
# # ---------------------------
# AUDIT_FILE = "dvkh_audit.csv"

# def audit_log(action: str, note: str = "", user: Optional[dict] = None):
#     """Ghi log hoạt động (append CSV)."""
#     ts = datetime.now().isoformat(sep=" ", timespec="seconds")
#     if user is None:
#         user = get_current_user() if callable(get_current_user) else {"username": "unknown"}
#     username = user.get("username", "unknown") if isinstance(user, dict) else str(user)
#     row = {"timestamp": ts, "username": username, "action": action, "note": note}
#     df_row = pd.DataFrame([row])
#     header = not os.path.exists(AUDIT_FILE)
#     df_row.to_csv(AUDIT_FILE, mode="a", header=header, index=False, encoding="utf-8-sig")


# @st.cache_data(show_spinner=False)
# def read_excel_file_bytesio(uploaded_file) -> pd.DataFrame:
#     """Đọc file uploaded (pandas) với dtype=str an toàn."""
#     return pd.read_excel(uploaded_file, dtype=str)


# @st.cache_data(show_spinner=False)
# def read_text_file_bytesio(uploaded_file, sep='\t') -> pd.DataFrame:
#     return pd.read_csv(uploaded_file, sep=sep, dtype=str, on_bad_lines='skip')


# def safe_to_datetime(series, fmt=None):
#     if fmt:
#         return pd.to_datetime(series, format=fmt, errors='coerce')
#     return pd.to_datetime(series, errors='coerce')


# def to_excel_bytes(dfs: dict) -> bytes:
#     """Trả về bytes của Excel (multi-sheet)."""
#     output = io.BytesIO()
#     with pd.ExcelWriter(output, engine="openpyxl") as writer:
#         for name, df in dfs.items():
#             # truncate sheet name to 31 chars
#             sheet = name[:31]
#             df.to_excel(writer, sheet_name=sheet, index=False)
#     output.seek(0)
#     return output.getvalue()


# # ---------------------------
# # XỬ LÝ TIÊU CHÍ 1-3 (Ủy quyền + SMS + SCM010)
# # ---------------------------
# def process_uyquyen_sms_scm(
#     uploaded_ckh_files: List,
#     uploaded_kkh_files: List,
#     uploaded_muc30_file,
#     uploaded_sms_txt_file,
#     uploaded_scm10_xlsx_file,
#     filter_chi_nhanh: Optional[str] = None
# ):
#     """Trả về df_uyquyen, df_tc3 (final display for tab1)."""
#     # 1. ghép CKH + KKH
#     df_b_CKH = pd.concat([read_excel_file_bytesio(f) for f in uploaded_ckh_files], ignore_index=True) if uploaded_ckh_files else pd.DataFrame()
#     df_b_KKH = pd.concat([read_excel_file_bytesio(f) for f in uploaded_kkh_files], ignore_index=True) if uploaded_kkh_files else pd.DataFrame()
#     df_b = pd.concat([df_b_CKH, df_b_KKH], ignore_index=True) if not df_b_CKH.empty or not df_b_KKH.empty else pd.DataFrame()

#     # 2. đọc MUC30 (df_a)
#     df_a = read_excel_file_bytesio(uploaded_muc30_file)

#     # filter DESCRIPTION chứa chu ky
#     df_a = df_a[df_a["DESCRIPTION"].str.contains(r"chu\s*ky|chuky|cky", case=False, na=False)].copy()

#     # chuyển ngày
#     # một số file cung cấp YYYYMMDD, một số đã ở dạng khác -> dùng coerce
#     df_a["EXPIRYDATE"] = safe_to_datetime(df_a.get("EXPIRYDATE", pd.Series(dtype=str)))
#     df_a["EFFECTIVEDATE"] = safe_to_datetime(df_a.get("EFFECTIVEDATE", pd.Series(dtype=str)))
#     # format mm/dd/YYYY để nhất quán
#     df_a["EXPIRYDATE_str"] = df_a["EXPIRYDATE"].dt.strftime("%m/%d/%Y")
#     df_a["EFFECTIVEDATE_str"] = df_a["EFFECTIVEDATE"].dt.strftime("%m/%d/%Y")

#     # filter loại doanh nghiệp
#     keywords = ["CONG TY", "CTY", "CONGTY", "CÔNG TY", "CÔNGTY"]
#     df_a = df_a[~df_a["NGUOI_UY_QUYEN"].astype(str).str.upper().str.contains("|".join(keywords), na=False)].copy()

#     # extract name
#     def extract_name(value):
#         parts = re.split(r'[-,]', str(value))
#         for part in parts:
#             name = part.strip()
#             if re.fullmatch(r'[A-Z ]{3,}', name):
#                 return name
#         return value

#     df_a["NGUOI_DUOC_UY_QUYEN"] = df_a["NGUOI_DUOC_UY_QUYEN"].apply(extract_name)
#     df_a = df_a.drop_duplicates(subset=["PRIMARY_SOL_ID", "TK_DUOC_UY_QUYEN", "NGUOI_DUOC_UY_QUYEN"], keep='first')

#     # 3. merge TK_DUOC_UY_QUYEN vs df_b IDXACNO -> get CUSTSEQ (CIF)
#     if not df_b.empty and "IDXACNO" in df_b.columns:
#         df_a["TK_DUOC_UY_QUYEN"] = df_a["TK_DUOC_UY_QUYEN"].astype(str)
#         df_b["IDXACNO"] = df_b["IDXACNO"].astype(str)
#         merged = df_a.merge(df_b[["IDXACNO", "CUSTSEQ"]], left_on="TK_DUOC_UY_QUYEN", right_on="IDXACNO", how="left")
#     else:
#         merged = df_a.copy()
#         merged["CUSTSEQ"] = np.nan

#     # CIF người ủy quyền
#     merged["CIF_NGUOI_UY_QUYEN"] = merged["CUSTSEQ"].apply(lambda x: str(int(float(x))) if pd.notna(x) and str(x).strip() != "" and str(x) != "nan" else "NA")

#     # bổ sung CIF nếu cùng NGUOI_UY_QUYEN
#     cif_nguoi_uy_quyen_updated = merged["CIF_NGUOI_UY_QUYEN"].copy()
#     for nguoi_uq, group in merged.groupby("NGUOI_UY_QUYEN"):
#         if len(group) >= 2:
#             cif_values = group["CIF_NGUOI_UY_QUYEN"]
#             has_na = "NA" in cif_values.unique()
#             actual_cifs = [c for c in cif_values.unique() if c != "NA"]
#             if has_na and actual_cifs:
#                 cif_to_fill = actual_cifs[0]
#                 indices_to_update = group[group["CIF_NGUOI_UY_QUYEN"] == "NA"].index
#                 cif_nguoi_uy_quyen_updated.loc[indices_to_update] = cif_to_fill
#     merged["CIF_NGUOI_UY_QUYEN"] = cif_nguoi_uy_quyen_updated

#     # remove helper columns if exist
#     for drop_col in ["IDXACNO", "CUSTSEQ"]:
#         if drop_col in merged.columns:
#             merged.drop(columns=[drop_col], inplace=True, errors='ignore')

#     # classify account type using CKH/KKH sets
#     set_ckh = set(df_b_CKH["CUSTSEQ"].astype(str).dropna()) if not df_b.empty and 'CUSTSEQ' in df_b_CKH.columns else set()
#     set_kkh = set(df_b_KKH["IDXACNO"].astype(str).dropna()) if not df_b.empty and 'IDXACNO' in df_b_KKH.columns else set()
#     def phan_loai_tk(tk):
#         if str(tk) in set_ckh:
#             return "CKH"
#         if str(tk) in set_kkh:
#             return "KKH"
#         return "NA"
#     merged["LOAI_TK"] = merged["TK_DUOC_UY_QUYEN"].astype(str).apply(phan_loai_tk)

#     # time calculations
#     merged["EXPIRYDATE_dt"] = safe_to_datetime(merged.get("EXPIRYDATE_str") if "EXPIRYDATE_str" in merged.columns else merged.get("EXPIRYDATE"))
#     merged["EFFECTIVEDATE_dt"] = safe_to_datetime(merged.get("EFFECTIVEDATE_str") if "EFFECTIVEDATE_str" in merged.columns else merged.get("EFFECTIVEDATE"))
#     merged["YEAR_DIFF"] = merged["EXPIRYDATE_dt"].dt.year - merged["EFFECTIVEDATE_dt"].dt.year
#     merged["KHONG_NHAP_TGIAN_UQ"] = ""
#     merged.loc[merged["YEAR_DIFF"].fillna(-1) == 99, "KHONG_NHAP_TGIAN_UQ"] = "X"
#     merged["UQ_TREN_50_NAM"] = ""
#     merged.loc[merged["YEAR_DIFF"].fillna(-1) >= 50, "UQ_TREN_50_NAM"] = "X"
#     merged.drop(columns=["EXPIRYDATE_dt", "EFFECTIVEDATE_dt", "YEAR_DIFF"], inplace=True, errors='ignore')

#     # 4. SMS + SCM010 processing
#     df_sms_raw = read_text_file_bytesio(uploaded_sms_txt_file)  # expects tab separated
#     df_sms = df_sms_raw.copy()
#     for col in ["FORACID", "ORGKEY", "C_MOBILE_NO"]:
#         if col in df_sms.columns:
#             df_sms[col] = df_sms[col].astype(str)
#     # normalize date
#     if "CRE_DATE" in df_sms.columns:
#         df_sms["CRE_DATE_parsed"] = safe_to_datetime(df_sms["CRE_DATE"])
#         df_sms["CRE_DATE_str"] = df_sms["CRE_DATE_parsed"].dt.strftime("%m/%d/%Y")
#     # filter
#     if "FORACID" in df_sms.columns:
#         df_sms = df_sms[df_sms["FORACID"].str.match(r'^\d+$', na=False)]
#     if "CUSTTPCD" in df_sms.columns:
#         df_sms = df_sms[df_sms["CUSTTPCD"].str.upper() != "KHDN"]

#     df_scm10 = read_excel_file_bytesio(uploaded_scm10_xlsx_file)
#     df_scm10 = df_scm10.rename(columns=lambda x: x.strip())
#     if "CIF_ID" in df_scm10.columns:
#         df_scm10["CIF_ID"] = df_scm10["CIF_ID"].astype(str)
#     df_sms["PL DICH VU"] = "SMS"
#     df_scm10["ORGKEY"] = df_scm10.get("CIF_ID", pd.Series(dtype=str))
#     df_scm10["PL DICH VU"] = "SCM010"
#     df_merged_sms_scm10 = pd.concat([df_sms, df_scm10[["ORGKEY", "PL DICH VU"]].drop_duplicates()], ignore_index=True, axis=0)

#     # mark accounts registered for SMS and CIF registered for SCM010
#     df_sms_only = df_merged_sms_scm10[df_merged_sms_scm10["PL DICH VU"] == "SMS"] if "PL DICH VU" in df_merged_sms_scm10.columns else pd.DataFrame()
#     tk_sms_set = set(df_sms_only["FORACID"].astype(str).dropna()) if not df_sms_only.empty else set()
#     df_scm10_only = df_merged_sms_scm10[df_merged_sms_scm10["PL DICH VU"] == "SCM010"] if "PL DICH VU" in df_merged_sms_scm10.columns else pd.DataFrame()
#     cif_scm10_set = set(df_scm10_only["ORGKEY"].astype(str).dropna()) if not df_scm10_only.empty else set()

#     merged["TK có đăng ký SMS"] = merged["TK_DUOC_UY_QUYEN"].astype(str).apply(lambda x: "X" if str(x) in tk_sms_set else "")
#     merged["CIF có đăng ký SCM010"] = merged["CIF_NGUOI_UY_QUYEN"].astype(str).apply(lambda x: "X" if str(x) in cif_scm10_set else "")

#     # 5. 1 người nhận nhiều UQ
#     df_tc3 = merged.copy()
#     grouped = df_tc3.groupby("NGUOI_DUOC_UY_QUYEN")["NGUOI_UY_QUYEN"].nunique().reset_index()
#     grouped = grouped[grouped["NGUOI_UY_QUYEN"] >= 2]
#     nguoi_nhan_nhieu_uq = set(grouped["NGUOI_DUOC_UY_QUYEN"].astype(str).dropna())
#     df_tc3["1 người nhận UQ của nhiều người"] = df_tc3["NGUOI_DUOC_UY_QUYEN"].astype(str).apply(lambda x: "X" if x in nguoi_nhan_nhieu_uq else "")

#     return merged, df_tc3


# # ---------------------------
# # # XỬ LÝ TIÊU CHÍ 4-5 (42a, mapping)



#     def safe_to_datetime(series):
#         """Chuyển đổi ngày an toàn, không báo lỗi."""
#         return pd.to_datetime(series, errors="coerce")
    
    
#     def ensure_columns(df, columns):
#         """Tự thêm các cột còn thiếu (fill='')"""
#         for c in columns:
#             if c not in df.columns:
#                 df[c] = ""
#         return df
    
    
#     def process_tieuchi_4_5(
#         files_42a_upload: List,
#         file_42b_upload,
#         file_42c_upload,
#         file_42d_upload,
#         file_mapping_upload,
#         chi_nhanh: str
#     ):
    
#         # ============================================================
#         # 1) GHÉP 42A – KHÁCH HÀNG
#         # ============================================================
#         df_42a = pd.concat(
#             [read_excel_file_bytesio(f) for f in files_42a_upload],
#             ignore_index=True
#         ) if files_42a_upload else pd.DataFrame()
    
#         if df_42a.empty:
#             return pd.DataFrame(), pd.DataFrame()
    
#         df_42a = df_42a[df_42a["BRCD"].astype(str).str.upper().str.contains(chi_nhanh)]
    
#         cols_42a = [
#             "BRCD", "DEPTCD", "CUST_TYPE", "CUSTSEQ", "NMLOC", "BIRTH_DAY",
#             "IDXACNO", "SCHM_NAME", "CCYCD", "CURBAL_VN",
#             "OPNDT_FIRST", "OPNDT_EFFECT"
#         ]
#         df_42a = ensure_columns(df_42a, cols_42a)
#         df_42a = df_42a[cols_42a]
    
#         # Keep KHCN
#         df_42a = df_42a[df_42a["CUST_TYPE"].astype(str).str.upper() == "KHCN"]
    
#         # Loại SCHM_NAME
#         exclude_keywords = ["KY QUY", "GIAI NGAN", "CHI LUONG", "TKTT THE", "TRUNG GIAN"]
#         df_42a = df_42a[
#             ~df_42a["SCHM_NAME"].astype(str).str.upper().str.contains("|".join(exclude_keywords), na=False)
#         ]
    
    
#         # ============================================================
#         # 2) GHÉP 42B – CHARGELEVEL (MACIF + TK)
#         # ============================================================
#         df_42b = read_excel_file_bytesio(file_42b_upload)
#         df_42b = ensure_columns(df_42b, ["MACIF", "STKKH", "CHARGELEVELCODE_CIF", "CHARGELEVELCODE_TK"])
    
#         df_42a["CUSTSEQ"] = df_42a["CUSTSEQ"].astype(str)
#         df_42b["MACIF"] = df_42b["MACIF"].astype(str)
#         df_42b["STKKH"] = df_42b["STKKH"].astype(str)
    
#         df_42a = df_42a.merge(
#             df_42b.drop_duplicates("MACIF")[["MACIF", "CHARGELEVELCODE_CIF"]],
#             left_on="CUSTSEQ", right_on="MACIF", how="left"
#         ).drop(columns=["MACIF"], errors="ignore")
    
#         df_42a.rename(columns={"CHARGELEVELCODE_CIF": "CHARGELEVELCODE_CUA_CIF"}, inplace=True)
    
#         df_42a = df_42a.merge(
#             df_42b.drop_duplicates("STKKH")[["STKKH", "CHARGELEVELCODE_TK"]],
#             left_on="IDXACNO", right_on="STKKH", how="left"
#         ).drop(columns=["STKKH"], errors="ignore")
    
#         df_42a.rename(columns={"CHARGELEVELCODE_TK": "CHARGELEVELCODE_CUA_TK"}, inplace=True)
    
    
#         # TK ưu đãi CBNV
#         df_42a["TK_GAN_CODE_UU_DAI_CBNV"] = np.where(
#             df_42a["CHARGELEVELCODE_CUA_TK"] == "NVEIB", "X", ""
#         )
    
    
#         # ============================================================
#         # 3) GHÉP NHÂN SỰ NGHỈ VIỆC
#         # ============================================================
#         df_42d = read_excel_file_bytesio(file_42d_upload)
#         df_42d = ensure_columns(df_42d, ["CIF", "Ngày thôi việc"])
    
#         df_42a = df_42a.merge(df_42d, left_on="CUSTSEQ", right_on="CIF", how="left")
    
#         df_42a["CBNV_NGHI_VIEC"] = np.where(df_42a["CIF"].notna(), "X", "")
#         df_42a.rename(columns={"Ngày thôi việc": "NGAY_NGHI_VIEC"}, inplace=True)
#         df_42a["NGAY_NGHI_VIEC"] = safe_to_datetime(df_42a["NGAY_NGHI_VIEC"]).dt.strftime("%m/%d/%Y")
#         df_42a.drop(columns=["CIF"], inplace=True, errors="ignore")
    
    
#         # ============================================================
#         # 4) MAPPING (TIÊU CHÍ 5)
#         # ============================================================
#         df_map = read_excel_file_bytesio(file_mapping_upload)
#         df_map.columns = df_map.columns.str.lower()
    
#         need_cols = [
#             "brcd","semaacount","cardnbr","token","relation","uploaddt",
#             "odaccount","acctcd","dracctno","drratio","adduser","updtuser",
#             "expiredate","custnm","cif","xpcode","xpcodedt","remark","oldxpcode"
#         ]
#         df_map = ensure_columns(df_map, need_cols)
#         df_map = df_map[need_cols]
    
#         df_map["uploaddt"] = safe_to_datetime(df_map["uploaddt"])
#         df_map["xpcodedt"] = safe_to_datetime(df_map["xpcodedt"])
    
#         df_map["SO_NGAY_MO_THE"] = (df_map["xpcodedt"] - df_map["uploaddt"]).dt.days
    
#         df_map["MO_DONG_TRONG_6_THANG"] = df_map.apply(
#             lambda r: "X" if (
#                 pd.notnull(r["SO_NGAY_MO_THE"]) and
#                 0 <= r["SO_NGAY_MO_THE"] < 180 and
#                 r["uploaddt"] > pd.to_datetime("2025-06-30")
#             ) else "",
#             axis=1
#         )
    
#         df_map["xpcodedt"] = df_map["xpcodedt"].dt.strftime("%m%d%Y")
#         df_map["uploaddt"] = df_map["uploaddt"].dt.strftime("%m%d%Y")
    
#         return df_42a, df_map
# # # ---------------------------
# # def process_tieuchi_4_5(
# #     files_42a_upload: List,
# #     file_42b_upload,
# #     file_42c_upload,
# #     file_42d_upload,
# #     file_mapping_upload,
# #     chi_nhanh: str
# # ):
# #     """Trả về df_42a_processed, df_mapping_final"""
# #     # 1) ghép file 42a (HDV_CHITIET_KKH_*)
# #     df_ghep42a = pd.concat([read_excel_file_bytesio(f) for f in files_42a_upload], ignore_index=True) if files_42a_upload else pd.DataFrame()
# #     df_42a = df_ghep42a[df_ghep42a["BRCD"].astype(str).str.upper().str.contains(chi_nhanh)].copy() if not df_ghep42a.empty else pd.DataFrame()

# #     # keep columns
# #     columns_needed_42a = ['BRCD', 'DEPTCD', 'CUST_TYPE', 'CUSTSEQ', 'NMLOC', 'BIRTH_DAY',
# #                           'IDXACNO', 'SCHM_NAME', 'CCYCD', 'CURBAL_VN', 'OPNDT_FIRST', 'OPNDT_EFFECT']
# #     df_42a = df_42a[[c for c in columns_needed_42a if c in df_42a.columns]].copy()

# #     # KHCN
# #     if 'CUST_TYPE' in df_42a.columns:
# #         df_42a = df_42a[df_42a['CUST_TYPE'].str.upper() == 'KHCN'].copy()
# #     if 'CURBAL_VN' in df_42a.columns:
# #         df_42a['CURBAL_VN'] = df_42a['CURBAL_VN'].astype(str)

# #     exclude_keywords = ['KY QUY', 'GIAI NGAN', 'CHI LUONG', 'TKTT THE', 'TRUNG GIAN']
# #     if 'SCHM_NAME' in df_42a.columns:
# #         mask_exclude = df_42a['SCHM_NAME'].astype(str).str.upper().str.contains('|'.join(exclude_keywords), na=False)
# #         df_42a = df_42a[~mask_exclude].copy()

# #     # 2) df_42b (chargelevel)
# #     df_ghep42b = read_excel_file_bytesio(file_42b_upload)
# #     df_42b = df_ghep42b[df_ghep42b['CN_MO_TK'].astype(str).str.upper().str.contains(chi_nhanh)].copy() if 'CN_MO_TK' in df_ghep42b.columns else df_ghep42b.copy()

# #     # merge MACIF -> CHARGELEVELCODE_CIF
# #     if 'CUSTSEQ' in df_42a.columns and 'MACIF' in df_42b.columns:
# #         df_42a['CUSTSEQ'] = df_42a['CUSTSEQ'].astype(str)
# #         df_42b['MACIF'] = df_42b['MACIF'].astype(str)
# #         df_42b_unique_macif = df_42b.drop_duplicates(subset=['MACIF'], keep='first')
# #         df_42a = df_42a.merge(df_42b_unique_macif[['MACIF', 'CHARGELEVELCODE_CIF']], how='left', left_on='CUSTSEQ', right_on='MACIF')
# #         df_42a.rename(columns={'CHARGELEVELCODE_CIF': 'CHARGELEVELCODE_CUA_CIF'}, inplace=True)
# #         df_42a.drop(columns=['MACIF'], inplace=True, errors='ignore')

# #     # merge STKKH -> CHARGELEVELCODE_TK
# #     if 'IDXACNO' in df_42a.columns and 'STKKH' in df_42b.columns:
# #         df_42a['IDXACNO'] = df_42a['IDXACNO'].astype(str)
# #         df_42b['STKKH'] = df_42b['STKKH'].astype(str)
# #         df_42b_unique_stkkh = df_42b.drop_duplicates(subset=['STKKH'], keep='first')
# #         df_42a = df_42a.merge(df_42b_unique_stkkh[['STKKH', 'CHARGELEVELCODE_TK']], how='left', left_on='IDXACNO', right_on='STKKH')
# #         df_42a.rename(columns={'CHARGELEVELCODE_TK': 'CHARGELEVELCODE_CUA_TK'}, inplace=True)
# #         df_42a.drop(columns=['STKKH'], inplace=True, errors='ignore')

# #     # (3) TK gắn code ưu đãi CBNV
# #     if 'CHARGELEVELCODE_CUA_TK' in df_42a.columns:
# #         df_42a['TK_GAN_CODE_UU_DAI_CBNV'] = np.where(df_42a['CHARGELEVELCODE_CUA_TK'] == 'NVEIB', 'X', '')

# #     # (4) nhân sự nghỉ việc
# #     df_42d = read_excel_file_bytesio(file_42d_upload)
# #     if 'CUSTSEQ' in df_42a.columns and 'CIF' in df_42d.columns:
# #         df_42a["CBNV_NGHI_VIEC"] = df_42a["CUSTSEQ"].isin(df_42d["CIF"]).map({True: "X", False: ""})
# #         df_42a = df_42a.merge(df_42d[['CIF', 'Ngày thôi việc']], how='left', left_on='CUSTSEQ', right_on='CIF')
# #         df_42a['CBNV_NGHI_VIEC'] = np.where(df_42a['CIF'].notna(), 'X', '')
# #         df_42a.rename(columns={'Ngày thôi việc': 'NGAY_NGHI_VIEC'}, inplace=True)
# #         df_42a['NGAY_NGHI_VIEC'] = safe_to_datetime(df_42a['NGAY_NGHI_VIEC']).dt.strftime('%m/%d/%Y')

# #     # 5) Mapping_1405 -> tiêu chí 5
# #     df_mapping = read_excel_file_bytesio(file_mapping_upload)
# #     df_mapping.columns = df_mapping.columns.str.lower()
# #     cols_needed_mapping = [
# #         'brcd', 'semaacount', 'cardnbr', 'token', 'relation', 'uploaddt',
# #         'odaccount', 'acctcd', 'dracctno', 'drratio', 'adduser', 'updtuser',
# #         'expiredate', 'custnm', 'cif', 'xpcode', 'xpcodedt', 'remark', 'oldxpcode'
# #     ]
# #     existing_cols_mapping = [c for c in cols_needed_mapping if c in df_mapping.columns]
# #     df_mapping_final = df_mapping[existing_cols_mapping].copy()
# #     if 'xpcodedt' in df_mapping_final.columns:
# #         df_mapping_final['xpcodedt'] = safe_to_datetime(df_mapping_final['xpcodedt'])
# #     if 'uploaddt' in df_mapping_final.columns:
# #         df_mapping_final['uploaddt'] = safe_to_datetime(df_mapping_final['uploaddt'])

# #     if 'xpcodedt' in df_mapping_final.columns and 'uploaddt' in df_mapping_final.columns:
# #         df_mapping_final['SO_NGAY_MO_THE'] = (df_mapping_final['xpcodedt'] - df_mapping_final['uploaddt']).dt.days
# #         df_mapping_final['MO_DONG_TRONG_6_THANG'] = df_mapping_final.apply(
# #             lambda row: 'X' if (
# #                 pd.notnull(row.get('SO_NGAY_MO_THE')) and
# #                 row.get('SO_NGAY_MO_THE') >= 0 and
# #                 row.get('SO_NGAY_MO_THE') < 180 and
# #                 pd.notnull(row.get('uploaddt')) and
# #                 row.get('uploaddt') > pd.to_datetime('2023-05-31')
# #             ) else '', axis=1
# #         )

# #     return df_42a, df_mapping_final


# # ---------------------------
# # STREAMLIT UI PUBLIC FUNCTION
# # ---------------------------
# def run_dvkh_5_tieuchi():
#     st.title("👥 DVKH — 5 tiêu chí (Ủy quyền, SMS/SCM, HDV, Mapping)")

#     user = get_current_user() or {"username": "unknown"}

#     tab1, tab2 = st.tabs(["Tiêu chí 1-3 (Ủy quyền + SMS/SCM)", "Tiêu chí 4-5 (42a & Mapping)"])

#     # ---- TAB 1 ----
#     # with tab1:
#     #     st.header("A. Tiêu chí 1-3: Ủy quyền + SMS + SCM010")
#     #     st.info("Upload: HDV_CHITIET_CKH (nhiều file), HDV_CHITIET_KKH (nhiều file), MUC30, Muc14_DKSMS.txt, Muc14_SCM010.xlsx")

#     #     uploaded_ckh_files = st.file_uploader("HDV_CHITIET_CKH (CKH) - multiple", type=["xls", "xlsx"], accept_multiple_files=True, key="dvkh_ckh")
#     #     uploaded_kkh_files = st.file_uploader("HDV_CHITIET_KKH (KKH) - multiple", type=["xls", "xlsx"], accept_multiple_files=True, key="dvkh_kkh")
#     #     uploaded_muc30_file = st.file_uploader("MUC 30 (Muc30) - single", type=["xls", "xlsx", "xlsx"], key="dvkh_muc30")
#     #     uploaded_sms_txt_file = st.file_uploader("Muc14_DKSMS.txt (tab-separated)", type=["txt", "csv"], key="dvkh_sms")
#     #     uploaded_scm10_xlsx_file = st.file_uploader("Muc14_SCM010.xlsx", type=["xls", "xlsx"], key="dvkh_scm10")

#     #     if st.button("Chạy Tiêu chí 1-3"):
#     #         if not (uploaded_ckh_files and uploaded_kkh_files and uploaded_muc30_file and uploaded_sms_txt_file and uploaded_scm10_xlsx_file):
#     #             st.error("Vui lòng tải lên đầy đủ các file yêu cầu cho Tiêu chí 1-3.")
#     #             audit_log("run_tieuchi_1_3_failed", "missing files", user)
#     #         else:
#     #             try:
#     #                 audit_log("run_tieuchi_1_3_start", f"files: CKH={len(uploaded_ckh_files)}, KKH={len(uploaded_kkh_files)}", user)
#     #                 merged, df_tc3 = process_uyquyen_sms_scm(uploaded_ckh_files, uploaded_kkh_files, uploaded_muc30_file, uploaded_sms_txt_file, uploaded_scm10_xlsx_file)
#     #                 st.success("Xử lý xong Tiêu chí 1-3")
#     #                 st.subheader("Kết quả — preview (Tiêu chí 3)")
#     #                 st.dataframe(df_tc3.head(200), use_container_width=True)

#     #                 # Download both sheets
#     #                 out_bytes = to_excel_bytes({
#     #                     "UyQuyen": merged,
#     #                     "UyQuyen_TC3": df_tc3
#     #                 })
#     #                 st.download_button("Tải Excel Tiêu chí 1-3", data=out_bytes, file_name="DVKH_TC1_3.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
#     #                 audit_log("run_tieuchi_1_3_success", f"rows:{len(df_tc3)}", user)
#     #             except Exception as e:
#     #                 st.error("Đã xảy ra lỗi trong quá trình xử lý Tiêu chí 1-3.")
#     #                 st.exception(e)
#     #                 audit_log("run_tieuchi_1_3_error", str(e), user)

    


#     def extract_sms_txt_from_zip(uploaded_zip_file):
#         """Trích xuất file Muc14_DKSMS.txt từ ZIP (trong bộ nhớ)."""
#         try:
#             z = zipfile.ZipFile(uploaded_zip_file)
#             for name in z.namelist():
#                 if name.lower().endswith(".txt"):
#                     return io.BytesIO(z.read(name)), name  # trả về bytesIO + tên file
#             return None, None
#         except Exception as e:
#             return None, None
    
    
#     with tab1:
#         st.header("A. Tiêu chí 1-3: Ủy quyền + SMS + SCM010")
#         st.info("Upload: CKH (nhiều), KKH (nhiều), MUC30, ZIP chứa Muc14_DKSMS.txt, SCM010.xlsx")
    
#         uploaded_ckh_files = st.file_uploader("HDV_CHITIET_CKH (CKH) - multiple", 
#                                               type=["xls", "xlsx"], 
#                                               accept_multiple_files=True, key="dvkh_ckh")
    
#         uploaded_kkh_files = st.file_uploader("HDV_CHITIET_KKH (KKH) - multiple", 
#                                               type=["xls", "xlsx"], 
#                                               accept_multiple_files=True, key="dvkh_kkh")
    
#         uploaded_muc30_file = st.file_uploader("MUC 30 (Muc30)", 
#                                                type=["xls", "xlsx"], key="dvkh_muc30")
    
#         # 🆕 Upload ZIP thay vì txt
#         uploaded_sms_zip = st.file_uploader("Muc14_DKSMS.zip (bên trong chứa 1 file .txt)", 
#                                             type=["zip"], key="dvkh_sms_zip")
    
#         uploaded_scm10_xlsx_file = st.file_uploader("Muc14_SCM010.xlsx", 
#                                                     type=["xls", "xlsx"], key="dvkh_scm10")
    
#         if st.button("Chạy Tiêu chí 1-3"):
#             # kiểm tra zip
#             if not uploaded_sms_zip:
#                 st.error("Bạn phải upload file ZIP chứa Muc14_DKSMS.txt.")
#                 audit_log("run_tieuchi_1_3_failed", "missing sms_zip", user)
#                 st.stop()
    
#             # giải nén file txt từ zip
#             sms_txt_bytes, sms_filename = extract_sms_txt_from_zip(uploaded_sms_zip)
    
#             if sms_txt_bytes is None:
#                 st.error("Không tìm thấy file .txt trong ZIP. Vui lòng kiểm tra lại ZIP!")
#                 audit_log("run_tieuchi_1_3_failed", "txt not found in zip", user)
#                 st.stop()
    
#             if not (uploaded_ckh_files and uploaded_kkh_files and uploaded_muc30_file and uploaded_scm10_xlsx_file):
#                 st.error("Vui lòng tải lên đầy đủ các file yêu cầu cho Tiêu chí 1-3.")
#                 audit_log("run_tieuchi_1_3_failed", "missing other files", user)
#             else:
#                 try:
#                     audit_log("run_tieuchi_1_3_start", f"files: CKH={len(uploaded_ckh_files)}, KKH={len(uploaded_kkh_files)}", user)
    
#                     # truyền sms_txt_bytes thay cho uploaded_sms_txt_file
#                     merged, df_tc3 = process_uyquyen_sms_scm(
#                         uploaded_ckh_files,
#                         uploaded_kkh_files,
#                         uploaded_muc30_file,
#                         sms_txt_bytes,
#                         uploaded_scm10_xlsx_file
#                     )
    
#                     st.success("Xử lý xong Tiêu chí 1-3")
    
#                     st.subheader("Kết quả — preview (Tiêu chí 3)")
#                     st.dataframe(df_tc3.head(200), use_container_width=True)
    
#                     out_bytes = to_excel_bytes({
#                         "UyQuyen": merged,
#                         "UyQuyen_TC3": df_tc3
#                     })
    
#                     st.download_button("📥 Tải Excel Tiêu chí 1-3", 
#                                        data=out_bytes,
#                                        file_name="DVKH_TC1_3.xlsx",
#                                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    
#                     audit_log("run_tieuchi_1_3_success", f"rows:{len(df_tc3)}", user)
    
#                 except Exception as e:
#                     st.error("Đã xảy ra lỗi trong quá trình xử lý Tiêu chí 1-3.")
#                     st.exception(e)
#                     audit_log("run_tieuchi_1_3_error", str(e), user)


      
#     # ---- TAB 2 ----
#     with tab2:
#         st.header("B. Tiêu chí 4 & 5 (42a / Mapping)")
#         st.info("Upload files: HDV_CHITIET_KKH (list), BC_LAY_CHARGELEVELCODE..., 10_Danh sach nhan su..., DS nghi viec..., Mapping_1405.xlsx")

#         files_42a_upload = st.file_uploader("HDV_CHITIET_KKH_*.xls (multiple)", type=["xls", "xlsx"], accept_multiple_files=True, key="dvkh_42a")
#         file_42b_upload = st.file_uploader("BC_LAY_CHARGELEVELCODE_THEO_KHCN.xlsx", type=["xls", "xlsx"], key="dvkh_42b")
#         file_42c_upload = st.file_uploader("10_Danh sach nhan su_T*.xlsx", type=["xls", "xlsx"], key="dvkh_42c")
#         file_42d_upload = st.file_uploader("2.DS..._nghi_viec.xlsx", type=["xls", "xlsx"], key="dvkh_42d")
#         file_mapping_upload = st.file_uploader("Mapping_1405.xlsx", type=["xls", "xlsx"], key="dvkh_map")
#         chi_nhanh = st.text_input("Nhập tên chi nhánh hoặc mã SOL để lọc (VD: HANOI hoặc 1405)").strip().upper()

#         if st.button("Chạy Tiêu chí 4-5"):
#             if not (files_42a_upload and file_42b_upload and file_42c_upload and file_42d_upload and file_mapping_upload and chi_nhanh):
#                 st.error("Vui lòng tải đầy đủ file và nhập chi nhánh để chạy Tiêu chí 4-5.")
#                 audit_log("run_tieuchi_4_5_failed", "missing inputs", user)
#             else:
#                 try:
#                     audit_log("run_tieuchi_4_5_start", f"chi_nhanh={chi_nhanh}", user)
#                    # df_42a_final, df_mapping_final = process_tieuchi_4_5(files_42a_upload, file_42b_upload, file_42c_upload, file_42d_upload, file_mapping_upload, chi_nhanh)
#                     df_42a_final, df_mapping_final = process_tieuchi_4_5(
#                         files_42a_upload = files_42a_upload,      # list BytesIO
#                         file_42b_upload = file_42b_upload,        # 42b
#                         file_42c_upload = file_42c_upload,        # 42c
#                         file_42d_upload = file_42d_upload,        # nghỉ việc
#                         file_mapping_upload = file_mapping_upload, # mapping
#                         chi_nhanh = chi_nhanh
#                     )


#                     st.success("Xử lý xong Tiêu chí 4-5")
#                     st.subheader("Preview Tiêu chí 4 (42a)")
#                     st.dataframe(df_42a_processed.head(200), use_container_width=True)
#                     st.subheader("Preview Tiêu chí 5 (Mapping)")
#                     st.dataframe(df_mapping_final.head(200), use_container_width=True)

#                     # xuất Excel 2 sheet
#                     out_bytes = to_excel_bytes({
#                         "Tieu_chi_4": df_42a_processed,
#                         "Tieu_chi_5": df_mapping_final
#                     })
#                     st.download_button("Tải Excel Tiêu chí 4-5", data=out_bytes, file_name="DVKH_TC4_5.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
#                     audit_log("run_tieuchi_4_5_success", f"rows4:{len(df_42a_processed)} rows5:{len(df_mapping_final)}", user)
#                 except Exception as e:
#                     st.error("Đã xảy ra lỗi trong quá trình xử lý Tiêu chí 4-5.")
#                     st.exception(e)
#                     audit_log("run_tieuchi_4_5_error", str(e), user)

#     # ---- Audit viewer & quick exports ----
#     st.markdown("---")
#     st.header("Audit & Logs")
#     st.write("Nhật ký hoạt động DVKH (local file):")
#     if os.path.exists(AUDIT_FILE):
#         try:
#             df_audit = pd.read_csv(AUDIT_FILE)
#             st.dataframe(df_audit.sort_values("timestamp", ascending=False).head(200))
#             csv_bytes = df_audit.to_csv(index=False).encode("utf-8-sig")
#             st.download_button("Tải Log Audit (CSV)", data=csv_bytes, file_name="dvkh_audit.csv", mime="text/csv")
#         except Exception as e:
#             st.error("Không thể đọc file audit.")
#             st.exception(e)
#     else:
#         st.info("Chưa có log hoạt động (file dvkh_audit.csv chưa tồn tại).")

#     # footer
#     st.markdown("---")
#     st.info("Module DVKH — hoàn tất. Liên hệ admin khi cần thêm các cột/out rule bổ sung.")
