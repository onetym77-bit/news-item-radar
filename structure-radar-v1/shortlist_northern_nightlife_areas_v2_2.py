"""v2.2: 연결표와 상권 원본 양쪽의 상권 코드를 같은 문자열 형식으로 정규화한다."""

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
    if not base.MAPPING.exists() or not base.TREND.exists():
        return base.main()
    mapping = json.loads(base.MAPPING.read_text(encoding="utf-8"))
    trend = json.loads(base.TREND.read_text(encoding="utf-8"))
    mapping["rows"] = [{**row, "TRDAR_CD": norm(row.get("TRDAR_CD"))} for row in mapping.get("rows", [])]
    for dataset in trend.get("datasets", {}).values():
        for rows in dataset.values():
            for row in rows:
                row["TRDAR_CD"] = norm(row.get("TRDAR_CD"))
    mapping_path = base.OUTPUT.parent / "commercial_area_mapping" / "commercial_area_mapping_normalized_v2.json"
    trend_path = base.OUTPUT.parent / "commercial_area_trend" / "commercial_area_trend_normalized_v2.json"
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    trend_path.parent.mkdir(parents=True, exist_ok=True)
    mapping_path.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
    trend_path.write_text(json.dumps(trend, ensure_ascii=False), encoding="utf-8")
    base.MAPPING, base.TREND = mapping_path, trend_path
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
