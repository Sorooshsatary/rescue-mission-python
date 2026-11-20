"""پیکربندی تست‌ها: پوشهٔ دادهٔ موقت برای هر اجرا."""
import os
import sys
from pathlib import Path

os.environ["RESCUE_DATA_DIR"] = str(Path(__file__).parent / ".test-data")
sys.path.insert(0, str(Path(__file__).parent.parent))
