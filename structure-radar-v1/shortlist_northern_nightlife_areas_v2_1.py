"""v2.1: 상권 코드의 숫자 표기 차이(예: 3001491.0)를 정규화해 현장 후보를 선별한다."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BASE_PATH = ROOT / "shortlist_northern_nightlife_areas_v2.py"


def norm(value):
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def load_base():
    spec = importlib.util.spec_from_file_location("area_v2", BASE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def main() -> int:
    base = load_base()
    if not base.MAPPING.exists():
        return base.main()
    source = json.loads(base.MAPPING.read_text(encoding="utf-8"))
    rows = source.get("rows", [])
    normalized_rows = []
    for row in rows:
        copied = dict(row)
        copied["TRDAR_CD"] = norm(copied.get("TRDAR_CD"))
        normalized_rows.append(copied)
    temp = base.OUTPUT.parent / "commercial_area_mapping" / "commercial_area_mapping_normalized.json"
    temp.parent.mkdir(parents=True, exist_ok=True)
    temp.write_text(json.dumps({**source, "rows": normalized_rows}, ensure_ascii=False), encoding="utf-8")
    base.MAPPING = temp
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
