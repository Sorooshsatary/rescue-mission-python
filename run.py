"""اجرای سرور مأموریت نجات: python run.py"""
from __future__ import annotations

import uvicorn


def main() -> None:
    print("مأموریت نجات در حال اجراست — نشانی: http://localhost:8000")
    print("رمز ادمین: ۱۲۳ — رمز مرحلهٔ بعد: ۱۳۸۴")
    uvicorn.run("app.server:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
