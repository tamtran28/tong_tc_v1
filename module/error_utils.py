import traceback
from typing import Callable, Iterable, List, Optional

import streamlit as st


class UserFacingError(Exception):
    """Lỗi dùng để hiển thị thông điệp thân thiện cho người dùng cuối."""


def render_error(message: str, exc: Optional[Exception] = None) -> None:
    """Hiển thị lỗi thân thiện và (tuỳ chọn) chi tiết kỹ thuật trong expander."""
    st.error(message)
    if exc is not None:
        with st.expander("Chi tiết kỹ thuật (dành cho đội phát triển)"):
            st.code(
                "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
                language="text",
            )


def _should_reraise(exc: Exception) -> bool:
    """Trả về True nếu đó là exception đặc biệt của Streamlit cần propagate."""
    try:
        from streamlit.runtime.scriptrunner import RerunException, StopException

        return isinstance(exc, (RerunException, StopException))
    except Exception:
        return False


def require_columns(df, required: Iterable[str]) -> List[str]:
    """Trả về danh sách cột còn thiếu (nếu có)."""
    required_set = {col.strip().upper() for col in required}
    existing = set(df.columns.str.strip().str.upper())
    return sorted(required_set - existing)


def ensure_required_columns(df, required: Iterable[str]) -> None:
    """Raise UserFacingError nếu thiếu cột bắt buộc."""
    missing = require_columns(df, required)
    if missing:
        raise UserFacingError("Tệp Excel thiếu các cột bắt buộc: " + ", ".join(missing))


def normalize_columns(df):
    """Chuẩn hoá tên cột: bỏ khoảng trắng, viết hoa để giảm xung đột khi nhập file."""
    df.columns = df.columns.str.strip().str.upper()
    return df


def run_with_user_error(fn: Callable[[], None], context: str) -> None:
    """Wrapper để hiển thị thông báo lỗi thân thiện cho toàn bộ UI chính."""
    try:
        fn()
    except UserFacingError as exc:
        render_error(str(exc))
    except Exception as exc:
        if _should_reraise(exc):
            raise

        render_error(
            f"Đã xảy ra lỗi khi {context}. Vui lòng kiểm tra dữ liệu đầu vào và thử lại.",
            exc,
        )


# ==========================================================
# VALIDATE INPUT – SOL ONLY (4 digits)
# ==========================================================

def validate_sol_only(raw: str, sol_length: int = 4) -> str:
    """
    Validate mã SOL.
    - Chỉ chấp nhận đúng 4 chữ số (VD: 0001, 0100, 1234)
    - Không cho nhập chữ / ký tự đặc biệt / tên chi nhánh
    """
    if raw is None:
        raise UserFacingError("Vui lòng nhập mã SOL.")

    s = str(raw).strip()

    if s == "":
        raise UserFacingError("Vui lòng nhập mã SOL (ví dụ: 0001).")

    if not s.isdigit():
        raise UserFacingError("Mã SOL chỉ được chứa chữ số (0–9).")

    if len(s) != sol_length:
        raise UserFacingError(f"Mã SOL phải gồm đúng {sol_length} chữ số (ví dụ: 0001).")

    return s


def validate_branch_has_data(df, col: str, sol_4: str, src_name: str) -> None:
    """
    Validate nâng cao: kiểm tra SOL có xuất hiện trong df[col] hay không.
    Dùng để tránh user nhập sai dẫn tới lọc ra rỗng.
    """
    if df is None or getattr(df, "empty", True):
        raise UserFacingError(f"Dữ liệu {src_name} rỗng hoặc không đọc được.")

    if col not in df.columns:
        # Không chặn nếu thiếu cột (tuỳ thực tế), nhưng bạn có thể đổi thành raise nếu muốn chặt
        return

    sol = validate_sol_only(sol_4)

    # Chuẩn hoá dữ liệu SOL trong df: về string và zfill(4)
    series = df[col].astype(str).str.strip()
    series = series.apply(lambda x: x.zfill(4) if x.isdigit() else x)

    n = (series == sol).sum()
    if n == 0:
        raise UserFacingError(
            f"Không tìm thấy dữ liệu {src_name} theo mã SOL '{sol}'. "
            "Vui lòng kiểm tra lại mã SOL."
        )

# import traceback
# from typing import Callable, Iterable, List, Optional
# import streamlit as st



# class UserFacingError(Exception):
#     """Lỗi dùng để hiển thị thông điệp thân thiện cho người dùng cuối."""


# def render_error(message: str, exc: Optional[Exception] = None) -> None:
#     """Hiển thị lỗi thân thiện và (tuỳ chọn) chi tiết kỹ thuật trong expander."""
#     st.error(message)
#     if exc is not None:
#         with st.expander("Chi tiết kỹ thuật (dành cho đội phát triển)"):
#             st.code(
#                 "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
#                 language="text",
#             )


# def _should_reraise(exc: Exception) -> bool:
#     """Trả về True nếu đó là exception đặc biệt của Streamlit cần propagate."""
#     try:
#         from streamlit.runtime.scriptrunner import RerunException, StopException

#         return isinstance(exc, (RerunException, StopException))
#     except Exception:
#         return False


# def require_columns(df, required: Iterable[str]) -> List[str]:
#     """Trả về danh sách cột còn thiếu (nếu có)."""
#     required_set = {col.strip().upper() for col in required}
#     existing = set(df.columns.str.strip().str.upper())
#     return sorted(required_set - existing)


# def ensure_required_columns(df, required: Iterable[str]) -> None:
#     """Raise UserFacingError nếu thiếu cột bắt buộc."""
#     missing = require_columns(df, required)
#     if missing:
#         raise UserFacingError(
#             "Tệp Excel thiếu các cột bắt buộc: " + ", ".join(missing)
#         )


# def normalize_columns(df):
#     """Chuẩn hoá tên cột: bỏ khoảng trắng, viết hoa để giảm xung đột khi nhập file."""
#     df.columns = df.columns.str.strip().str.upper()
#     return df


# def run_with_user_error(fn: Callable[[], None], context: str) -> None:
#     """Wrapper để hiển thị thông báo lỗi thân thiện cho toàn bộ UI chính.

#     Parameters
#     ----------
#     fn: Callable
#         Hàm thực thi (không đối số) cần bọc lỗi.
#     context: str
#         Mô tả ngắn gọn cho hành động, dùng trong thông báo lỗi chung.
#     """
#     try:
#         fn()
#     except UserFacingError as exc:
#         render_error(str(exc))
#     except Exception as exc:
#         if _should_reraise(exc):
#             raise

#         render_error(
#             f"Đã xảy ra lỗi khi {context}. Vui lòng kiểm tra dữ liệu đầu vào và thử lại.",
#             exc,
#         )
