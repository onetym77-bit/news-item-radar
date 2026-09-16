#!/usr/bin/env python3
"""Bounded L2 body-structure sample for Seoul audit result pages.

The collector fetches at most five official detail pages. It keeps listing
metadata plus derived structure flags and hashes only. It never downloads
attachments or persists article sentences, contacts, names, questions, or
briefing content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from collect_l1_batch import clean_text, fetch_html, parse_audit
from thin_source_contract import load_registry, validate_thin_observation

SOURCE_ID = "seoul_audit_results"
MAX_DETAIL_RECORDS = 5
DATE_RE = re.compile(r"(?<!\d)(20\d{2})[-./]\s*(\d{1,2})[-./]\s*(\d{1,2})(?!\d)")
STOP_TOKENS = ("추천하기", "페이지 만족도", "이 페이지에서 제공하는 정보")
STRUCTURE_PATTERNS = {
    "audit_background": (r"감사\s*배경", r"감사\s*목적"),
    "audit_subject": (r"감사\s*대상", r"대상\s*기관"),
    "audit_period_scope": (r"감사\s*기간", r"감사\s*범위", r"기간\s*[·ㆍ/]\s*범위"),
    "audit_focus": (r"감사\s*중점", r"중점\s*사항"),
    "finding_or_disposition": (
        r"감사\s*결과", r"지적\s*사항", r"처분\s*요구",
        r"시정\s*요구", r"개선\s*요구",
    ),
    "financial_measure": (r"재정상", r"회수", r"추징", r"감액", r"변상"),
    "followup_status": (r"이행\s*실태", r"조치\s*결과", r"이행\s*결과"),
}


def now_kst() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalized_title(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", clean_text(value)).casefold()


def first_date(value: str) -> str | None:
    match = DATE_RE.search(value)
    if not match:
        return None
    year, month, day = map(int, match.groups())
    try:
        datetime(year, month, day)
    except ValueError:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


class DetailParser(HTMLParser):
    """Hold page text in memory only long enough to derive non-personal signals."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tokens: list[str] = []
        self.heading_candidates: list[str] = []
        self._ignored_depth = 0
        self._heading_parts: list[str] | None = None
        self.meta_titles: list[str] = []
        self.links: list[tuple[int, str]] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "template"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        attr_map = {str(k).lower(): str(v or "") for k, v in attrs}
        if tag == "meta" and attr_map.get("property", "").lower() in {"og:title", "twitter:title"}:
            value = clean_text(attr_map.get("content", ""))
            if value:
                self.meta_titles.append(value)
        if tag in {"h1", "h2", "h3"}:
            self._heading_parts = []
        if tag == "a":
            self.links.append((len(self.tokens), attr_map.get("href", "")))

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "template"}:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return
        if not self._ignored_depth and tag in {"h1", "h2", "h3"} and self._heading_parts is not None:
            value = clean_text(" ".join(self._heading_parts))
            if value:
                self.heading_candidates.append(value)
            self._heading_parts = None

    def handle_data(self, data):
        if self._ignored_depth:
            return
        value = clean_text(data)
        if not value:
            return
        self.tokens.append(value)
        if self._heading_parts is not None:
            self._heading_parts.append(value)


def _labeled_date(tokens: list[str], label: str) -> str | None:
    for index, token in enumerate(tokens):
        if label not in token:
            continue
        window = " ".join(tokens[index:index + 4])
        value = first_date(window)
        if value:
            return value
    return None


def _article_bounds(tokens: list[str], listing_title: str) -> tuple[int, int]:
    start = 0
    for label in ("수정일", "등록일"):
        for index, token in enumerate(tokens):
            if label in token and first_date(" ".join(tokens[index:index + 4])):
                start = min(len(tokens), index + 4)
                break
        if start:
            break
    if not start:
        target = normalized_title(listing_title)
        title_positions = [i for i, token in enumerate(tokens) if normalized_title(token) == target]
        if title_positions:
            start = title_positions[-1] + 1
    end = len(tokens)
    for index in range(start, len(tokens)):
        if any(stop in tokens[index] for stop in STOP_TOKENS):
            end = index
            break
    return start, end


def _title_match(parser: DetailParser, listing_title: str) -> str:
    expected = clean_text(listing_title)
    candidates = parser.meta_titles + parser.heading_candidates
    if any(clean_text(value) == expected for value in candidates):
        return "EXACT"
    expected_norm = normalized_title(expected)
    if any(normalized_title(value) == expected_norm for value in candidates):
        return "NORMALIZED"
    return "MISMATCH"


def _marker_counts(article_text: str) -> dict[str, int]:
    return {
        name: sum(len(re.findall(pattern, article_text)) for pattern in patterns)
        for name, patterns in STRUCTURE_PATTERNS.items()
    }


def _attachment_count(parser: DetailParser, start: int, end: int, detail_url: str) -> int:
    official_host = (urlparse(detail_url).hostname or "").lower()
    count = 0
    for token_index, href in parser.links:
        if not (start <= token_index < end) or not href:
            continue
        parsed = urlparse(href)
        if parsed.scheme and parsed.scheme != "https":
            continue
        if parsed.hostname and parsed.hostname.lower() != official_host:
            continue
        lowered = href.lower()
        if any(ext in lowered for ext in (".pdf", ".hwp", ".hwpx", ".doc", ".docx", "download")):
            count += 1
    return count


def derive_detail_record(listing_record: dict, html_text: str, diagnostics: dict) -> dict:
    parser = DetailParser()
    parser.feed(html_text)
    start, end = _article_bounds(parser.tokens, listing_record["title"])
    article_text = " ".join(parser.tokens[start:end])
    markers = _marker_counts(article_text)
    marker_total = sum(markers.values())
    title_match = _title_match(parser, listing_record["title"])
    registered = _labeled_date(parser.tokens, "등록일")
    modified = _labeled_date(parser.tokens, "수정일")
    if registered:
        date_kind = "REGISTERED"
        date_match = "MATCH" if registered == listing_record["published_at"] else "MISMATCH"
    elif modified:
        date_kind = "MODIFIED_ONLY"
        date_match = "NOT_COMPARABLE"
    else:
        date_kind = "NOT_FOUND"
        date_match = "NOT_COMPARABLE"
    body_status = "STRUCTURED" if marker_total and len(article_text) >= 20 else "BOUNDED_TEXT"
    access_status = "SUCCESS"
    if title_match == "MISMATCH" or date_match == "MISMATCH" or body_status != "STRUCTURED":
        access_status = "PARTIAL"
    result = dict(listing_record)
    result.update(
        {
            "access_status": access_status,
            "body_status": body_status,
            "content_fingerprint": diagnostics.get("content_sha256")
            or hashlib.sha256(html_text.encode("utf-8")).hexdigest(),
            "title_match": title_match,
            "detail_date_kind": date_kind,
            "detail_published_at": registered,
            "detail_modified_at": modified,
            "listing_detail_date_match": date_match,
            "structural_markers": markers,
            "structural_marker_count": marker_total,
            "article_text_chars_observed": len(article_text),
            "attachment_link_count_not_fetched": _attachment_count(
                parser, start, end, listing_record["detail_url"]
            ),
        }
    )
    return result


def failed_detail_record(listing_record: dict, diagnostics: dict) -> dict:
    result = dict(listing_record)
    result.update(
        {
            "access_status": "FAILED",
            "body_status": "FAILED",
            "title_match": "NOT_EVALUATED",
            "detail_date_kind": "NOT_EVALUATED",
            "detail_published_at": None,
            "detail_modified_at": None,
            "listing_detail_date_match": "NOT_EVALUATED",
            "structural_markers": {name: 0 for name in STRUCTURE_PATTERNS},
            "structural_marker_count": 0,
            "article_text_chars_observed": 0,
            "attachment_link_count_not_fetched": 0,
            "detail_error_code": diagnostics.get("error_code") or "DETAIL_FETCH_FAILED",
        }
    )
    return result


def collect_one(
    source: dict,
    observed_at: str,
    *,
    listing_fetcher=fetch_html,
    detail_fetcher=fetch_html,
) -> dict:
    listing_status, listing_html, listing_diagnostics = listing_fetcher(source["official_url"])
    if listing_html is None:
        return {
            "schema": 1,
            "source_id": source["source_id"],
            "maturity": source["maturity"],
            "collected_at_kst": observed_at,
            "source_url": source["official_url"],
            "access_status": "FAILED",
            "coverage": "FIRST_OFFICIAL_LIST_PAGE_FIRST_5_DETAILS_NO_ATTACHMENTS",
            "records": [],
            "interpretation_status": "NOT_EVALUATED",
            "diagnostics": {
                "listing_error_code": listing_diagnostics.get("error_code"),
                "detail_requested": 0,
                "detail_success": 0,
                "detail_partial": 0,
                "detail_failed": 0,
            },
        }

    listing_records, parse_diagnostics = parse_audit(
        listing_html, source["official_url"], observed_at
    )
    selected = listing_records[:MAX_DETAIL_RECORDS]
    records = []
    detail_statuses = []
    for listing_record in selected:
        status, html_text, diagnostics = detail_fetcher(listing_record["detail_url"])
        if html_text is None or status == "FAILED":
            records.append(failed_detail_record(listing_record, diagnostics))
            detail_statuses.append("FAILED")
            continue
        detail = derive_detail_record(listing_record, html_text, diagnostics)
        if status == "PARTIAL" and detail["access_status"] == "SUCCESS":
            detail["access_status"] = "PARTIAL"
        records.append(detail)
        detail_statuses.append(detail["access_status"])

    if listing_status == "FAILED":
        access_status = "FAILED"
    elif not selected or any(status != "SUCCESS" for status in detail_statuses):
        access_status = "PARTIAL"
    else:
        access_status = "SUCCESS"

    return {
        "schema": 1,
        "source_id": source["source_id"],
        "maturity": source["maturity"],
        "collected_at_kst": observed_at,
        "source_url": source["official_url"],
        "access_status": access_status,
        "coverage": "FIRST_OFFICIAL_LIST_PAGE_FIRST_5_DETAILS_NO_ATTACHMENTS",
        "records": records,
        "interpretation_status": "NOT_EVALUATED",
        "diagnostics": {
            "listing_error_code": listing_diagnostics.get("error_code"),
            "listing_candidate_count": parse_diagnostics.get("candidate_count", 0),
            "listing_date_missing_count": parse_diagnostics.get("date_missing_count", 0),
            "detail_requested": len(selected),
            "detail_success": detail_statuses.count("SUCCESS"),
            "detail_partial": detail_statuses.count("PARTIAL"),
            "detail_failed": detail_statuses.count("FAILED"),
            "attachment_downloads": 0,
        },
    }


def render_summary(observation: dict) -> str:
    d = observation["diagnostics"]
    lines = [
        "# 서울시 감사 결과 L2 본문 구조 표본",
        "",
        "최근 상세 페이지 최대 5건에서 목록 대응과 구조 표지만 확인했습니다. 원문 문장, 담당자, 연락처, 첨부파일, 질문과 브리핑은 저장하지 않았습니다.",
        "",
        f"- 전체 접근: {observation['access_status']}",
        f"- 상세 요청: {d.get('detail_requested', 0)}건",
        f"- 성공/부분/실패: {d.get('detail_success', 0)}/{d.get('detail_partial', 0)}/{d.get('detail_failed', 0)}",
        f"- 첨부파일 다운로드: {d.get('attachment_downloads', 0)}건",
        "",
        "| 등록일 | 제목 | 제목 대응 | 상세 날짜 | 구조 표지 | 첨부 링크(미수집) | 접근 |",
        "|---|---|---|---|---:|---:|---|",
    ]
    for row in observation["records"]:
        lines.append(
            f"| {row.get('published_at') or '-'} | [{row['title']}]({row['detail_url']}) | "
            f"{row.get('title_match', '-')} | {row.get('detail_date_kind', '-')} / "
            f"{row.get('listing_detail_date_match', '-')} | {row.get('structural_marker_count', 0)} | "
            f"{row.get('attachment_link_count_not_fetched', 0)} | {row['access_status']} |"
        )
    lines.extend(
        [
            "",
            "- MODIFIED_ONLY는 목록 등록일을 대체하지 않습니다.",
            "- 구조 표지는 문서 형식의 존재만 뜻하며 문제·피해·기사 가치를 확정하지 않습니다.",
            "- PARTIAL·FAILED는 감사 결과가 0건이라는 뜻이 아닙니다.",
            "",
        ]
    )
    return "\n".join(lines)


def run(output_dir: Path) -> dict:
    registry = load_registry()
    sources = {row["source_id"]: row for row in registry["sources"]}
    observed_at = now_kst()
    observation = collect_one(sources[SOURCE_ID], observed_at)
    errors = validate_thin_observation(observation, registry)
    if errors:
        raise RuntimeError("; ".join(errors))
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle = {
        "schema": 1,
        "probe": "L2_BOUNDED_BODY_STRUCTURE",
        "collected_at_kst": observed_at,
        "observations": [observation],
    }
    (output_dir / "audit_l2.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "SUMMARY.md").write_text(render_summary(observation), encoding="utf-8")
    return observation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("source-onboarding-v1/output/audit-l2"),
    )
    args = parser.parse_args()
    print(render_summary(run(args.output_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
