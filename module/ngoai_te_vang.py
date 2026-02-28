import streamlit as st
import pandas as pd
import numpy as np

from module.error_utils import UserFacingError, _should_reraise
from io import BytesIO 
# ======================================================
#   MODULE: NGOẠI TỆ & VÀNG (FULL TIÊU CHÍ 1 → 6)
# ======================================================

def run_ngoai_te_vang():
    try:
        _run_ngoai_te_vang()
    except UserFacingError:
        raise
    except Exception as exc:
        if _should_reraise(exc):
            raise

        raise UserFacingError(
            "Đã xảy ra lỗi khi xử lý Ngoại tệ & Vàng (TC5–TC6). Vui lòng kiểm tra file đầu vào."
        ) from exc


def _run_ngoai_te_vang():

    st.header("💱 NGHIỆP VỤ MUA BÁN NGOẠI TỆ / VÀNG – FULL 6 TIÊU CHÍ")

    st.set_page_config(page_title="Xử lý giao dịch Ngoại tệ", layout="wide")
    
    st.markdown("""
    Upload 4 file nguồn:
    
    - **MUC49_1002**: Dữ liệu giao dịch FX chính (df_fx)  
    - **MUC20_1002**: Rate Request A (df_a)  
    - **MUC21_1002**: Rate Request B (df_b)  
    - **MUC19_1002**: Dữ liệu Mục 19 (df_muc19)  
    """)
    
    # ===============================
    # UPLOAD FILES
    # ===============================
    col1, col2 = st.columns(2)
    with col1:
        file_fx = st.file_uploader("📂 Upload file MUC49_1002 (FX)", type=["xlsx"])
        file_a = st.file_uploader("📂 Upload file MUC20_1002", type=["xlsx"])
    with col2:
        file_b = st.file_uploader("📂 Upload file MUC21_1002", type=["xlsx"])
        file_muc19 = st.file_uploader("📂 Upload file MUC19_1002", type=["xlsx"])
    
    run_btn = st.button("⚡ Chạy xử lý & tạo file Excel kết quả")
    
    def contains_any(text, keywords):
        if pd.isna(text):
            return False
        text = str(text).upper()
        return any(k in text for k in keywords)
    
    if run_btn:
        if not all([file_fx, file_a, file_b, file_muc19]):
            st.error("⚠ Vui lòng upload đầy đủ **4 file** trước khi chạy!")
            st.stop()
    
        try:
            # ===============================
            # ĐỌC FILE
            # ===============================
            df_fx = pd.read_excel(file_fx)
            df_a = pd.read_excel(file_a)
            df_b = pd.read_excel(file_b)
            df_muc19 = pd.read_excel(file_muc19)
    
            # ===============================
            # PHẦN 1: XỬ LÝ df_filtered (MUC49_1002)
            # ===============================
    
            # Loại GD có CRNCY_PURCHSD hoặc CRNCY_SOLD = GD1
            df_filtered = df_fx[
                (df_fx['CRNCY_PURCHSD'] != 'GD1') &
                (df_fx['CRNCY_SOLD'] != 'GD1')
            ].copy()
    
            # Lọc DEALER có dấu '.' và không chứa ROBOT
            filter_dot = df_filtered['DEALER'].astype(str).str.contains('.', regex=False, na=False)
            filter_not_robot = ~df_filtered['DEALER'].astype(str).str.contains('ROBOT', case=False, regex=False, na=False)
            df_filtered = df_filtered[filter_dot & filter_not_robot].copy()
    
            # P/S
            df_filtered['P/S'] = np.where(
                df_filtered['PURCHASED_AMOUNT'].fillna(0) != 0, 'P',
                np.where(df_filtered['SOLD_AMOUNT'].fillna(0) != 0, 'S', '')
            )
    
            # AMOUNT
            df_filtered['AMOUNT'] = np.where(
                df_filtered['P/S'] == 'P',
                df_filtered['PURCHASED_AMOUNT'],
                df_filtered['SOLD_AMOUNT']
            )
    
            # Rate
            df_filtered['Rate'] = np.where(
                df_filtered['P/S'] == 'P',
                df_filtered['PURCHASED_RATE'],
                df_filtered['SOLD_RATE']
            )
    
            # Treasury Rate
            df_filtered['Treasury Rate'] = np.where(
                df_filtered['P/S'] == 'P',
                df_filtered['TREASURY_BUY_RATE'],
                df_filtered['TREASURY_SELL_RATE']
            )
    
            # Loại ngoại tệ
            df_filtered['Loại Ngoại tệ'] = np.where(
                df_filtered['P/S'] == 'P',
                df_filtered['CRNCY_PURCHSD'],
                df_filtered['CRNCY_SOLD']
            )
    
            # Thông tin chung
            df_filtered['SOL'] = df_filtered['SOL_ID']
            df_filtered['Đơn vị'] = df_filtered['SOL_DESC']
            df_filtered['CIF'] = df_filtered['CIF_ID']
            df_filtered['Tên KH'] = df_filtered['CUST_NAME']
    
            df_filtered['DEAL_DATE'] = pd.to_datetime(df_filtered['DEAL_DATE'], errors='coerce')
            df_filtered['DUE_DATE'] = pd.to_datetime(df_filtered['DUE_DATE'], errors='coerce')
    
            df_filtered['TRANSACTION_NO'] = df_filtered['TRANSACTION_NO'].astype(str).str.strip()
            df_filtered['Quy đổi VND'] = df_filtered['VALUE_VND']
            df_filtered['Quy đổi USD'] = df_filtered['VALUE_USD']
            df_filtered['Mục đích'] = df_filtered['PURPOSE_OF_TRANSACTION']
            df_filtered['Kết quả Lãi/lỗ'] = df_filtered['KETQUA']
            df_filtered['Số tiền Lãi lỗ'] = df_filtered['SOTIEN_LAI_LO']
    
            # Maker, Checker, Date
            df_filtered['Maker'] = df_filtered['DEALER'].apply(
                lambda x: str(x).strip() if pd.notnull(x) and 'ROBOT' not in str(x).upper() else ''
            )
            df_filtered['Maker Date'] = pd.to_datetime(df_filtered['MAKER_DATE'], errors='coerce')
            df_filtered['Checker'] = df_filtered['VERIFY_ID']
            df_filtered['Verify Date'] = pd.to_datetime(df_filtered['VERIFY_DATE'], errors='coerce')
    
            # ===== CÁC CỘT ĐÁNH DẤU =====
    
            # GD bán ngoại tệ CK
            df_filtered['GD bán ngoại tệ CK'] = df_filtered.apply(
                lambda x: 'X' if x['P/S'] == 'S' and contains_any(x['Mục đích'], ['BAN NTE CK', 'CK']) else '',
                axis=1
            )
    
            # GD bán ngoại tệ mặt
            df_filtered['GD bán ngoại tệ mặt'] = df_filtered.apply(
                lambda x: 'X' if x['P/S'] == 'S' and contains_any(x['Mục đích'], ['BAN NTE MAT', 'MAT']) else '',
                axis=1
            )
    
            # GD bán NT không TB chi phí
            df_filtered['GD bán NT không TB chi phí'] = df_filtered.apply(
                lambda x: 'X' if x['P/S'] == 'S' and contains_any(
                    x['Mục đích'],
                    ['BO SUNG', 'SINH HOAT PHI', 'BOSUNG']
                ) else '',
                axis=1
            )
    
            # Bán NT - Trợ cấp
            df_filtered['Bán NT - Trợ cấp'] = df_filtered.apply(
                lambda x: 'X' if x['P/S'] == 'S' and contains_any(
                    x['Mục đích'], ['TRO CAP', 'TROCAP']
                ) else '',
                axis=1
            )
    
            # Bán NT - Du học
            df_filtered['Bán NT - Du học'] = df_filtered.apply(
                lambda x: 'X' if x['P/S'] == 'S' and contains_any(
                    x['Mục đích'], ['DU HOC', 'DUHOC', 'SINH HOAT PHI']
                ) else '',
                axis=1
            )
    
            # Bán NT - Du lịch
            df_filtered['Bán NT - Du lịch'] = df_filtered.apply(
                lambda x: 'X' if x['P/S'] == 'S' and contains_any(
                    x['Mục đích'], ['DU LICH', 'DULICH']
                ) else '',
                axis=1
            )
    
            # Bán NT - Công tác
            df_filtered['Bán NT - Công tác'] = df_filtered.apply(
                lambda x: 'X' if x['P/S'] == 'S' and contains_any(
                    x['Mục đích'], ['CONG TAC', 'CONGTAC']
                ) else '',
                axis=1
            )
    
            # Bán NT - Chữa bệnh
            df_filtered['Bán NT - Chữa bệnh'] = df_filtered.apply(
                lambda x: 'X' if x['P/S'] == 'S' and contains_any(
                    x['Mục đích'], ['CHUA BENH', 'CHUABENH']
                ) else '',
                axis=1
            )
    
            # Bán NT - Khác
            ban_nt_loai_tru_cols = [
                'Bán NT - Trợ cấp',
                'Bán NT - Du học',
                'Bán NT - Du lịch',
                'Bán NT - Công tác',
                'Bán NT - Chữa bệnh'
            ]
            df_filtered['Bán NT - Khác'] = df_filtered.apply(
                lambda x: 'X' if (str(x['P/S']).strip().upper() == 'S' and
                                  all(str(x[col]).strip() == '' for col in ban_nt_loai_tru_cols))
                else '',
                axis=1
            )
    
            # Nhập sai mục đích
            df_filtered['Nhập sai mục đích'] = df_filtered.apply(
                lambda x: 'X' if (
                    (x['P/S'] == 'P' and contains_any(x['Mục đích'], ['BAN'])) or
                    (x['P/S'] == 'S' and contains_any(x['Mục đích'], ['MUA']))
                ) else '',
                axis=1
            )
    
            # Thứ tự cột theo final_columns bạn định nghĩa
            final_columns = [
                'SOL', 'Đơn vị', 'CIF', 'Tên KH', 'P/S', 'AMOUNT', 'Rate', 'Treasury Rate', 'Loại Ngoại tệ',
                'DEAL_DATE', 'DUE_DATE',
                'TRANSACTION_NO', 'Quy đổi VND', 'Quy đổi USD', 'Mục đích',
                'Kết quả Lãi/lỗ', 'Số tiền Lãi lỗ', 'Maker', 'Maker Date',
                'Checker', 'Verify Date',
                'GD bán ngoại tệ CK', 'GD bán ngoại tệ mặt', 'GD bán NT không TB chi phí',
                'Bán NT - Trợ cấp', 'Bán NT - Du học', 'Bán NT - Du lịch',
                'Bán NT - Công tác', 'Bán NT - Chữa bệnh', 'Bán NT - Khác',
                'Nhập sai mục đích'
            ]
    
            df_filtered = df_filtered[final_columns].copy()
    
            # (22) Giao dịch lỗ >100.000đ
            df_filtered['GD lỗ >100.000đ'] = df_filtered.apply(
                lambda x: 'X' if x['Kết quả Lãi/lỗ'] == 'LO' and abs(x['Số tiền Lãi lỗ']) >= 100_000 else '',
                axis=1
            )
    
            # (23) GD duyệt trễ >30p
            df_filtered['Maker Date_dt'] = pd.to_datetime(df_filtered['Maker Date'], errors='coerce')
            df_filtered['Verify Date_dt'] = pd.to_datetime(df_filtered['Verify Date'], errors='coerce')
            delay = df_filtered['Verify Date_dt'] - df_filtered['Maker Date_dt']
            df_filtered['GD duyệt trễ >30p'] = delay.apply(
                lambda x: 'X' if pd.notnull(x) and x.total_seconds() > 1800 else ''
            )
            df_filtered.drop(columns=['Maker Date_dt', 'Verify Date_dt'], inplace=True)
    
            # ===============================
            # GD Rate Request (df_a + df_b)
            # ===============================
    
            # Chuẩn hóa df_a
            df_a['FRWRD_CNTRCT_NUM'] = df_a['FRWRD_CNTRCT_NUM'].astype(str).str.strip()
            df_a['TREA_REF_NUM'] = pd.to_numeric(df_a['TREA_REF_NUM'], errors='coerce')
            df_a_valid = df_a[df_a['TREA_REF_NUM'].notna()].copy()
            set_a = set(df_a_valid['FRWRD_CNTRCT_NUM'])
    
            # Chuẩn hóa df_b cho điều kiện b (theo TRAN_ID + TRAN_DATE)
            df_b['TRAN_ID'] = df_b['TRAN_ID'].astype(str).str.strip()
            df_b['TRAN_DATE'] = pd.to_datetime(df_b['TRAN_DATE'], errors='coerce').dt.strftime('%m/%d/%Y')
            df_b['TREA_REF_NUM'] = pd.to_numeric(df_b['TREA_REF_NUM'], errors='coerce')
            df_b_valid = df_b[df_b['TREA_REF_NUM'].notna()].copy()
            df_b_valid['match_key'] = list(zip(df_b_valid['TRAN_ID'], df_b_valid['TRAN_DATE']))
            set_b = set(df_b_valid['match_key'])
    
            # Chuẩn hóa df_filtered để tạo match_key
            df_filtered['TRANSACTION_NO'] = df_filtered['TRANSACTION_NO'].astype(str).str.strip()
            df_filtered['MAKER_DATE_ONLY'] = pd.to_datetime(
                df_filtered['Maker Date'], errors='coerce'
            ).dt.strftime('%m/%d/%Y')
            df_filtered['match_key'] = list(zip(df_filtered['TRANSACTION_NO'], df_filtered['MAKER_DATE_ONLY']))
    
            cond_a = df_filtered['TRANSACTION_NO'].isin(set_a)
            cond_b = df_filtered['match_key'].isin(set_b)
    
            df_filtered['GD Rate Request'] = np.where(cond_a | cond_b, 'X', '')
            df_filtered.drop(columns=['MAKER_DATE_ONLY', 'match_key'], inplace=True)
    
            # ===============================
            # XÁC ĐỊNH LOẠI TỶ GIÁ (RATE_CODE_A + RATE_CODE_B)
            # ===============================
    
            # Chuẩn hóa cho join
            df_filtered['TRANSACTION_NO'] = df_filtered['TRANSACTION_NO'].astype(str).str.strip()
            df_filtered['Maker_Date_fmt'] = pd.to_datetime(
                df_filtered['Maker Date'], errors='coerce'
            ).dt.strftime('%m/%d/%Y')
            df_filtered['AMOUNT'] = pd.to_numeric(df_filtered['AMOUNT'], errors='coerce')
    
            df_a['FRWRD_CNTRCT_NUM'] = df_a['FRWRD_CNTRCT_NUM'].astype(str).str.strip()
    
            df_b['TRAN_ID'] = df_b['TRAN_ID'].astype(str).str.strip()
            df_b['TRAN_DATE_fmt'] = pd.to_datetime(df_b['TRAN_DATE'], errors='coerce').dt.strftime('%m/%d/%Y')
            df_b['TRAN_AMT'] = pd.to_numeric(df_b['TRAN_AMT'], errors='coerce')
    
            # RATE_CODE_A theo FRWRD_CNTRCT_NUM
            rate_dict_a = df_a.set_index('FRWRD_CNTRCT_NUM')['RATE_CODE'].to_dict()
            df_filtered['RATE_CODE_A'] = df_filtered['TRANSACTION_NO'].map(rate_dict_a)
    
            # RATE_CODE_B theo (TRAN_ID, TRAN_DATE_fmt) + sai số AMOUNT nhỏ nhất
            df_temp = df_filtered[['TRANSACTION_NO', 'Maker_Date_fmt', 'AMOUNT']].copy()
            df_temp['index_main'] = df_temp.index
            df_temp['key'] = list(zip(df_temp['TRANSACTION_NO'], df_temp['Maker_Date_fmt']))
    
            df_b_temp = df_b[['TRAN_ID', 'TRAN_DATE_fmt', 'TRAN_AMT', 'RATE_CODE']].copy()
            df_b_temp['key'] = list(zip(df_b_temp['TRAN_ID'], df_b_temp['TRAN_DATE_fmt']))
    
            df_joined = df_temp.merge(df_b_temp, on='key', how='left')
    
            df_joined['diff'] = (df_joined['AMOUNT'] - df_joined['TRAN_AMT']).abs()
            df_best_match = df_joined.sort_values('diff').groupby('index_main').first().reset_index()
    
            df_filtered['RATE_CODE_B'] = df_best_match.set_index('index_main')['RATE_CODE']
    
            # Loại tỷ giá
            df_filtered['Loại tỷ giá'] = df_filtered['RATE_CODE_A'].combine_first(df_filtered['RATE_CODE_B'])
    
            df_filtered.drop(columns=['RATE_CODE_A', 'RATE_CODE_B', 'Maker_Date_fmt'], inplace=True, errors='ignore')
    
            # GD bán NT sai loại tỷ giá (bán tiền mặt nhưng loại tỷ giá != T1000)
            df_filtered['GD bán NT sai loại tỷ giá'] = np.where(
                (df_filtered['P/S'].astype(str).str.upper() == 'S') &
                (df_filtered['Mục đích'].astype(str).str.upper().str.contains('BAN NTE MAT|MAT', na=False)) &
                (df_filtered['Loại tỷ giá'].astype(str).str.upper() != 'T1000'),
                'X', ''
            )
    
            # ===============================
            # PHẦN 2: XỬ LÝ MỤC 19 → df_baocao
            # ===============================
    
            df = df_muc19.copy()
    
            df['SOL'] = df['SOL_ID']
            df['ĐON_VI'] = df['SOL_DESC']
            df['CIF'] = df['CIF_ID']
            df['Tên KH'] = df['CUST_NAME']
            df['DEAL_DATE'] = df['DEAL_DATE']
            df['DUE_DATE'] = df['DUE_DATE']
    
            # P/S
            df['P/S'] = np.where(
                df['PURCHASED_AMOUNT'].fillna(0) != 0, 'P',
                np.where(df['SOLD_AMOUNT'].fillna(0) != 0, 'S', '')
            )
    
            # AMOUNT
            df['AMOUNT'] = np.where(
                df['P/S'] == 'P', df['PURCHASED_AMOUNT'],
                np.where(df['P/S'] == 'S', df['SOLD_AMOUNT'], np.nan)
            )
    
            # RATE
            df['RATE'] = np.where(
                df['P/S'] == 'P', df['PURCHASED_RATE'],
                np.where(df['P/S'] == 'S', df['SOLD_RATE'], np.nan)
            )
    
            # Treasury Rate (ở đây để nguyên TREASURY_BUY_RATE như code bạn)
            df['TREASURY_BUY_RATE'] = df['TREASURY_BUY_RATE']
    
            # Quy đổi VND
            df['Quy đổi VND'] = df['VALUE_VND']
    
            # TRANSACTION_NO
            df['TRANSACTION_NO'] = df['TRANSACTION_NO'].astype(str).str.strip()
    
            # Maker
            df['MAKER'] = df['DEALER'].where(
                df['DEALER'].astype(str).str.contains(r'\.', na=False) &
                ~df['DEALER'].astype(str).str.contains("ROBOT", na=False),
                np.nan
            )
    
            # Maker Date & Verify Date (giữ datetime để tính delay)
            df['MAKER_DATE'] = pd.to_datetime(df['MAKER_DATE'], errors='coerce')
            df['VERIFY_DATE'] = pd.to_datetime(df['VERIFY_DATE'], errors='coerce')
    
            # Mục đích
            df['Mục đích'] = df['PURPOSE_OF_TRANSACTION']
    
            # Transaction_type
            df['Transaction_type'] = df['TRANSACTION_TYPE']
    
            # Kết quả Lãi/lỗ
            df['Kết quả Lãi/lỗ'] = df['KETQUA']
    
            # Số tiền Lãi lỗ
            df['Số tiền Lãi lỗ'] = df['SOTIEN_LAI_LO']
    
            # Loại tiền KQ & Số tiền KQ (theo đúng code bạn)
            df['Loại tiền KQ'] = df['KYQUY_NT']
            df['Số tiền KQ'] = df['LOAITIEN_KYQUY']
    
            # GD lỗ > 100.000đ
            df['GD lỗ > 100.000đ'] = np.where(
                (df['Kết quả Lãi/lỗ'] == 'LO') & (df['Số tiền Lãi lỗ'].abs() >= 100_000),
                'X', ''
            )
    
            # Cột dùng để xuất df_baocao (đúng thứ tự như bạn liệt kê)
            columns_baocao = [
                'SOL', 'ĐON_VI', 'CIF', 'Tên KH', 'DEAL_DATE', 'DUE_DATE', 'P/S', 'AMOUNT',
                'RATE', 'TREASURY_BUY_RATE', 'Quy đổi VND', 'TRANSACTION_NO', 'MAKER', 'MAKER_DATE',
                'CHECKER', 'VERIFY_DATE', 'Mục đích', 'Transaction_type', 'Kết quả Lãi/lỗ',
                'Số tiền Lãi lỗ', 'Loại tiền KQ', 'Số tiền KQ', 'GD lỗ > 100.000đ'
            ]
    
            # CHECKER (từ VERIFY_ID)
            df['CHECKER'] = df['VERIFY_ID']
    
            df_baocao = df[columns_baocao].copy()
    
            # GD duyệt trễ > 20p
            df_baocao['TIME_DELAY'] = df_baocao['VERIFY_DATE'] - df_baocao['MAKER_DATE']
            df_baocao['GD duyệt trễ > 20p'] = np.where(
                df_baocao['TIME_DELAY'] > pd.Timedelta(minutes=20),
                'X', ''
            )
    
            # ===============================
            # RATE REQUEST CHO df_baocao
            # ===============================
    
            df_baocao['TRANSACTION_NO_CLEAN'] = df_baocao['TRANSACTION_NO'].astype(str).str.strip()
            df_baocao['MAKER_DATE_FMT'] = pd.to_datetime(
                df_baocao['MAKER_DATE'], errors='coerce'
            ).dt.strftime('%m/%d/%Y')
    
            df_a['FRWRD_CNTRCT_NUM'] = df_a['FRWRD_CNTRCT_NUM'].astype(str).str.strip()
            df_a_valid2 = df_a[df_a['TREA_REF_NUM'].notna()].copy()
    
            df_b['TRAN_ID'] = df_b['TRAN_ID'].astype(str).str.strip()
            df_b['TRAN_DATE_FMT'] = pd.to_datetime(df_b['TRAN_DATE'], errors='coerce').dt.strftime('%m/%d/%Y')
    
            # Điều kiện A
            cond_a_baocao = df_baocao['TRANSACTION_NO_CLEAN'].isin(df_a_valid2['FRWRD_CNTRCT_NUM'])
    
            # Merge df_b để xem TREA_REF_NUM
            df_merged_b = df_baocao.merge(
                df_b[['TRAN_ID', 'TRAN_DATE_FMT', 'TREA_REF_NUM']].drop_duplicates(subset=['TRAN_ID', 'TRAN_DATE_FMT']),
                left_on=['TRANSACTION_NO_CLEAN', 'MAKER_DATE_FMT'],
                right_on=['TRAN_ID', 'TRAN_DATE_FMT'],
                how='left'
            )
    
            cond_b_baocao = df_merged_b['TREA_REF_NUM'].notna()
    
            df_baocao['GD Rate Request'] = np.where(cond_a_baocao | cond_b_baocao, 'X', '')
    
            # Dọn cột phụ
            df_baocao.drop(columns=['TRANSACTION_NO_CLEAN', 'MAKER_DATE_FMT'], inplace=True, errors='ignore')
    
            # ===============================
            # GD CASH & SPOT T0
            # ===============================
            df_baocao['GD CASH'] = df_baocao['Transaction_type'].astype(str).str.upper().apply(
                lambda x: 'X' if x == 'CASH' else ''
            )
    
            df_baocao['DEAL_DATE'] = pd.to_datetime(df_baocao['DEAL_DATE'], errors='coerce')
            df_baocao['DUE_DATE'] = pd.to_datetime(df_baocao['DUE_DATE'], errors='coerce')
    
            df_baocao['GD SPOT T0'] = df_baocao.apply(
                lambda row: 'X' if (
                    str(row['Transaction_type']).upper() == 'SPOT' and
                    pd.notnull(row['DEAL_DATE']) and
                    pd.notnull(row['DUE_DATE']) and
                    (row['DUE_DATE'] - row['DEAL_DATE']).days == 0
                ) else '',
                axis=1
            )
    
            # ===============================
            # TẠO FILE EXCEL KẾT QUẢ
            # ===============================
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_filtered.to_excel(writer, sheet_name='Tieu chi 1,2,3,4', index=False)
                df_baocao.to_excel(writer, sheet_name='Tieu chi 5,6', index=False)
    
            buffer.seek(0)
    
            st.success("✅ ĐÃ XỬ LÝ THÀNH CÔNG! File Excel đã sẵn sàng tải về.")
    
            st.download_button(
                label="⬇ Tải file **KQ_xuly_NT.xlsx**",
                data=buffer,
                file_name="KQ_xuly_NT.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    
            with st.expander("👀 Xem nhanh Sheet 1 – df_filtered (Tiêu chí 1,2,3,4)"):
                st.dataframe(df_filtered.head(50))
    
            with st.expander("👀 Xem nhanh Sheet 2 – df_baocao (Tiêu chí 5,6)"):
                st.dataframe(df_baocao.head(50))
    
        except Exception as e:
            st.error(f"❌ Lỗi khi xử lý: {e}")
