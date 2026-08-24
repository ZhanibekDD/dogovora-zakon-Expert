from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.master_template_payment_service import build_master_template  # noqa: E402

OUTPUT_PATH = ROOT / "app" / "templates" / "contracts" / "master_v1.docx"


def build() -> Path:
    path = build_master_template(OUTPUT_PATH)
    print(f"Master template written to {path}")
    return path


if __name__ == "__main__":
    build()
