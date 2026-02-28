import streamlit as st
import pandas as pd
from io import BytesIO
import re


def _safe_colname(s: str) -> str:
    """Làm sạch tên cột để an toàn khi ghép header."""
    s = "" if s is None else str(s)
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\s\-\.]", "_", s)  # thay ký tự lạ bằng _
    s = s.replace(" ", "_")
    return s[:120]  # tránh header quá dài


def run_chuyen_tien():
    uploaded = st.file_uploader(
        "📁 Upload file Mục 09 (Chuyển tiền)",
        type=["xls", "xlsx"]
    )

    if uploaded is None:
        st.info("Vui lòng upload file Mục 09 để xử lý.")
        return

    if st.button("▶️ Chạy Mục 09"):

        # ================================
        # ĐỌC FILE – BẮT LỖI
        # ================================
        try:
            df = pd.read_excel(uploaded)
        except Exception as e:
            st.error("❌ Không đọc được file Excel.")
            st.exception(e)
            return

        if df.empty:
            st.warning("⚠️ File không có dữ liệu.")
            return

        # ================================
        # KIỂM TRA CỘT BẮT BUỘC
        # ================================
        required_cols = ["TRAN_DATE", "PART_NAME", "PURPOSE_OF_REMITTANCE", "TRAN_ID", "QUY_DOI_USD"]
        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols:
            st.error("❌ File thiếu cột bắt buộc:")
            st.code("\n".join(missing_cols))
            return

        # ================================
        # CHUẨN HÓA DỮ LIỆU
        # ================================
        try:
            df["TRAN_DATE"] = pd.to_datetime(df["TRAN_DATE"], errors="coerce")
            df["YEAR"] = df["TRAN_DATE"].dt.year
            df["QUY_DOI_USD"] = pd.to_numeric(df["QUY_DOI_USD"], errors="coerce").fillna(0)
        except Exception as e:
            st.error("❌ Lỗi khi chuẩn hóa TRAN_DATE / YEAR / QUY_DOI_USD.")
            st.exception(e)
            return

        invalid_dates = int(df["TRAN_DATE"].isna().sum())
        if df["YEAR"].notna().sum() == 0:
            st.error("❌ Không xác định được YEAR vì TRAN_DATE không parse được.")
            st.info(f"Số dòng TRAN_DATE lỗi parse: {invalid_dates}")
            return

        # ================================
        # XÁC ĐỊNH 3 NĂM GẦN NHẤT
        # ================================
        nam_max = int(df["YEAR"].max())
        nam_T = nam_max
        nam_T1 = nam_T - 1
        nam_T2 = nam_T - 2
        cac_nam = [nam_T2, nam_T1, nam_T]

        # ================================
        # LOẠI TRÙNG
        # ================================
        before = len(df)
        df = df.drop_duplicates(subset=["PART_NAME", "PURPOSE_OF_REMITTANCE", "TRAN_DATE", "TRAN_ID"])
        removed_dup = before - len(df)

        # ================================
        # TỔNG HỢP
        # ================================
        ket_qua = pd.DataFrame()
        ds_muc_dich = df["PURPOSE_OF_REMITTANCE"].dropna().unique()

        if len(ds_muc_dich) == 0:
            st.warning("⚠️ Không có PURPOSE_OF_REMITTANCE hợp lệ để tổng hợp.")
            return

        try:
            for muc_dich in ds_muc_dich:
                df_muc_dich = df[df["PURPOSE_OF_REMITTANCE"] == muc_dich]
                muc_dich_safe = _safe_colname(muc_dich)

                for nam in cac_nam:
                    df_nam = df_muc_dich[df_muc_dich["YEAR"] == nam]
                    if df_nam.empty:
                        continue

                    pivot = df_nam.groupby("PART_NAME").agg(
                        tong_lan_nhan=("TRAN_ID", "count"),
                        tong_tien_usd=("QUY_DOI_USD", "sum")
                    ).reset_index()

                    col_lan = f"{muc_dich_safe}_LAN_{nam}"
                    col_tien = f"{muc_dich_safe}_TIEN_{nam}"

                    pivot.rename(columns={
                        "tong_lan_nhan": col_lan,
                        "tong_tien_usd": col_tien
                    }, inplace=True)

                    ket_qua = pivot if ket_qua.empty else pd.merge(
                        ket_qua, pivot, on="PART_NAME", how="outer"
                    )
        except Exception as e:
            st.error("❌ Lỗi khi tổng hợp/pivot dữ liệu.")
            st.exception(e)
            return

        if ket_qua.empty:
            st.warning("⚠️ Không có dữ liệu sau khi tổng hợp (có thể 3 năm gần nhất không có giao dịch).")
            return

        # ================================
        # FILL NA + ÉP KIỂU
        # ================================
        for col in ket_qua.columns:
            if "_LAN_" in col:
                ket_qua[col] = ket_qua[col].fillna(0).astype(int)
            elif "_TIEN_" in col:
                ket_qua[col] = ket_qua[col].fillna(0).astype(float)

        # ================================
        # THÔNG BÁO
        # ================================
        if invalid_dates > 0:
            st.warning(f"⚠️ Có {invalid_dates} dòng TRAN_DATE không parse được (YEAR sẽ NaN).")

        st.success("✔ Đã tổng hợp chuyển tiền theo PART_NAME, PURPOSE và 3 năm gần nhất.")
        st.info(
            f"📌 Năm xử lý: {cac_nam} | "
            f"Mục đích: {len(ds_muc_dich)} | "
            f"Loại trùng: {removed_dup}"
        )

        st.dataframe(ket_qua, use_container_width=True)

        # ================================
        # XUẤT FILE
        # ================================
        try:
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                ket_qua.to_excel(writer, sheet_name="tong_hop", index=False)

                # Sheet meta (tuỳ chọn)
                meta = pd.DataFrame([{
                    "nam_T2": nam_T2, "nam_T1": nam_T1, "nam_T": nam_T,
                    "invalid_dates": invalid_dates,
                    "removed_duplicates": removed_dup,
                    "so_muc_dich": len(ds_muc_dich),
                    "rows_after_dedup": len(df)
                }])
                meta.to_excel(writer, sheet_name="meta", index=False)

            st.download_button(
                "⬇️ Tải file tong_hop_chuyen_tien.xlsx",
                data=buffer.getvalue(),
                file_name=f"tong_hop_chuyen_tien_{nam_T2}_{nam_T}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except Exception as e:
            st.error("❌ Lỗi khi xuất file Excel.")
            st.exception(e)
