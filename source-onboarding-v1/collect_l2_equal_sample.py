#!/usr/bin/env python3
"""Compare Seoul audit results and citizen proposals on one bounded L2 basis.

Both adapters inspect the first five unique records from one official list page,
fetch the official detail page, and persist derived metadata only. Attachments,
full body text, author names, contacts, questions, and editorial judgements are
not stored.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
sys.path.insert(0, str(BASE))

from collect_audit_l2 import collect_one as collect_audit
from source_batch_scorecard import build_scorecard, render_summary as render_scorecard
from thin_source_contract import load_registry, validate_thin_observation

SAMPLE_SIZE = 5
SOURCE_IDS = ("seoul_audit_results", "citizen_proposals")
BODY_AVAILABLE = {"BOUNDED_TEXT", "STRUCTURED"}


def now_kst() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_citizen_module():
    path = ROOT / "citizen-proposal-pilot" / "watch.py"
    spec = importlib.util.spec_from_file_location("citizen_proposal_watch_l2", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("citizen proposal adapter unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fallback_fingerprint(record_id: str, title: str, url: str) -> str:
    return hashlib.sha256("\x1f".join((record_id, title, url)).encode("utf-8")).hexdigest()


def collect_citizen(source: dict, observed_at: str, *, module=None, fetcher=None) -> dict:
    module = module or load_citizen_module()
    fetcher = fetcher or module.fetch
    source_url = source["official_url"]
    try:
        listing_html, listing_hash = fetcher(source_url)
        proposals = module.parse_list(listing_html, limit=SAMPLE_SIZE)
    except Exception as exc:
        return {
            "schema": 1,
            "source_id": source["source_id"],
            "maturity": source["maturity"],
            "collected_at_kst": observed_at,
            "source_url": source_url,
            "access_status": "FAILED",
            "coverage": "FIRST_OFFICIAL_LIST_PAGE_FIRST_5_DETAILS_NO_ATTACHMENTS",
            "records": [],
            "interpretation_status": "NOT_EVALUATED",
            "diagnostics": {
                "listing_error_code": type(exc).__name__,
                "detail_requested": 0,
                "detail_success": 0,
                "detail_partial": 0,
                "detail_failed": 0,
            },
        }

    records = []
    statuses = []
    for proposal in proposals[:SAMPLE_SIZE]:
        record_id = str(proposal["proposal_id"])
        title = str(proposal["title"])
        detail_url = str(proposal["source_url"])
        published_at = proposal.get("posted_date")
        base = {
            "source_record_id": record_id,
            "title": title,
            "detail_url": detail_url,
            "published_at": published_at,
            "published_at_status": "CANDIDATE" if published_at else "UNKNOWN",
            "observed_at_kst": observed_at,
        }
        try:
            detail_html, detail_hash = fetcher(detail_url)
            detail_text = module.relevant_detail_text(detail_html, title)
        except Exception as exc:
            records.append({
                **base,
                "access_status": "FAILED",
                "body_status": "FAILED",
                "content_fingerprint": fallback_fingerprint(record_id, title, detail_url),
                "title_match": "NOT_EVALUATED",
                "article_text_chars_observed": 0,
                "detail_error_code": type(exc).__name__,
            })
            statuses.append("FAILED")
            continue
        if detail_text is None:
            records.append({
                **base,
                "access_status": "PARTIAL",
                "body_status": "FAILED",
                "content_fingerprint": detail_hash or fallback_fingerprint(record_id, title, detail_url),
                "title_match": "MISMATCH",
                "article_text_chars_observed": 0,
            })
            statuses.append("PARTIAL")
            continue
        records.append({
            **base,
            "access_status": "SUCCESS",
            "body_status": "BOUNDED_TEXT",
            "content_fingerprint": detail_hash or fallback_fingerprint(record_id, title, detail_url),
            "title_match": "TITLE_ANCHORED",
            "article_text_chars_observed": len(detail_text),
        })
        statuses.append("SUCCESS")

    access_status = (
        "SUCCESS"
        if records and all(status == "SUCCESS" for status in statuses)
        else "PARTIAL"
        if records
        else "FAILED"
    )
    return {
        "schema": 1,
        "source_id": source["source_id"],
        "maturity": source["maturity"],
        "collected_at_kst": observed_at,
        "source_url": source_url,
        "access_status": access_status,
        "coverage": "FIRST_OFFICIAL_LIST_PAGE_FIRST_5_DETAILS_NO_ATTACHMENTS",
        "records": records,
        "interpretation_status": "NOT_EVALUATED",
        "diagnostics": {
            "listing_error_code": None,
            "list_sha256": listing_hash,
            "detail_requested": len(records),
            "detail_success": statuses.count("SUCCESS"),
            "detail_partial": statuses.count("PARTIAL"),
            "detail_failed": statuses.count("FAILED"),
            "attachment_downloads": 0,
        },
    }


def common_metrics(observation: dict) -> dict:
    records = observation["records"]
    available = [row for row in records if row.get("body_status") in BODY_AVAILABLE]
    aligned = [
        row for row in records
        if row.get("title_match") in {"EXACT", "NORMALIZED", "TITLE_ANCHORED"}
    ]
    lengths = [
        int(row.get("article_text_chars_observed") or 0)
        for row in available
        if int(row.get("article_text_chars_observed") or 0) > 0
    ]
    unique = {
        row.get("content_fingerprint")
        for row in records
        if row.get("content_fingerprint")
    }
    attachment_links = sum(
        int(row.get("attachment_link_count_not_fetched") or 0) for row in records
    )
    substantive_scope = (
        "ATTACHMENT_REQUIRED_FOR_FINDINGS"
        if observation["source_id"] == "seoul_audit_results" and attachment_links
        else "DETAIL_PAGE_BODY"
        if observation["source_id"] == "citizen_proposals"
        else "DETAIL_PAGE_TEXT_ONLY"
    )
    return {
        "source_id": observation["source_id"],
        "sample_target": SAMPLE_SIZE,
        "sample_count": len(records),
        "detail_success_count": sum(row.get("access_status") == "SUCCESS" for row in records),
        "title_aligned_count": len(aligned),
        "detail_text_available_count": len(available),
        "verified_date_count": sum(row.get("published_at_status") == "VERIFIED" for row in records),
        "unique_content_count": len(unique),
        "median_detail_text_chars_observed": int(statistics.median(lengths)) if lengths else None,
        "attachment_links_not_fetched": attachment_links,
        "substantive_body_scope": substantive_scope,
        "editorial_value_status": "HUMAN_REVIEW_REQUIRED",
    }


def render_equal_summary(observations: list[dict], scorecard: dict) -> str:
    metrics = [common_metrics(row) for row in observations]
    labels = {
        "seoul_audit_results": "서울시 감사 결과",
        "citizen_proposals": "상상대로 서울 시민제안",
    }
    lines = [
        "# 감사 결과·시민제안 동일 L2 본문 표본 비교",
        "",
        "두 소스 모두 공식 목록 상단의 고유 항목 5건과 각 공식 상세 화면만 읽었습니다. 첨부파일, 원문 전체, 작성자명·연락처, 질문·기사 판정은 저장하지 않았습니다.",
        "",
        "| 소스 | 목표/확보 | 상세 성공 | 제목 대응 | 상세 텍스트 확인 | 날짜 검증 | 실질 본문 위치 | 상세 텍스트 길이 중앙값 |",
        "|---|---:|---:|---:|---:|---:|---|---:|",
    ]
    for row in metrics:
        lines.append(
            f"| {labels.get(row['source_id'], row['source_id'])} | "
            f"{row['sample_target']}/{row['sample_count']} | "
            f"{row['detail_success_count']} | {row['title_aligned_count']} | "
            f"{row['detail_text_available_count']} | {row['verified_date_count']} | "
            f"{row['substantive_body_scope']} | "
            f"{row['median_detail_text_chars_observed'] if row['median_detail_text_chars_observed'] is not None else '-'} |"
        )
    lines.extend([
        "",
        "## 이 표가 말하는 것",
        "",
        "- 같은 분모와 상세 접근 기준에서 텍스트 추출 가능성을 비교합니다. 상세 텍스트는 핵심 사실이 담긴 실질 본문과 다를 수 있습니다.",
        "- 날짜 검증은 상세 본문 가치가 아니라 게시일 확정 품질입니다. 시민제안의 목록 날짜는 이번 단계에서 후보값입니다.",
        "- 감사 결과의 핵심 내용이 첨부 PDF에만 있으면 이번 비교에서는 첨부 의존으로 남습니다. 시민제안의 제목 고정 텍스트도 메뉴·부가정보를 포함할 수 있습니다.",
        "",
        "## 아직 말할 수 없는 것",
        "",
        "- 어느 소스가 더 좋은 기획 아이템을 많이 내는지는 자동 판정하지 않습니다.",
        "- 유효 단서율은 두 소스 각 5건을 같은 라벨(PROMISING, VERIFY, NOISE, DUPLICATE, UNREADABLE)로 사람이 검토한 뒤 계산해야 합니다.",
        "- 게시 주기가 다른 두 소스이므로 목록 상단 5건은 같은 날짜 범위의 표본이 아닙니다.",
        "",
        "## 표본 목록: 원문 확인용",
        "",
    ])
    for observation in observations:
        lines.append(f"### {labels.get(observation['source_id'], observation['source_id'])}")
        lines.append("")
        for row in observation["records"]:
            lines.append(
                f"- {row.get('published_at') or '날짜 미확인'} · "
                f"[{row['title']}]({row['detail_url']}) · "
                f"상세 {row.get('access_status')} · 텍스트 {row.get('body_status')}"
            )
        lines.append("")
    lines.extend([
        "## 공통 판정",
        "",
        "- 두 소스 모두 5건의 상세 화면까지 안정적으로 도달했습니다.",
        "- 감사 결과는 실질 지적 내용이 첨부 공개문에 있어 첨부 확인 전 편집 표본으로 간주할 수 없습니다.",
        "- 시민제안은 상세 화면에서 제안문을 읽을 수 있지만, 게시일 확정과 사실 검증은 별도입니다.",
    ])
    return "\n".join(lines)


def write_review_queue(observations: list[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "source_id", "source_record_id", "title", "detail_url",
            "published_at", "body_available", "review_label", "review_note",
        ])
        writer.writeheader()
        for observation in observations:
            for row in observation["records"]:
                writer.writerow({
                    "source_id": observation["source_id"],
                    "source_record_id": row["source_record_id"],
                    "title": row["title"],
                    "detail_url": row["detail_url"],
                    "published_at": row.get("published_at") or "",
                    "body_available": row.get("body_status") in BODY_AVAILABLE,
                    "review_label": "",
                    "review_note": "",
                })


def collect(registry: dict, observed_at: str, *, audit_collector=collect_audit, citizen_collector=collect_citizen) -> list[dict]:
    sources = {row["source_id"]: row for row in registry["sources"]}
    observations = [
        audit_collector(sources["seoul_audit_results"], observed_at),
        citizen_collector(sources["citizen_proposals"], observed_at),
    ]
    for observation in observations:
        errors = validate_thin_observation(observation, registry)
        if errors:
            raise RuntimeError(f"{observation['source_id']}: " + "; ".join(errors))
    return observations


def run(output_dir: Path) -> dict:
    registry = load_registry()
    observed_at = now_kst()
    observations = collect(registry, observed_at)
    scorecard = build_scorecard(observations, registry, [])
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle = {
        "schema": 1,
        "probe": "EQUAL_L2_BODY_SAMPLE",
        "sample_size_per_source": SAMPLE_SIZE,
        "collected_at_kst": observed_at,
        "observations": observations,
        "common_metrics": [common_metrics(row) for row in observations],
        "editorial_value_status": "HUMAN_REVIEW_REQUIRED",
    }
    (output_dir / "observations.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "source_scorecard.json").write_text(
        json.dumps(scorecard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_review_queue(observations, output_dir / "human_review_queue.csv")
    summary = render_equal_summary(observations, scorecard)
    (output_dir / "SUMMARY.md").write_text(summary, encoding="utf-8")
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BASE / "output" / "l2-equal-sample",
    )
    args = parser.parse_args()
    result = run(args.output_dir)
    print(render_equal_summary(
        result["observations"],
        build_scorecard(result["observations"], load_registry(), []),
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
