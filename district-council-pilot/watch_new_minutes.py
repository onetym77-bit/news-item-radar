#!/usr/bin/env python3
"""Bounded, pre-editorial observation of 25 council recent-list windows.

This is not a full archive or article discovery. A missing overlap is reported
as a possible gap; collection failure never becomes "no new minutes".
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse

from collect_pilot import Client, discover_list, load_recent_tabs, select_rows

BASE = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))
SCHEMA = 1
WINDOW_LIMIT = 20
SEEN_LIMIT = 200


def empty_state():
    return {"schema": SCHEMA, "sources": {}, "last_run": {}}


def load_state(path):
    if not path.is_file():
        return empty_state()
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema") != SCHEMA or not isinstance(state.get("sources"), dict):
        raise ValueError("Unsupported council watch state")
    return state


def record_key(url):
    parsed = urlparse(url)
    identity = parsed.path + "?" + urlencode(sorted(parse_qsl(parsed.query)))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def observe(source, limit=WINDOW_LIMIT):
    client = Client(source)
    listing_url = source["list_url"]
    page = client.get(listing_url)
    fallback = source.get("list_fallback_url")
    if page is None and fallback and not client.stopped and client.logs:
        if "name resolution" in client.logs[-1].get("error", "").lower():
            listing_url = fallback
            page = client.get(listing_url)
    if page is not None and source.get("discover_list_label"):
        discovered = discover_list(page, listing_url, source)
        if discovered:
            listing_url = discovered
            page = client.get(discovered)
    if page is not None and source.get("recent_tabs_api"):
        try:
            page = load_recent_tabs(client, source)
        except (ValueError, TypeError, json.JSONDecodeError):
            page = None
    if page is None:
        return {"id": source["id"], "name": source["name"],
                "status": "UNKNOWN_COLLECTION", "listed": None, "records": []}
    rows, listed = select_rows(page, listing_url, source, limit)
    if not rows or any(not row["url"] for row in rows):
        return {"id": source["id"], "name": source["name"],
                "status": "UNKNOWN_LIST_WINDOW", "listed": listed, "records": []}
    records = [{"key": record_key(row["url"]), "url": row["url"],
                "meeting_date": row["meeting_date"]} for row in rows]
    return {"id": source["id"], "name": source["name"], "status": "OBSERVED",
            "listed": listed, "records": records}


def safe_observe(source):
    try:
        return observe(source)
    except (ValueError, KeyError, TypeError, AttributeError):
        return {"id": source["id"], "name": source["name"],
                "status": "UNKNOWN_LIST_WINDOW", "listed": None, "records": []}


def compare(previous, observations, collected_at):
    if previous.get("schema") != SCHEMA or not isinstance(previous.get("sources"), dict):
        raise ValueError("Unsupported council watch state")
    state = copy.deepcopy(previous)
    state["sources"] = dict(previous["sources"])
    run = {"collected_at_kst": collected_at, "coverage": "FIRST_PAGE_VISIBLE_WINDOW_ONLY",
           "question_output": "NONE", "briefing_output": "NONE",
           "automatic_ledger_write": False, "results": []}
    for item in observations:
        source_id = item["id"]
        prior = state["sources"].get(source_id)
        if item["status"] != "OBSERVED":
            run["results"].append({"id": source_id, "name": item["name"],
                "status": item["status"], "listed": item["listed"],
                "visible": 0, "new_count": None, "candidates": []})
            continue
        records = item["records"]
        if not records or len(records) > WINDOW_LIMIT:
            raise ValueError("Observed window outside bounded contract")
        keys = [row["key"] for row in records]
        if len(keys) != len(set(keys)) or any(not row["url"] for row in records):
            raise ValueError("Duplicate or unresolved council record")
        old_seen = set(prior.get("seen_keys", [])) if prior else set()
        old_window = set(prior.get("window_keys", [])) if prior else set()
        if prior is None:
            status = "BASELINE"
            candidates = []
        else:
            candidates = [row for row in records if row["key"] not in old_seen]
            status = "POSSIBLE_GAP" if not old_window.intersection(keys) else (
                "NEW_IN_VISIBLE_WINDOW" if candidates else "NO_NEW_IN_VISIBLE_WINDOW")
        ordered_seen = list(dict.fromkeys(keys + (prior.get("seen_keys", []) if prior else [])))
        state["sources"][source_id] = {
            "seen_keys": ordered_seen[:SEEN_LIMIT],
            "window_keys": keys,
            "last_successful_at_kst": collected_at,
        }
        run["results"].append({
            "id": source_id, "name": item["name"], "status": status,
            "listed": item["listed"], "visible": len(records),
            "new_count": len(candidates) if prior is not None else None,
            "candidates": candidates,
        })
    state["last_run"] = run
    return state


def render(state):
    run = state["last_run"]
    lines = [
        "# 서울 25개 구의회 얇은 관측", "",
        f"관측 시각: {run['collected_at_kst']}", "",
        "공식 최근목록의 첫 화면만 비교합니다. 회의일은 게시일이 아닙니다.",
        "첫 관측은 신규로 세지 않으며 접속 실패는 자료 0건이 아닙니다.",
        "이전 목록과 겹치지 않으면 POSSIBLE_GAP으로 표시합니다. 이 관측만으로 누락 없는 수집을 보장하지 않습니다.",
        "질문·브리핑·아이템 장부에는 연결하지 않습니다.", "",
        "| 구 | 목록 확인 | 관측 | 확인 범위 내 신규 | 상태 |",
        "|---|---:|---:|---:|---|",
    ]
    for item in run["results"]:
        count = "-" if item["new_count"] is None else str(item["new_count"])
        listed = "-" if item["listed"] is None else str(item["listed"])
        lines.append(f"| {item['name']} | {listed} | {item['visible']} | {count} | {item['status']} |")
    for item in run["results"]:
        if not item["candidates"]:
            continue
        lines.extend(["", f"## {item['name']} · {item['status']}", ""])
        for row in item["candidates"]:
            lines.append(f"- {row['meeting_date'] or '회의일 미확인'} · [공식 회의록]({row['url']})")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", type=Path, default=BASE / "sources_25.json")
    parser.add_argument("--state", type=Path, default=BASE / "output" / "watch" / "state_latest.json")
    parser.add_argument("--output", type=Path, default=BASE / "output" / "watch")
    args = parser.parse_args()
    sources = json.loads(args.sources.read_text(encoding="utf-8"))
    if len(sources) != 25 or len({item["id"] for item in sources}) != 25:
        parser.error("Expected 25 distinct council sources")
    prior = load_state(args.state)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:
        observed = list(pool.map(safe_observe, sources))
    collected_at = datetime.now(KST).isoformat(timespec="seconds")
    state = compare(prior, observed, collected_at)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "state_latest.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "status_latest.md").write_text(render(state), encoding="utf-8")
    print(json.dumps({"status_counts": {
        status: sum(row["status"] == status for row in state["last_run"]["results"])
        for status in sorted({row["status"] for row in state["last_run"]["results"]})
    }}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
