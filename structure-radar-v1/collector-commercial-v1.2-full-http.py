"""Fetch the complete Seoul commercial baseline through the approved HTTP API.

This is an initialization job, not a frequent scheduler. It raises the safe
row ceiling to cover the currently reported source sizes and paces requests.
"""

from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "collector-commercial-v1.py"

spec = importlib.util.spec_from_file_location("commercial_v1_full", SOURCE)
if spec is None or spec.loader is None:
    raise RuntimeError("collector-commercial-v1.py를 불러올 수 없습니다.")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

# Current reported totals are approximately 52k and 32k. 100k leaves room for
# normal growth while preventing an accidental unbounded extraction.
base.MAX_ROWS_PER_SOURCE = 100000


def fetch_page_http(key: str, service: str, start: int, end: int) -> dict:
    url = f"http://openapi.seoul.go.kr:8088/{key}/json/{service}/{start}/{end}/"
    time.sleep(0.12)
    with urlopen(url, timeout=45) as response:  # nosec B310: official HTTP-only endpoint, user-approved dedicated key
        return json.loads(response.read().decode("utf-8"))


base.fetch_page = fetch_page_http

if __name__ == "__main__":
    raise SystemExit(base.main())
