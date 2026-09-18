#!/usr/bin/env python3
"""Read-only, bounded Atom-feed trial for channels linked by official homepages."""
from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from verify_registry import REGISTRY, safe_https

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "youtube_feed_trial.json"
ATOM = "{http://www.w3.org/2005/Atom}"
YT = "{http://www.youtube.com/xml/schemas/2015}"
KST = timezone(timedelta(hours=9))
CHANNEL_ID = re.compile(r"UC[A-Za-z0-9_-]{22}\Z")
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")
MAX_BYTES = 600_000
MAX_ITEMS = 20
TIMEOUT = 12


def validate_config(config: dict, registry: dict) -> list[str]:
    errors = []
    rows = config.get("channels")
    if config.get("schema") != 1 or not isinstance(rows, list) or not 1 <= len(rows) <= 20:
        return ["channel config needs 1-20 rows"]
    entities = {entity["id"]: entity for entity in registry["entities"]}
    seen_entity = set()
    seen_channel = set()
    for row in rows:
        entity_id = row.get("entity_id")
        channel_id = row.get("channel_id", "")
        if entity_id not in entities or entity_id in seen_entity:
            errors.append(f"{entity_id}: unknown or repeated entity")
        if not CHANNEL_ID.fullmatch(channel_id) or channel_id in seen_channel:
            errors.append(f"{entity_id}: invalid or repeated channel ID")
        seen_entity.add(entity_id)
        seen_channel.add(channel_id)
        if row.get("channel_url") != f"https://www.youtube.com/channel/{channel_id}":
            errors.append(f"{entity_id}: channel URL must match ID")
        if row.get("source_status") != "OFFICIAL_HOMEPAGE_LINK_CANDIDATE":
            errors.append(f"{entity_id}: source is still an L0 candidate")
        evidence = row.get("evidence_page", "")
        expected_site = entities.get(entity_id, {}).get("official_site", "")
        if not safe_https(evidence) or not safe_https(expected_site):
            errors.append(f"{entity_id}: missing safe HTTPS evidence")
        elif (urlsplit(evidence).hostname or "").removeprefix("www.") != (urlsplit(expected_site).hostname or "").removeprefix("www."):
            errors.append(f"{entity_id}: evidence is not on registered official site")
    return errors


def parse_feed(xml: bytes, channel_id: str) -> tuple[str, list[dict], int]:
    if b"<!DOCTYPE" in xml.upper() or len(xml) > MAX_BYTES:
        return "INVALID_XML", [], 0
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return "INVALID_XML", [], 0
    if root.tag != f"{ATOM}feed":
        return "INVALID_FEED", [], 0
    self_links = [node.get("href", "") for node in root.findall(f"{ATOM}link") if node.get("rel") == "self"]
    if not any(parse_qs(urlsplit(link).query).get("channel_id") == [channel_id] for link in self_links):
        return "CHANNEL_MISMATCH", [], 0
    items = []
    invalid_entries = 0
    seen = set()
    for entry in root.findall(f"{ATOM}entry")[:MAX_ITEMS]:
        video_id = entry.findtext(f"{YT}videoId", default="")
        entry_channel = entry.findtext(f"{YT}channelId", default="")
        title = (entry.findtext(f"{ATOM}title", default="") or "").strip()
        published = entry.findtext(f"{ATOM}published", default="")
        try:
            date = datetime.fromisoformat(published.replace("Z", "+00:00"))
            valid_date = date.tzinfo is not None
        except ValueError:
            valid_date = False
        if entry_channel != channel_id or not VIDEO_ID.fullmatch(video_id) or not title or not valid_date:
            invalid_entries += 1
            continue
        if video_id in seen:
            invalid_entries += 1
            continue
        seen.add(video_id)
        items.append({
            "source_id": "official_sns_network",
            "entity_id": None,
            "source_video_id": video_id,
            "title": title[:180],
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "published_at": published,
            "date_status": "VERIFIED_FEED_VALUE",
            "account_status": "OFFICIAL_HOMEPAGE_LINK_CANDIDATE",
        })
    status = "PARTIAL_INVALID_ENTRIES" if invalid_entries else ("SUCCESS_WITH_ITEMS" if items else "SUCCESS_EMPTY_FEED")
    return status, items, invalid_entries


def fetch_one(row: dict) -> dict:
    channel_id = row["channel_id"]
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    result = {
        "entity_id": row["entity_id"],
        "channel_id": channel_id,
        "channel_url": row["channel_url"],
        "evidence_page": row["evidence_page"],
        "feed_url": feed_url,
        "status": "NOT_ATTEMPTED",
        "invalid_entries": 0,
        "items": [],
    }
    try:
        request = Request(feed_url, headers={
            "User-Agent": "news-item-radar-social-l1-trial/1.0",
            "Accept": "application/atom+xml,application/xml,text/xml",
        })
        with urlopen(request, timeout=TIMEOUT) as response:
            final = urlsplit(response.geturl())
            if final.scheme != "https" or final.hostname not in {"www.youtube.com", "youtube.com"} or final.path != "/feeds/videos.xml" or parse_qs(final.query).get("channel_id") != [channel_id]:
                result["status"] = "UNEXPECTED_REDIRECT"
                return result
            if response.headers.get_content_type() not in {"application/atom+xml", "application/xml", "text/xml"}:
                result["status"] = "UNEXPECTED_CONTENT_TYPE"
                return result
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                result["status"] = "OVERSIZE_FEED"
                return result
            status, items, invalid = parse_feed(raw, channel_id)
            for item in items:
                item["entity_id"] = row["entity_id"]
            result.update(status=status, items=items, invalid_entries=invalid)
            return result
    except HTTPError as exc:
        result["status"] = f"HTTP_{exc.code}"
    except (URLError, OSError, TimeoutError, ValueError):
        result["status"] = "ACCESS_ERROR"
    return result


def render(payload: dict) -> str:
    rows = payload["channels"]
    lines = [
        "# 공식 홈페이지 연결 유튜브 8곳 영상 목록 L1 시험",
        "",
        "공식 홈페이지가 링크한 채널 ID의 공개 Atom 피드에서 영상 제목·게시일·고유주소만 읽었습니다. 링크 후보의 기관 주체와 편집 가치는 별도 확인이 필요합니다.",
        f"- 시험 채널: {len(rows)}곳",
        f"- 피드에서 읽은 영상: {sum(len(row['items']) for row in rows)}건 (채널당 최대 {MAX_ITEMS}건)",
        "- 본문·설명·댓글 수집: 0건; 질문·브리핑·장부 연결: 없음",
        "- 소스 성숙도: L0 유지 (이번 L1 시험은 자동 승격 아님)",
        "",
        "| 기관 | 피드 상태 | 영상 수 | 유효하지 않은 항목 |",
        "|---|---|---:|---:|",
    ]
    for row in rows:
        lines.append(f"| {row['entity_id']} | {row['status']} | {len(row['items'])} | {row['invalid_entries']} |")
    lines += ["", "## 채널별 최근 표본 (제목은 출처 메타데이터)", ""]
    for row in rows:
        for item in row["items"][:2]:
            title = item["title"].replace("|", " ").replace("\n", " ").replace("\r", " ").replace("<", "‹").replace(">", "›")
            lines.append(f"- {row['entity_id']}: {item['published_at']} · [{title}]({item['url']})")
    lines += [
        "",
        "접속 실패·빈 피드는 영상 부재나 채널 비활동으로 확정하지 않습니다. 제목만으로 시민 피해·사실관계·아이템 가치를 판정하지 않습니다.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument("--output-dir", type=Path, default=HERE / "output" / "youtube-feed-trial")
    cli.add_argument("--dry-run", action="store_true")
    args = cli.parse_args()
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    errors = validate_config(config, registry)
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors))
        return 1
    if args.dry_run:
        rows = [{
            "entity_id": row["entity_id"], "channel_id": row["channel_id"],
            "channel_url": row["channel_url"], "evidence_page": row["evidence_page"],
            "feed_url": f"https://www.youtube.com/feeds/videos.xml?channel_id={row['channel_id']}",
            "status": "NOT_ATTEMPTED", "invalid_entries": 0, "items": [],
        } for row in config["channels"]]
    else:
        with ThreadPoolExecutor(max_workers=4) as pool:
            rows = list(pool.map(fetch_one, config["channels"]))
    payload = {
        "schema": 1,
        "scope": "L1_ATOM_FEED_METADATA_TRIAL_ONLY",
        "checked_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "channels": rows,
        "post_bodies_stored": 0,
        "comments_stored": 0,
        "questions_generated": 0,
        "briefing_connected": False,
        "maturity_after": "L0",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = render(payload)
    (args.output_dir / "SUMMARY.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
