#!/usr/bin/env python3
"""Bounded search-index feasibility probe; never requests Facebook pages or posts."""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from search_officeholder_names import search_web
from verify_registry import validate_registry

HERE = Path(__file__).resolve().parent
REGISTRY = HERE / "accounts.json"
KST = timezone(timedelta(hours=9))
MAX_CANDIDATES = 3
POST_ID = re.compile(r"[A-Za-z0-9._-]{2,160}\Z")


def facebook_host(url: str) -> tuple[str, object] | None:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if host in {"www.facebook.com", "m.facebook.com", "facebook.com"} and parsed.scheme == "https" and not parsed.username and not parsed.password:
        return host, parsed
    return None


def account_identity(account_url: str) -> tuple[str, str] | None:
    checked = facebook_host(account_url)
    if not checked:
        return None
    parsed = checked[1]
    if parsed.path.rstrip("/").lower() == "/profile.php":
        ids = parse_qs(parsed.query).get("id", [])
        if len(ids) == 1 and ids[0].isdigit():
            return "numeric", ids[0]
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) == 1 and re.fullmatch(r"[A-Za-z0-9._-]{2,80}", parts[0]):
        return "handle", parts[0].lower()
    return None


def strict_post_url(raw: str, account_url: str) -> str | None:
    owner = account_identity(account_url)
    checked = facebook_host(raw)
    if not owner or not checked:
        return None
    parsed = checked[1]
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) == 3 and parts[1].lower() == "posts" and POST_ID.fullmatch(parts[2]):
        if parts[0].lower() == owner[1]:
            return f"https://www.facebook.com/{parts[0]}/posts/{parts[2]}"
    if owner[0] == "numeric" and parsed.path.rstrip("/").lower() == "/permalink.php":
        args = parse_qs(parsed.query)
        story = args.get("story_fbid", [])
        identity = args.get("id", [])
        if len(story) == len(identity) == 1 and identity[0] == owner[1] and POST_ID.fullmatch(story[0]):
            return f"https://www.facebook.com/permalink.php?story_fbid={story[0]}&id={identity[0]}"
    return None


def query_for(account_url: str, officeholder_name: str) -> str:
    owner = account_identity(account_url)
    if owner is None:
        raise ValueError("invalid Facebook account URL")
    if owner[0] == "numeric":
        return f"site:facebook.com/permalink.php {owner[1]} {officeholder_name}"
    return f"site:facebook.com/{owner[1]}/posts {officeholder_name}"


def probe(entity: dict, client_id: str, client_secret: str, search=search_web) -> dict:
    account = entity["officeholder_accounts"][0]
    row = {
        "entity_id": entity["id"],
        "officeholder_name": account["officeholder_name"],
        "account_url": account["url"],
        "status": "NOT_CONFIGURED",
        "results_seen": 0,
        "strict_owner_url_candidates": [],
        "date_status": "NOT_AVAILABLE_IN_SEARCH_INDEX",
        "platform_checked": False,
    }
    if not client_id or not client_secret:
        return row
    status, items = search(query_for(account["url"], account["officeholder_name"]), client_id, client_secret)
    if status != "SUCCESS":
        row["status"] = status
        return row
    row["results_seen"] = len(items)
    seen = set()
    for item in items:
        url = strict_post_url(str(item.get("link", "")), account["url"])
        if url and url not in seen:
            seen.add(url)
            row["strict_owner_url_candidates"].append(url)
            if len(seen) >= MAX_CANDIDATES:
                break
    row["status"] = "INDEX_URL_CANDIDATES" if seen else "SEARCHED_NO_STRICT_URL"
    return row


def render(payload: dict) -> str:
    rows = payload["entities"]
    counts = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    lines = [
        "# 단체장 페이스북 게시물 주소 검색 가능성 시험",
        "",
        "페이스북 프로필·게시물은 열지 않았습니다. 네이버 검색 색인의 URL만 원계정 주소와 엄격히 대조했으며, 게시일과 실제 게시 주체는 확인되지 않았습니다.",
        f"- 대상 계정: {len(rows)}개",
        f"- 원계정 경로와 일치하는 주소 후보: {counts.get('INDEX_URL_CANDIDATES', 0)}개 계정",
        f"- 검색 성공, 엄격 일치 주소 없음: {counts.get('SEARCHED_NO_STRICT_URL', 0)}개 계정",
        f"- 검색 미실행·실패: {len(rows) - counts.get('INDEX_URL_CANDIDATES', 0) - counts.get('SEARCHED_NO_STRICT_URL', 0)}개 계정",
        "- 검증된 게시일·본문: 0건; L1 통과: 아님; 성숙도: L0 유지",
        "",
        "| 행정 단위 ID | 이름 | 검색 상태 | 색인 결과 | 주소 후보 |",
        "|---|---|---|---:|---:|",
    ]
    for row in rows:
        lines.append(f"| {row['entity_id']} | {row['officeholder_name']} | {row['status']} | {row['results_seen']} | {len(row['strict_owner_url_candidates'])} |")
    lines += ["", "## 주소 후보(사실·게시일 미확인)", ""]
    for row in rows:
        for url in row["strict_owner_url_candidates"]:
            lines.append(f"- {row['entity_id']}: <{url}>")
    lines += [
        "",
        "주소 미발견은 게시물 부재가 아닙니다. 검색 색인은 완전한 목록이 아니며, 이 결과만으로 계정의 게시 빈도나 내용 가치를 평가하지 않습니다.",
        "공식 API 또는 사용 허가를 받은 안정적인 목록 접근 경로가 마련되기 전까지 본문 수집·질문·브리핑·장부에 연결하지 않습니다.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument("--output-dir", type=Path, default=HERE / "output" / "post-index")
    cli.add_argument("--dry-run", action="store_true")
    args = cli.parse_args()
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    errors = validate_registry(data)
    if errors:
        print("\n".join(f"ERROR: {item}" for item in errors))
        return 1
    client_id = "" if args.dry_run else os.environ.get("NAVER_CLIENT_ID", "")
    client_secret = "" if args.dry_run else os.environ.get("NAVER_CLIENT_SECRET", "")
    rows = [probe(entity, client_id, client_secret) for entity in data["entities"]]
    payload = {
        "schema": 1,
        "scope": "SEARCH_INDEX_POST_URL_FEASIBILITY_ONLY",
        "checked_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "source": "NAVER_WEB_INDEX",
        "entities": rows,
        "facebook_profiles_fetched": 0,
        "facebook_posts_fetched": 0,
        "post_bodies_stored": 0,
        "dates_verified": 0,
        "maturity_after": "L0",
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
