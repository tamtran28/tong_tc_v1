import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

from module.error_utils import UserFacingError, _should_reraise, validate_sol_only

# ============================================================
#     MODULE PHÔI THẺ – GTCG
# ============================================================

def run_phoi_the():
    try:
        _run_phoi_the()
    except UserFacingError:
        raise
    except Exception as exc:
        if _should_reraise(exc):
            raise

        raise UserFacingError(
            "Đã xảy ra lỗi khi xử lý Phôi Thẻ – GTCG. Vui lòng kiểm tra mã SOL và tệp tải lên."
        ) from exc


def _run_phoi_the():
    st.header("📘 Xử lý Phôi Thẻ – GTCG")

    sol_kiem_toan = st.text_input("Nhập mã SOL kiểm toán (ví dụ: 1002):", "")

    uploaded_file1 = st.file_uploader("📂 Tải file GTCG1_<sol>.xlsx", type=["xlsx"])
    uploaded_file2 = st.file_uploader("📂 Tải file GTCG2_<sol>.xlsx", type=["xlsx"])

    if sol_kiem_toan and uploaded_file1 and uploaded_file2:
        st.success("✔ Đã nhập mã SOL & tải đủ 2 file.")
        
        if st.button("🚀 Xử lý dữ liệu phôi thẻ"):
            prefix_tbl = f"{sol_kiem_toan}G"

            # ================================================================
            # 1) XỬ LÝ FILE GTCG1 (TIÊU CHÍ 1 & 2)
            # ================================================================
            df = pd.read_excel(uploaded_file1, dtype={"ACC_NO": str})

            df["ACC_NO"] = df["ACC_NO"].astype(str)
            df["INVT_TRAN_DATE"] = pd.to_datetime(df["INVT_TRAN_DATE"])
            df.sort_values(by="INVT_SRL_NUM", ascending=True, inplace=True)
            df.reset_index(drop=True, inplace=True)

            # (1) Số lần in hỏng
            failure_mask = (df["PASSBOOK_STATUS"] == "F") & (df["INVT_LOCN_CODE_TO"] == "IS")
            total_failure_counts = df.loc[failure_mask, "ACC_NO"].map(
                df.loc[failure_mask, "ACC_NO"].value_counts()
            )
            df["Số lần in hỏng"] = total_failure_counts.fillna(0).astype(int)

            # (2) In hỏng nhiều lần 1 ngày
            df["daily_failures"] = df[failure_mask].groupby(
                ["ACC_NO", df["INVT_TRAN_DATE"].dt.date]
            ).transform("size")

            df["TTK in hỏng nhiều lần trong 01 ngày"] = np.where(
                df["daily_failures"] >= 2, "X", ""
            )
            df.drop(columns=["daily_failures"], inplace=True)

            # (3) In hết dòng
            df["TRAN_DATE_ONLY"] = df["INVT_TRAN_DATE"].dt.date
            hetdong_mask = (df["PASSBOOK_STATUS"] == "U") & (df["INVT_LOCN_CODE_TO"] == "IS")

            df["Số lần in hết dòng"] = (
                df.loc[hetdong_mask, "ACC_NO"]
                .map(df.loc[hetdong_mask, "ACC_NO"].value_counts())
                .fillna(0)
                .astype(int)
            )

            df["daily_het_dong"] = df[hetdong_mask].groupby(
                ["ACC_NO", "TRAN_DATE_ONLY"]
            )["ACC_NO"].transform("count")

            df["TTK in hết dòng nhiều lần trong 01 ngày"] = np.where(
                df["daily_het_dong"] >= 2, "X", ""
            )
            df.drop(columns=["daily_het_dong"], inplace=True)

            # (4) Vừa in hỏng + hết dòng trong 1 ngày
            df_temp = df.groupby(["ACC_NO", "TRAN_DATE_ONLY"]).agg({
                "Số lần in hỏng": "sum",
                "Số lần in hết dòng": "sum",
            }).reset_index()

            df_temp["TTK vừa in hỏng vừa in hết dòng trong 01 ngày"] = np.where(
                (df_temp["Số lần in hỏng"] > 0) & (df_temp["Số lần in hết dòng"] > 0),
                "X",
                "",
            )

            df = df.merge(
                df_temp[
                    ["ACC_NO", "TRAN_DATE_ONLY", "TTK vừa in hỏng vừa in hết dòng trong 01 ngày"]
                ],
                on=["ACC_NO", "TRAN_DATE_ONLY"],
                how="left",
            )

            df.drop(columns=["TRAN_DATE_ONLY"], inplace=True)
            df["INVT_TRAN_DATE"] = df["INVT_TRAN_DATE"].dt.strftime("%m/%d/%Y")

            # ================================================================
            # 2) XỬ LÝ FILE GTCG2 (TIÊU CHÍ 3)
            # ================================================================
            df_muc18 = pd.read_excel(uploaded_file2)

            df_muc18["TBL"] = df_muc18["INVT_XFER_PARTICULAR"].astype(str).str.extract(
                f"({prefix_tbl}[^\\s/]*)"
            )[0]

            df_muc18["Phôi hỏng không gắn số"] = (
                df_muc18["INVT_LOCN_CODE_TO"]
                .astype(str)
                .str.contains("FAIL PRINT|FAIL", na=False)
                & ~df_muc18["INVT_XFER_PARTICULAR"].astype(str).str.contains(prefix_tbl)
            ).map({True: "X", False: ""})

            # (2) Số lần phát hành
            mask_ph = (df_muc18["INVT_LOCN_CODE_TO"] == "IS") & df_muc18["TBL"].notna()
            df_ph = df_muc18[mask_ph]

            ph_counts = df_ph["TBL"].value_counts().to_dict()
            df_muc18["Số lần phát hành"] = df_muc18["TBL"].map(ph_counts).fillna(0).astype(int)

            # (3) PH nhiều lần trong 1 ngày
            df_muc18["INVT_TRAN_DATE_ONLY"] = pd.to_datetime(
                df_muc18["INVT_TRAN_DATE"]
            ).dt.date

            df_muc18["PH nhiều lần trong 1 ngày"] = ""

            df_is = df_muc18[df_muc18["INVT_LOCN_CODE_TO"] == "IS"]
            df_count = df_is.groupby(["TBL", "INVT_TRAN_DATE_ONLY"]).size().reset_index(name="count")

            multi_groups = df_count[df_count["count"] >= 2]
            multi_keys = set(zip(multi_groups["TBL"], multi_groups["INVT_TRAN_DATE_ONLY"]))

            df_muc18["PH nhiều lần trong 1 ngày"] = df_muc18.apply(
                lambda r: "X"
                if (r["INVT_LOCN_CODE_TO"] == "IS"
                    and (r["TBL"], r["INVT_TRAN_DATE_ONLY"]) in multi_keys)
                else "",
                axis=1,
            )

            # (4) Số lần in hỏng
            mask_hong = (
                df_muc18["INVT_LOCN_CODE_TO"].isin(["FAIL", "FAIL PRINT"])
                & df_muc18["TBL"].notna()
            )

            df_hong = df_muc18[mask_hong]
            hong_counts = df_hong["TBL"].value_counts().to_dict()
            df_muc18["Số lần in hỏng"] = df_muc18["TBL"].map(hong_counts).fillna(0).astype(int)

            # (5) In hỏng nhiều lần trong 1 ngày
            df_muc18["In hỏng nhiều lần 1 ngày"] = ""

            mask_h2 = (
                (df_muc18["INVT_LOCN_CODE_TO"] == "FAIL PRINT")
                & (df_muc18["Số lần in hỏng"] >= 2)
            )

            df_fail2 = df_muc18[mask_h2]

            fail_groups = (
                df_fail2.groupby(["TBL", "INVT_TRAN_DATE_ONLY"])
                .filter(lambda g: len(g) >= 2)
            )

            df_muc18.loc[fail_groups.index, "In hỏng nhiều lần 1 ngày"] = "X"

            # (6) PH nhiều lần + có in hỏng
            df_muc18["PH nhiều lần + có in hỏng"] = df_muc18.apply(
                lambda r: "X"
                if (r["Số lần phát hành"] > 1 and r["Số lần in hỏng"] > 0)
                else "",
                axis=1,
            )

            df_muc18.drop(columns=["INVT_TRAN_DATE_ONLY", "TBL"], inplace=True)

            # ================================================================
            # 3) XUẤT FILE KẾT QUẢ
            # ================================================================
            output = BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df.to_excel(writer, sheet_name="tieu_chi_1_2", index=False)
                df_muc18.to_excel(writer, sheet_name="tieu_chi_3", index=False)

            st.success("🎯 Đã xử lý dữ liệu phôi thẻ thành công!")

            st.download_button(
                label="📥 Tải file kết quả (Phoi_the.xlsx)",
                data=output.getvalue(),
                file_name=f"Phoi_the_{sol_kiem_toan}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    else:
        st.info("Vui lòng nhập mã SOL và tải đủ 2 file Excel.")

