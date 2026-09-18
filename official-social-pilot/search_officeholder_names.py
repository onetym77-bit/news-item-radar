#!/usr/bin/env python3
"""Bounded L0 web-search discovery of officeholder Facebook profile candidates."""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlsplit
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
SEEDS = HERE / "name_search_seeds.json"
REGISTRY = HERE / "accounts.json"
API = "https://openapi.naver.com/v1/search/webkr.json"
KST = timezone(timedelta(hours=9))
MAX_BYTES = 500_000
MAX_RESULTS = 5
MAX_CANDIDATES = 3
EXCLUDED_PATHS = {
    "share", "sharer", "sharer.php", "posts", "events", "watch", "login",
    "pages", "groups", "help", "marketplace", "reel", "photo.php",
    "story.php", "permalink.php", "hashtag", "www.facebook.com",
}


def profile_url(raw: str) -> str | None:
    try:
        parsed = urlsplit(unescape(raw).strip())
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if host.startswith(("www.", "m.", "web.")):
        host = host.split(".", 1)[1]
    if parsed.scheme != "https" or host != "facebook.com" or parsed.username or parsed.password:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return None
    if parts[0].lower() == "profile.php":
        ids = parse_qs(parsed.query).get("id", [])
        return f"https://www.facebook.com/profile.php?id={ids[0]}" if len(ids) == 1 and ids[0].isdigit() else None
    if len(parts) != 1 or parts[0].lower() in EXCLUDED_PATHS or not re.fullmatch(r"[A-Za-z0-9._-]{2,80}", parts[0]):
        return None
    return f"https://www.facebook.com/{parts[0]}"


def validate_seeds(data: dict, registry: dict) -> list[str]:
    rows = data.get("entities")
    if data.get("schema") != 1 or not isinstance(rows, list):
        return ["invalid seed schema"]
    expected = {e["id"] for e in registry["entities"]}
    ids = [row.get("entity_id") for row in rows]
    errors = []
    if len(ids) != 26 or set(ids) != expected or len(set(ids)) != 26:
        errors.append("exactly 26 distinct registered entity IDs required")
    for row in rows:
        if not row.get("officeholder_name") or not row.get("municipality"):
            errors.append(f"{row.get('entity_id')}: missing name or municipality")
        if row.get("name_evidence") not in {"OFFICIAL_PAGE", "SECONDARY_ELECTION_ROSTER_SEED"}:
            errors.append(f"{row.get('entity_id')}: invalid name evidence")
        source = row.get("name_source", "")
        parsed = urlsplit(source)
        if parsed.scheme != "https" or not parsed.hostname:
            errors.append(f"{row.get('entity_id')}: invalid name source")
    return errors


def queries(row: dict) -> list[str]:
    name = row["officeholder_name"]
    place = row["municipality"]
    title = "서울시장" if row["entity_id"] == "seoul" else "구청장"
    return [f"{name} {place} {title} 페이스북", f"{name} {place} facebook.com"]


def search_web(query: str, client_id: str, client_secret: str) -> tuple[str, list[dict]]:
    url = f"{API}?query={quote(query)}&display={MAX_RESULTS}&start=1"
    request = Request(url, headers={
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
        "User-Agent": "news-item-radar-officeholder-l0/1.0",
        "Accept": "application/json",
    })
    try:
        with urlopen(request, timeout=10) as response:
            if response.geturl().split("?", 1)[0] != API:
                return "REDIRECT_REJECTED", []
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                return "OVERSIZE_RESPONSE", []
            payload = json.loads(raw.decode("utf-8"))
            items = payload.get("items", [])
            return ("SUCCESS", items if isinstance(items, list) else [])
    except HTTPError as exc:
        return f"HTTP_{exc.code}", []
    except (URLError, OSError, TimeoutError, ValueError, UnicodeError, json.JSONDecodeError):
        return "SEARCH_ACCESS_ERROR", []


def discover(row: dict, client_id: str, client_secret: str, search=search_web) -> dict:
    result = {
        "entity_id": row["entity_id"],
        "municipality": row["municipality"],
        "officeholder_name": row["officeholder_name"],
        "name_evidence": row["name_evidence"],
        "name_source": row["name_source"],
        "status": "NOT_CONFIGURED",
        "queries_attempted": 0,
        "results_seen": 0,
        "profile_candidates": [],
    }
    if not client_id or not client_secret:
        return result
    seen = set()
    for query in queries(row):
        status, items = search(query, client_id, client_secret)
        result["queries_attempted"] += 1
        if status != "SUCCESS":
            result["status"] = status
            return result
        result["results_seen"] += len(items)
        for rank, item in enumerate(items[:MAX_RESULTS], 1):
            title = re.sub(r"<[^>]*>", "", unescape(str(item.get("title", "")))).strip()
            # A Facebook URL in a search hit can belong to an institution or an unrelated page.
            if title not in {f"{row['officeholder_name']} - Facebook", f"Facebook - {row['officeholder_name']}"}:
                continue
            url = profile_url(str(item.get("link", "")))
            if url and url not in seen:
                seen.add(url)
                result["profile_candidates"].append({
                    "platform": "facebook",
                    "url": url,
                    "search_query": query,
                    "result_rank": rank,
                    "status": "UNVERIFIED_FACEBOOK_URL_ONLY",
                    "result_title": title[:120],
                })
                if len(result["profile_candidates"]) >= MAX_CANDIDATES:
                    break
        if result["profile_candidates"]:
            break
    result["status"] = "SEARCHED_WITH_FACEBOOK_URLS" if result["profile_candidates"] else "SEARCHED_NO_FACEBOOK_URL"
    return result


def render(payload: dict) -> str:
    rows = payload["entities"]
    counts = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    lines = [
        "# 서울시장·25개 구청장 이름 검색 L0",
        "",
        "네이버 웹문서 검색 결과 제목이 해당 인물 이름과 일치하는 페이스북 URL만 기록했습니다. 동명이인·팬 페이지·과거 계정일 수 있어 본인 계정 확인 수로 해석하지 않습니다.",
        f"- 검색 대상: {len(rows)}명",
        f"- 이름 일치 페이스북 URL 발견: {counts.get('SEARCHED_WITH_FACEBOOK_URLS', 0)}명",
        f"- 검색은 됐으나 이름 일치 URL 미발견: {counts.get('SEARCHED_NO_FACEBOOK_URL', 0)}명",
        "- 본인 계정으로 검증 완료: 0명 (이 검색만으로 승인 불가)",
        f"- 검색 미실행·실패: {len(rows) - counts.get('SEARCHED_WITH_FACEBOOK_URLS', 0) - counts.get('SEARCHED_NO_FACEBOOK_URL', 0)}명",
        "",
        "| 행정 단위 | 이름 | 이름 근거 | 검색 상태 | URL 수 |",
        "|---|---|---|---|---:|",
    ]
    for row in rows:
        lines.append(f"| {row['municipality']} | {row['officeholder_name']} | {row['name_evidence']} | {row['status']} | {len(row['profile_candidates'])} |")
    lines += ["", "## 미승인 페이스북 URL 검토 목록", "", "| 행정 단위 | 이름 | 검색 결과 제목 | 페이스북 URL | 검색 순위 |", "|---|---|---|---|---:|"]
    for row in rows:
        for candidate in row["profile_candidates"]:
            lines.append(
                f"| {row['municipality']} | {row['officeholder_name']} | "
                f"{candidate['result_title'].replace(chr(124), ' ')} | "
                f"<{candidate['url']}> | {candidate['result_rank']} |"
            )
    lines += [
        "",
        "미발견은 페이스북 계정 부재가 아닙니다. 검색 API가 해당 URL을 색인하지 않았거나 제목 형식이 달랐을 수 있습니다.",
        "2차 출처의 이름은 현직자 확인 전 검색용 씨앗일 뿐입니다. 위 URL은 검색 결과일 뿐이며 기관 계정·팬 페이지·과거 선거 계정을 포함할 수 있습니다.",
        "이 실행은 페이스북 프로필이나 게시물을 열지 않으며, 계정 자동 승인·질문·브리핑·장부 변경을 하지 않습니다.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument("--output-dir", type=Path, default=HERE / "output" / "name-search")
    cli.add_argument("--dry-run", action="store_true")
    args = cli.parse_args()
    seeds = json.loads(SEEDS.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    errors = validate_seeds(seeds, registry)
    if errors:
        print("\n".join(f"ERROR: {message}" for message in errors))
        return 1
    client_id = "" if args.dry_run else os.environ.get("NAVER_CLIENT_ID", "")
    client_secret = "" if args.dry_run else os.environ.get("NAVER_CLIENT_SECRET", "")
    rows = [discover(row, client_id, client_secret) for row in seeds["entities"]]
    payload = {
        "schema": 1,
        "scope": "L0_UNVERIFIED_OFFICEHOLDER_PROFILE_SEARCH_ONLY",
        "checked_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "entities": rows,
        "profile_pages_fetched": 0,
        "posts_collected": 0,
        "accounts_auto_approved": 0,
        "briefing_connected": False,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = render(payload)
    (args.output_dir / "SUMMARY.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
