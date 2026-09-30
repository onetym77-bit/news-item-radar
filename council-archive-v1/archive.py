#!/usr/bin/env python3
"""Keyword-free, resumable archive for Seoul council minutes.

The CLIK portal is used as the broad historical index. Official council pages
remain the freshness check because the portal can lag behind.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
DISTRICT = ROOT / "district-council-pilot"
sys.path.insert(0, str(DISTRICT))

from clik_api import ClikAPIError, fetch_payload, public_document_url  # noqa: E402

KST = timezone(timedelta(hours=9))
DOCID = re.compile(r"CLIKC[0-9]+")
ASSEMBLY_ID = re.compile(r"0020(?:0[1-9]|1[0-9]|2[0-6])")
SEOUL_CITY = {
    "id": "seoul_city",
    "name": "서울시의회",
    "clik_assembly_id": "002001",
    "list_url": "https://ms.smc.seoul.kr/kr/assembly/main.do",
}
STATE_SCHEMA = 1


class TextPage(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.parts = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
        elif not self.skip and tag in {"p", "div", "li", "br", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self.skip:
            self.skip -= 1
        elif not self.skip and tag in {"p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

    def text(self):
        rows = [re.sub(r"\s+", " ", row).strip() for row in "".join(self.parts).splitlines()]
        return "\n".join(row for row in rows if row)


def read_json(path, default=None):
    if not path or not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def safe_error_reason(exc):
    text = re.sub(r"https?://\\S+", "[URL]", compact_error(exc))
    text = re.sub(
        r"(?i)(api[_-]?key|token|secret|serviceKey)=([^&\\s]+)",
        r"\\1=[REDACTED]",
        text,
    )
    return text[:180] or type(exc).__name__


def compact_error(exc):
    return re.sub(r"\\s+", " ", str(exc or "")).strip()


def error_summary(errors):
    groups = {}
    for row in errors:
        key = (row["stage"], row["error_type"], row.get("reason", ""))
        group = groups.setdefault(key, {"count": 0, "sources": set()})
        group["count"] += 1
        group["sources"].add(row["source_id"])
    return [
        {
            "stage": stage,
            "error_type": error_type,
            "reason": reason,
            "count": group["count"],
            "source_count": len(group["sources"]),
        }
        for (stage, error_type, reason), group in sorted(groups.items())
    ]


def parse_meeting_date(value):
    text = str(value or "")
    if not re.fullmatch(r"20[0-9]{6}", text):
        return ""
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:])).isoformat()
    except ValueError:
        return ""


def load_sources(path):
    rows = read_json(path, [])
    if not isinstance(rows, list) or len(rows) != 25:
        raise ValueError("Expected 25 Seoul district council sources")
    sources = [SEOUL_CITY, *rows]
    ids = [row.get("clik_assembly_id") for row in sources]
    if len(set(ids)) != 26 or any(not ASSEMBLY_ID.fullmatch(str(value or "")) for value in ids):
        raise ValueError("Expected 26 unique Seoul council assembly IDs")
    return sources


def list_page(source, api_key, start_count, list_count):
    payload = fetch_payload(
        api_key,
        displayType="list",
        startCount=start_count,
        listCount=list_count,
        searchType="ALL",
        rasmblyId=source["clik_assembly_id"],
        sort="MTG_DE/DESC",
    )
    entries = payload.get("LIST") or []
    if not isinstance(entries, list):
        raise ClikAPIError("CLIK list rows are not an array")
    rows = []
    seen = set()
    for entry in entries:
        row = entry.get("ROW") if isinstance(entry, dict) else None
        if not isinstance(row, dict):
            raise ClikAPIError("CLIK list row schema is invalid")
        docid = str(row.get("DOCID") or "")
        meeting_date = parse_meeting_date(row.get("MTG_DE"))
        if (
            not DOCID.fullmatch(docid)
            or row.get("RASMBLY_ID") != source["clik_assembly_id"]
            or not meeting_date
        ):
            raise ClikAPIError("CLIK list row identity mismatch")
        if docid in seen:
            continue
        seen.add(docid)
        rows.append({
            "docid": docid,
            "meeting_date": meeting_date,
            "label": (
                f"제{row.get('RASMBLY_NUMPR') or ''}대 "
                f"제{row.get('RASMBLY_SESN') or ''}회 "
                f"{row.get('MTGNM') or '회의록'} 제{row.get('MINTS_ODR') or '0'}차"
            ),
            "url": public_document_url(docid),
        })
    try:
        total = int(payload.get("TOTAL_COUNT"))
    except (TypeError, ValueError):
        total = start_count + len(rows)
    return rows, max(total, 0)


def detail_record(source, item, api_key):
    payload = fetch_payload(api_key, displayType="detail", docid=item["docid"])
    if (
        payload.get("DOCID") != item["docid"]
        or payload.get("RASMBLY_ID") != source["clik_assembly_id"]
    ):
        raise ClikAPIError("CLIK detail identity mismatch")
    meeting_date = parse_meeting_date(payload.get("MTG_DE"))
    if meeting_date != item["meeting_date"]:
        raise ClikAPIError("CLIK detail date mismatch")
    html = payload.get("MINTS_HTML")
    if not isinstance(html, str):
        raise ClikAPIError("CLIK detail body is missing")
    body = TextPage(html).text()
    if len(body) < 80:
        raise ClikAPIError("CLIK detail transcript is too short")
    return {
        "schema": 1,
        "document_id": item["docid"],
        "source_id": source["id"],
        "source_name": source["name"],
        "assembly_id": source["clik_assembly_id"],
        "meeting_date": meeting_date,
        "title": item["label"],
        "document_url": item["url"],
        "official_list_url": source["list_url"],
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "body": body,
        "captured_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
    }


def empty_state(lookback_months):
    return {
        "schema": STATE_SCHEMA,
        "lookback_months": lookback_months,
        "documents": {},
        "sources": {},
        "updated_at_kst": "",
    }


def normalize_state(value, sources, lookback_months):
    if not isinstance(value, dict) or value.get("schema") != STATE_SCHEMA:
        value = empty_state(lookback_months)
    value.setdefault("documents", {})
    value.setdefault("sources", {})
    old_window = int(value.get("lookback_months") or 0)
    if lookback_months > old_window:
        for source_state in value["sources"].values():
            source_state.update({
                "next_start_count": 0,
                "complete": False,
                "finish_after_pending": False,
                "pending": [],
            })
    value["lookback_months"] = max(old_window, lookback_months)
    for source in sources:
        value["sources"].setdefault(source["id"], {
            "next_start_count": 0,
            "complete": False,
            "finish_after_pending": False,
            "pending": [],
            "portal_total": None,
            "portal_latest_date": "",
            "official_latest_date": "",
            "freshness": "NOT_CHECKED",
            "archived_count": 0,
            "failed_documents": [],
        })
    return value


def official_latest_map(path):
    payload = read_json(path, {})
    result = {}
    for source in payload.get("sources", []) if isinstance(payload, dict) else []:
        dates = [
            str(row.get("meeting_date") or "")
            for row in source.get("selected", [])
            if isinstance(row, dict)
        ]
        result[str(source.get("id") or "")] = max((value for value in dates if value), default="")
    return result


def append_jsonl_gzip(path, rows):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "at", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def archive(
    sources,
    *,
    api_key,
    state,
    archive_path,
    new_path,
    cutoff,
    max_documents,
    page_size,
    official_dates,
):
    added = []
    errors = []
    attempted_documents = set()
    attempted_pages = set()
    source_by_id = {source["id"]: source for source in sources}

    while len(added) < max_documents:
        progress = False
        for source in sources:
            if len(added) >= max_documents:
                break
            source_state = state["sources"][source["id"]]
            pending = source_state["pending"]

            if not pending and source_state.get("finish_after_pending"):
                source_state["complete"] = True
                source_state["finish_after_pending"] = False

            if not pending and not source_state["complete"] and source["id"] not in attempted_pages:
                attempted_pages.add(source["id"])
                start = int(source_state["next_start_count"])
                try:
                    rows, total = list_page(source, api_key, start, page_size)
                    source_state["portal_total"] = total
                    if start == 0 and rows:
                        source_state["portal_latest_date"] = rows[0]["meeting_date"]
                    in_window = [
                        row for row in rows
                        if date.fromisoformat(row["meeting_date"]) >= cutoff
                        and row["docid"] not in state["documents"]
                    ]
                    pending.extend(in_window)
                    source_state["next_start_count"] = start + len(rows)
                    older_seen = any(date.fromisoformat(row["meeting_date"]) < cutoff for row in rows)
                    exhausted = not rows or source_state["next_start_count"] >= total
                    if older_seen or exhausted:
                        source_state["finish_after_pending"] = True
                    progress = True
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    errors.append({
                        "source_id": source["id"],
                        "stage": "list",
                        "error_type": type(exc).__name__,
                        "reason": safe_error_reason(exc),
                    })

            candidate = next(
                (row for row in pending if row["docid"] not in attempted_documents),
                None,
            )
            if candidate is None:
                continue
            attempted_documents.add(candidate["docid"])
            try:
                record = detail_record(source, candidate, api_key)
                pending.remove(candidate)
                state["documents"][record["document_id"]] = {
                    key: record[key]
                    for key in (
                        "source_id", "source_name", "assembly_id", "meeting_date",
                        "title", "document_url", "body_sha256", "captured_at_kst",
                    )
                }
                source_state["archived_count"] = int(source_state.get("archived_count") or 0) + 1
                added.append(record)
                progress = True
            except (OSError, ValueError, KeyError, TypeError) as exc:
                candidate["attempts"] = int(candidate.get("attempts") or 0) + 1
                errors.append({
                    "source_id": source["id"],
                    "document_id": candidate["docid"],
                    "stage": "detail",
                    "error_type": type(exc).__name__,
                    "reason": safe_error_reason(exc),
                    "attempt": candidate["attempts"],
                })
                if candidate["attempts"] >= 3:
                    pending.remove(candidate)
                    source_state["failed_documents"].append({
                        "document_id": candidate["docid"],
                        "meeting_date": candidate["meeting_date"],
                        "official_fallback_required": True,
                    })
                    progress = True

        attempted_pages.clear()
        if not progress:
            break

    append_jsonl_gzip(archive_path, added)
    if new_path.exists():
        new_path.unlink()
    append_jsonl_gzip(new_path, added)

    for source_id, source_state in state["sources"].items():
        official_latest = official_dates.get(source_id, "")
        source_state["official_latest_date"] = official_latest
        portal_latest = source_state.get("portal_latest_date") or ""
        if official_latest and portal_latest and official_latest > portal_latest:
            source_state["freshness"] = "PORTAL_STALE_USE_OFFICIAL"
        elif official_latest and portal_latest:
            source_state["freshness"] = "CURRENT_AS_CHECKED"
        elif source_id == "seoul_city":
            source_state["freshness"] = "CITY_OFFICIAL_PATH_SEPARATE"
        else:
            source_state["freshness"] = "OFFICIAL_CHECK_INCOMPLETE"

    state["updated_at_kst"] = datetime.now(KST).isoformat(timespec="seconds")
    return added, errors


def status_payload(state, sources, added, errors, cutoff):
    rows = []
    for source in sources:
        item = state["sources"][source["id"]]
        rows.append({
            "source_id": source["id"],
            "source_name": source["name"],
            "assembly_id": source["clik_assembly_id"],
            "archived_count": item["archived_count"],
            "pending_count": len(item["pending"]),
            "complete_for_window": bool(item["complete"]),
            "portal_total": item["portal_total"],
            "portal_latest_date": item["portal_latest_date"],
            "official_latest_date": item["official_latest_date"],
            "freshness": item["freshness"],
            "failed_document_count": len(item["failed_documents"]),
        })
    return {
        "schema": 1,
        "generated_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "mode": "KEYWORD_FREE_FULL_MINUTES_ARCHIVE",
        "cutoff_date": cutoff.isoformat(),
        "source_count": len(rows),
        "archived_total": len(state["documents"]),
        "added_this_run": len(added),
        "complete_source_count": sum(row["complete_for_window"] for row in rows),
        "error_count": len(errors),
        "error_summary": error_summary(errors),
        "all_minutes_are_read_before_issue_selection": True,
        "silence_is_not_resolution": True,
        "sources": rows,
        "errors": errors,
    }


def render_status(payload):
    lines = [
        "# 서울시·자치구의회 회의록 전량 아카이브",
        "",
        f"- 수집 방식: 키워드 없이 회의록 목록 전체 순회",
        f"- 대상: {payload['source_count']}곳",
        f"- 기준일: {payload['cutoff_date']} 이후",
        f"- 누적 아카이브: {payload['archived_total']}건",
        f"- 이번 실행 추가: {payload['added_this_run']}건",
        f"- 범위 완료: {payload['complete_source_count']}/{payload['source_count']}곳",
        f"- 오류: {payload['error_count']}건 (0건으로 해석하지 않음)",
    ]
    for row in payload["error_summary"]:
        lines.append(
            f"  - {row['stage']} · {row['reason'] or row['error_type']}: "
            f"{row['count']}건 / {row['source_count']}개 소스"
        )
    lines.extend([
        "",
        "> 지방의정포털은 역사 자료의 공통 색인으로 사용합니다. "
        "공식 의회 페이지가 더 최신이면 해당 의회는 기존 공식 경로를 우선합니다.",
        "",
        "| 의회 | 누적 | 대기 | 범위 완료 | 최신성 판정 |",
        "|---|---:|---:|---|---|",
    ])
    for row in payload["sources"]:
        lines.append(
            f"| {row['source_name']} | {row['archived_count']} | {row['pending_count']} | "
            f"{'완료' if row['complete_for_window'] else '진행 중'} | {row['freshness']} |"
        )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", type=Path, default=DISTRICT / "sources_25.json")
    parser.add_argument("--runtime", type=Path, default=ROOT / ".runtime" / "council-archive")
    parser.add_argument("--output", type=Path, default=BASE / "output")
    parser.add_argument("--official-observation", type=Path)
    parser.add_argument("--lookback-months", type=int, choices=(24, 36, 60), default=36)
    parser.add_argument("--max-documents", type=int, choices=(26, 52, 104, 208), default=104)
    parser.add_argument("--page-size", type=int, choices=(10, 20, 50, 100), default=50)
    args = parser.parse_args()

    api_key = os.getenv("CLIK_API_KEY", "")
    if not api_key:
        raise ValueError("CLIK_API_KEY is required")

    sources = load_sources(args.sources)
    args.runtime.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    state_path = args.runtime / "state.json"
    state = normalize_state(read_json(state_path), sources, args.lookback_months)
    cutoff = datetime.now(KST).date() - timedelta(days=args.lookback_months * 31)

    added, errors = archive(
        sources,
        api_key=api_key,
        state=state,
        archive_path=args.runtime / "documents.jsonl.gz",
        new_path=args.output / "new_documents.jsonl.gz",
        cutoff=cutoff,
        max_documents=args.max_documents,
        page_size=args.page_size,
        official_dates=official_latest_map(args.official_observation),
    )
    write_json(state_path, state)
    payload = status_payload(state, sources, added, errors, cutoff)
    write_json(args.output / "status_latest.json", payload)
    (args.output / "SUMMARY.md").write_text(render_status(payload), encoding="utf-8")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write(render_status(payload))
    print(json.dumps({
        "archived_total": payload["archived_total"],
        "added_this_run": payload["added_this_run"],
        "complete_source_count": payload["complete_source_count"],
        "error_count": payload["error_count"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
