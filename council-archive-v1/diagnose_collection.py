#!/usr/bin/env python3
"""One-pass connectivity diagnostic for all Seoul council minute sources.

This does not change the archive cache and does not call OpenAI. Each council
gets one list request and, when possible, one detail request.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import archive as council_archive

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent


def render(payload):
    lines = [
        "# 서울시·자치구의회 수집 연결 진단",
        "",
        "- OpenAI 호출: 없음",
        f"- 대상 의회: {payload['source_count']}곳",
        f"- 목록 연결 성공: {payload['list_ok_count']}곳",
        f"- 본문 연결 성공: {payload['detail_ok_count']}곳",
        f"- 목록 연결 실패: {payload['list_failed_count']}곳",
        f"- 본문 연결 실패: {payload['detail_failed_count']}곳",
        f"- 목록 0건: {payload['empty_list_count']}곳",
        "",
        "| 의회 | 목록 | 본문 | 최신 표본일 | 진단 |",
        "|---|---:|---:|---|---|",
    ]
    for row in payload["sources"]:
        lines.append(
            f"| {row['source_name']} | "
            f"{'성공' if row['list_ok'] else '실패'} | "
            f"{'성공' if row['detail_ok'] else '-'} | "
            f"{row['latest_meeting_date'] or '-'} | {row['diagnosis']} |"
        )
        if row["error_reason"]:
            lines.append(f"|  |  |  |  | {row['error_reason']} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sources",
        type=Path,
        default=ROOT / "district-council-pilot" / "sources_25.json",
    )
    parser.add_argument("--output", type=Path, default=BASE / "output")
    parser.add_argument("--page-size", type=int, default=10)
    args = parser.parse_args()

    api_key = os.getenv("CLIK_API_KEY", "")
    if not api_key:
        raise ValueError("CLIK_API_KEY is required")

    rows = []
    for source in council_archive.load_sources(args.sources):
        result = {
            "source_id": source["id"],
            "source_name": source["name"],
            "assembly_id": source["clik_assembly_id"],
            "list_ok": False,
            "detail_ok": False,
            "listed_count": 0,
            "latest_meeting_date": "",
            "sample_document_id": "",
            "diagnosis": "",
            "error_type": "",
            "error_reason": "",
        }
        try:
            listed, _total = council_archive.list_page(
                source,
                api_key,
                0,
                args.page_size,
            )
            result["list_ok"] = True
            result["listed_count"] = len(listed)
            if not listed:
                result["diagnosis"] = "목록 0건"
            else:
                sample = listed[0]
                result["latest_meeting_date"] = sample["meeting_date"]
                result["sample_document_id"] = sample["docid"]
                try:
                    council_archive.detail_record(source, sample, api_key)
                    result["detail_ok"] = True
                    result["diagnosis"] = "목록·본문 정상"
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    result["diagnosis"] = "본문 연결 실패"
                    result["error_type"] = type(exc).__name__
                    result["error_reason"] = council_archive.safe_error_reason(exc)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            result["diagnosis"] = "목록 연결 실패"
            result["error_type"] = type(exc).__name__
            result["error_reason"] = council_archive.safe_error_reason(exc)
        rows.append(result)

    payload = {
        "schema": 1,
        "generated_at_kst": datetime.now(council_archive.KST).isoformat(timespec="seconds"),
        "mode": "COUNCIL_COLLECTION_CONNECTIVITY_DIAGNOSTIC",
        "openai_call_count": 0,
        "source_count": len(rows),
        "list_ok_count": sum(row["list_ok"] for row in rows),
        "detail_ok_count": sum(row["detail_ok"] for row in rows),
        "list_failed_count": sum(not row["list_ok"] for row in rows),
        "detail_failed_count": sum(
            row["list_ok"] and row["listed_count"] > 0 and not row["detail_ok"]
            for row in rows
        ),
        "empty_list_count": sum(
            row["list_ok"] and row["listed_count"] == 0 for row in rows
        ),
        "sources": rows,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    council_archive.write_json(
        args.output / "collection_diagnostic_latest.json",
        payload,
    )
    summary = render(payload)
    (args.output / "COLLECTION_DIAGNOSTIC.md").write_text(summary, encoding="utf-8")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write(summary)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
