"""v1.1: 자치구 단위 상권 원본만 사용하도록 고정한 실행판."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BASE_PATH = ROOT / "check_northern_nightlife_longterm_v1.py"


def load_base():
    spec = importlib.util.spec_from_file_location("nightlife_base", BASE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def locate_district_tables(base):
    candidates = []
    for path in ROOT.rglob("*.json"):
        if "output" not in path.parts:
            continue
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        for rows in base.walk_lists(data):
            fields = set(rows[0])
            is_district = {"SIGNGU_CD_NM", "STDR_YYQU_CD", "SVC_INDUTY_CD_NM"}.issubset(fields) and not any(
                key in fields for key in ("TRDAR_CD", "TRDAR_NM", "TRDAR_SE_CD", "TRDAR_SE_NM")
            )
            if is_district:
                candidates.append((path, fields, rows))
    stores = [item for item in candidates if "STOR_CO" in item[1]]
    sales = [item for item in candidates if "THSMON_SELNG_AMT" in item[1] and "THSMON_SELNG_CO" in item[1]]
    return (
        max(stores, key=lambda item: len(item[2])) if stores else None,
        max(sales, key=lambda item: len(item[2])) if sales else None,
        candidates,
    )


def main() -> int:
    base = load_base()
    base.locate_tables = lambda: locate_district_tables(base)
    base.OUTPUT = ROOT / "output" / "nightlife_check"
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
