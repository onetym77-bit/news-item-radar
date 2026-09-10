"""Seoul commercial baseline collector for the official HTTP-only port 8088.

Use only with a dedicated Seoul OpenAPI key approved for this purpose.
The endpoint is documented by Seoul as HTTP on port 8088. This script never
writes the key to output files, but the transport itself is not encrypted.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "collector-commercial-v1.py"

spec = importlib.util.spec_from_file_location("commercial_v1", SOURCE)
if spec is None or spec.loader is None:
    raise RuntimeError("collector-commercial-v1.py를 불러올 수 없습니다.")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


def fetch_page_http(key: str, service: str, start: int, end: int) -> dict:
    url = f"http://openapi.seoul.go.kr:8088/{key}/json/{service}/{start}/{end}/"
    with urlopen(url, timeout=45) as response:  # nosec B310: official Seoul OpenAPI HTTP-only endpoint, user-approved
        return json.loads(response.read().decode("utf-8"))


base.fetch_page = fetch_page_http

if __name__ == "__main__":
    raise SystemExit(base.main())
