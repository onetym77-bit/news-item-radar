#!/usr/bin/env python3
"""L3 semantic trial for Seoul audit reports.

At most three recent official detail pages and their public PDF attachments are
read. Only the first twelve PDF pages are converted to text in a temporary
folder. Persisted output contains derived counts, categories, hashes, and
verification-only questions; never the extracted report text, names, contacts,
briefing entries, or ledger updates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import socket
from io import BytesIO
from datetime import date, datetime
from pathlib import Path

from pypdf import PdfReader
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, build_opener

from collect_audit_l2 import DetailParser, _article_bounds, _title_match
from collect_l1_batch import fetch_html, parse_audit
from probe_l0_batch import SafeRedirectHandler
from thin_source_contract import FORBIDDEN_KEYS, load_registry, walk_keys

SOURCE_ID = "seoul_audit_results"
MAX_DETAIL_RECORDS = 3
MAX_PDF_BYTES = 20_000_000
MAX_PDF_PAGES = 12
MAX_EXTRACTED_CHARS = 250_000
PDF_TIMEOUT_SECONDS = 25

DISPOSITION_TERMS = ("시정", "주의", "개선", "권고", "통보", "징계", "고발", "기관경고")
DOMAIN_TERMS = {
    "RIGHTS_SAFETY": (
        "인권", "아동", "안전", "개인정보", "진정", "보호", "치료", "사고", "위험",
    ),
    "PROCUREMENT_CONTRACT": (
        "계약", "입찰", "수의계약", "발주", "공사", "용역", "물품", "하도급", "업체",
    ),
    "CITIZEN_SERVICE": (
        "민원", "처리 기한", "시민 불편", "서비스", "이용", "대기", "신청",
    ),
    "FINANCE_BENEFIT": (
        "회계", "후원금", "수당", "급여", "자금", "예산", "재정", "환수", "추징", "감액",
    ),
    "GOVERNANCE_CONTROL": (
        "채용", "복무", "위원회", "내부통제", "절차", "관리", "감독", "지침",
    ),
}
DOMAIN_PRIORITY = (
    "RIGHTS_SAFETY",
    "PROCUREMENT_CONTRACT",
    "CITIZEN_SERVICE",
    "FINANCE_BENEFIT",
    "GOVERNANCE_CONTROL",
)


def now_kst() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def find_pdf_attachment(html_text: str, detail_url: str) -> str | None:
    parser = DetailParser()
    parser.feed(html_text)
    start, end = _article_bounds(parser.tokens, "")
    expected_host = (urlparse(detail_url).hostname or "").lower()
    for token_index, href in parser.links:
        if not href or not (start <= token_index < end):
            continue
        absolute = urljoin(detail_url, href)
        parsed = urlparse(absolute)
        if (
            parsed.scheme == "https"
            and (parsed.hostname or "").lower() == expected_host
            and parsed.path.lower().endswith(".pdf")
        ):
            return absolute
    return None


def fetch_pdf(url: str, timeout: int = PDF_TIMEOUT_SECONDS) -> tuple[str, bytes | None, dict]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return "FAILED", None, {"error_code": "UNSAFE_PDF_URL", "http_status": None}
    redirects = SafeRedirectHandler(parsed.hostname)
    opener = build_opener(redirects)
    request = Request(
        url,
        headers={
            "User-Agent": "news-item-radar-audit-l3/1.0 (+read-only; public-report-pages-only)",
            "Accept": "application/pdf;q=1.0,*/*;q=0.1",
        },
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            final = urlparse(response.geturl())
            if final.scheme != "https" or (final.hostname or "").lower() != parsed.hostname.lower():
                return "FAILED", None, {
                    "error_code": "FINAL_PDF_URL_OUTSIDE_OFFICIAL_HOST",
                    "http_status": response.getcode(),
                }
            raw = response.read(MAX_PDF_BYTES + 1)
            if len(raw) > MAX_PDF_BYTES:
                return "FAILED", None, {
                    "error_code": "PDF_TOO_LARGE",
                    "http_status": response.getcode(),
                    "response_bytes": len(raw),
                }
            content_type = response.headers.get_content_type()
            if not raw.startswith(b"%PDF-"):
                return "FAILED", None, {
                    "error_code": "NOT_A_PDF",
                    "http_status": response.getcode(),
                    "content_type": content_type,
                }
            return "SUCCESS", raw, {
                "error_code": None,
                "http_status": response.getcode(),
                "response_bytes": len(raw),
                "content_type": content_type,
                "content_sha256": hashlib.sha256(raw).hexdigest(),
                "redirect_count": redirects.redirect_count,
            }
    except HTTPError as exc:
        return "FAILED", None, {"error_code": f"HTTP_{exc.code}", "http_status": exc.code}
    except (TimeoutError, socket.timeout):
        return "FAILED", None, {"error_code": "TIMEOUT", "http_status": None}
    except URLError:
        return "FAILED", None, {"error_code": "NETWORK_ERROR", "http_status": None}
    except ValueError:
        return "FAILED", None, {"error_code": "SECURITY_ERROR", "http_status": None}


def extract_pdf_text(pdf_bytes: bytes) -> tuple[str, str | None, dict]:
    """Extract only first pages in memory; fail closed on huge/opaque pages."""
    try:
        reader = PdfReader(BytesIO(pdf_bytes), strict=True)
        if reader.is_encrypted:
            return "FAILED", None, {"error_code": "PDF_ENCRYPTED"}
        parts = []
        total_chars = 0
        pages_sampled = min(len(reader.pages), MAX_PDF_PAGES)
        for index in range(pages_sampled):
            page = reader.pages[index]
            contents = page.get_contents()
            if contents is not None and len(contents.get_data()) > 5_000_000:
                return "FAILED", None, {"error_code": "PDF_PAGE_CONTENT_TOO_LARGE"}
            page_text = page.extract_text(extraction_mode="layout") or ""
            total_chars += len(page_text)
            if total_chars > MAX_EXTRACTED_CHARS:
                return "PARTIAL", None, {
                    "error_code": "EXTRACTED_TEXT_TOO_LARGE",
                    "pdf_pages_sampled": index + 1,
                }
            parts.append(page_text)
        text_value = "\\f".join(parts)
        if len(text_value.strip()) < 100:
            return "PARTIAL", None, {
                "error_code": "PDF_TEXT_INSUFFICIENT",
                "pdf_pages_sampled": pages_sampled,
            }
        return "SUCCESS", text_value, {
            "error_code": None,
            "pdf_pages_sampled": pages_sampled,
            "extracted_text_chars": len(text_value),
            "extracted_text_sha256": hashlib.sha256(text_value.encode("utf-8")).hexdigest(),
        }
    except Exception:
        return "FAILED", None, {"error_code": "PDF_TEXT_EXTRACTION_FAILED"}


def normalize_report_text(value: str) -> str:
    value = value.replace("\u00a0", " ").replace("\ufeff", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def summary_window(report_text: str) -> tuple[str, bool]:
    """Find a real findings table after the contents pages, never the TOC."""
    pages = report_text.split("\f")
    if len(pages) < 3:
        return "", False
    for index in range(2, min(len(pages), MAX_PDF_PAGES)):
        page = normalize_report_text(pages[index])
        has_table = "일람표" in page or "감사결과 총괄" in page
        has_finding_columns = any(
            token in page for token in ("처분유형", "조치(안)", "조치(안)", "조치현황")
        )
        if not (has_table and has_finding_columns):
            continue
        next_page = normalize_report_text(pages[index + 1]) if index + 1 < len(pages) else ""
        return (page + "\n" + next_page)[:30_000], True
    return "", False


def extract_finding_count(window: str) -> int | None:
    patterns = (
        r"(?:처분요구사항|지적사항|처분요구)\s*(?:일람표|목록)?\s*[:：]?\s*(\d{1,3})\s*건",
        r"(?:일람표|목록)\s*[:：]\s*(\d{1,3})\s*건",
        r"총\s*건수\s*[:：]?\s*(\d{1,3})\s*건",
    )
    for pattern in patterns:
        match = re.search(pattern, window)
        if match:
            value = int(match.group(1))
            if 0 < value <= 500:
                return value
    return None


def extract_dispositions(window: str) -> tuple[list[str], dict[str, int]]:
    present = [term for term in DISPOSITION_TERMS if term in window]
    counts: dict[str, int] = {}
    bracket_candidates = re.findall(r"[\[【]([^\]】\n]{1,180})[\]】]", window)
    candidates = bracket_candidates + window.splitlines()[:25]
    for fragment in candidates:
        for term in DISPOSITION_TERMS:
            match = re.search(rf"{re.escape(term)}\s*[(]?\s*(\d{{1,3}})\s*[)]?", fragment)
            if match:
                value = int(match.group(1))
                if 0 <= value <= 500:
                    counts[term] = value
    return present, counts


def classify_domains(window: str) -> dict[str, int]:
    return {
        domain: sum(window.count(term) for term in terms)
        for domain, terms in DOMAIN_TERMS.items()
        if any(term in window for term in terms)
    }


def subject_from_title(title: str) -> str:
    value = re.sub(
        r"\s*(기관운영|관리[·ㆍ ]운영 실태|관리운영 실태|종합|특정)?\s*감사\s*결과\s*(공개문)?\s*$",
        "",
        title,
    ).strip()
    return value or title.strip()


def days_since(published_at: str | None, today: date | None = None) -> int | None:
    if not published_at:
        return None
    try:
        published = date.fromisoformat(published_at)
    except ValueError:
        return None
    return ((today or date.today()) - published).days


def dominant_domain(domain_counts: dict[str, int]) -> str | None:
    if not domain_counts:
        return None
    return max(
        DOMAIN_PRIORITY,
        key=lambda domain: (domain_counts.get(domain, 0), -DOMAIN_PRIORITY.index(domain)),
    ) if any(domain_counts.get(domain, 0) for domain in DOMAIN_PRIORITY) else None


def question_components(subject: str, domain: str) -> dict:
    if domain == "RIGHTS_SAFETY":
        return {
            "verification_question": (
                f"{subject} 감사에서 확인된 권리·안전 지적은 문서상 조치로 끝났나, "
                "실제 보호 절차의 변화로 이어졌나? 감사 전후 진정·민원·사고·후속점검 기록을 "
                "비교하면 개별 사례인지 감독 구조의 반복 문제인지 가를 수 있는가?"
            ),
            "public_interest_to_verify": "이용자·보호대상의 안전과 권리 보장",
            "structural_hypothesis": "감독·기록·후속점검 구조의 결함이 같은 위험을 반복시킨다.",
            "alternative_hypothesis": "감사 시점의 개별 시설 또는 단발성 절차 오류였다.",
            "minimum_test": "감사 전후의 진정·민원·사고 기록과 조치 이행 자료를 같은 기준으로 대조한다.",
        }
    if domain == "PROCUREMENT_CONTRACT":
        return {
            "verification_question": (
                f"{subject} 감사에서 확인된 계약·조달 지적은 개별 실수인가, 반복되는 내부 통제 부재인가? "
                "감사 전후 계약자료에서 경쟁 방식·변경계약·수의계약·업체 집중과 조치 이행을 "
                "대조하면 어느 설명이 남는가?"
            ),
            "public_interest_to_verify": "공공예산의 경쟁성·가격 적정성과 사업 품질",
            "structural_hypothesis": "심사·계약 통제 규칙이 약해 특정 유형의 계약 문제가 반복된다.",
            "alternative_hypothesis": "특수한 사업 조건 때문에 생긴 소수의 불가피한 예외였다.",
            "minimum_test": "감사 전후 계약 공개자료에서 계약 방식과 변경·수의계약 비중을 비교한다.",
        }
    if domain == "CITIZEN_SERVICE":
        return {
            "verification_question": (
                f"{subject} 감사에서 확인된 민원·서비스 지적은 처리기록상의 지연인가, "
                "시민이 다시 신청하거나 이용을 포기하게 만든 운영 문제인가? 감사 전후 처리기한·"
                "재접수·후속민원을 비교하면 업무량 효과와 관리 부실을 구분할 수 있는가?"
            ),
            "public_interest_to_verify": "민원 처리시간과 서비스 이용 기회",
            "structural_hypothesis": "처리 책임과 점검 체계의 공백이 지연과 재접수를 만든다.",
            "alternative_hypothesis": "일시적인 업무량 증가나 복잡한 민원 구성 때문이었다.",
            "minimum_test": "감사 전후 처리기한 초과와 재접수·후속민원 비율을 비교한다.",
        }
    if domain == "FINANCE_BENEFIT":
        return {
            "verification_question": (
                f"{subject} 감사에서 확인된 회계·급여·재정 지적은 장부 정정으로 끝났나, "
                "실제 지급·회수 결과를 바꿨나? 감사 전후 정산·지급·환수 내역을 대상과 항목별로 "
                "대조하면 단순 기록 오류와 시민 재산상 영향을 구분할 수 있는가?"
            ),
            "public_interest_to_verify": "지급 대상의 재산상 권리와 공공재정 누수",
            "structural_hypothesis": "정산·승인 통제의 결함이 실제 지급 또는 회수 오류로 이어진다.",
            "alternative_hypothesis": "실제 금전 영향 없이 기록과 절차만 잘못됐다.",
            "minimum_test": "감사 전후 정산·지급·환수 자료를 항목별로 맞춰 실제 금액 변화를 확인한다.",
        }
    return {
        "verification_question": (
            f"{subject} 감사의 관리·절차 지적은 한 부서의 실수인가, 기관 전체 통제 구조의 문제인가? "
            "같은 유형의 과거 감사와 후속 조치 이행을 대조하면 반복 범위와 책임 주체를 가를 수 있는가?"
        ),
        "public_interest_to_verify": "행정 결정의 일관성과 책임성",
        "structural_hypothesis": "기관 공통의 승인·점검 구조가 반복 지적을 만든다.",
        "alternative_hypothesis": "특정 부서·시기의 단발성 집행 오류였다.",
        "minimum_test": "같은 유형의 과거 감사 지적과 현재 조치 이행 여부를 항목별로 대조한다.",
    }


def build_card(listing_record: dict, attachment_url: str, pdf_diagnostics: dict, report_text: str) -> dict:
    window, summary_confirmed = summary_window(report_text)
    finding_count = extract_finding_count(window)
    dispositions, disposition_counts = extract_dispositions(window)
    domain_counts = classify_domains(window)
    domain = dominant_domain(domain_counts)
    documented_issue = bool(
        re.search(r"부적정|미흡|소홀|위반|지연|불이행|부족|개선\\s*필요", window)
    )
    anchor_ready = bool(summary_confirmed and documented_issue and domain and dispositions)
    anchor = "PROBLEM_SIGNAL" if anchor_ready else "UNRESOLVED"
    subject = subject_from_title(listing_record["title"])
    freshness = days_since(listing_record.get("published_at"))
    base = {
        "source_record_id": listing_record["source_record_id"],
        "title": listing_record["title"],
        "detail_url": listing_record["detail_url"],
        "published_at": listing_record.get("published_at"),
        "attachment_url": attachment_url,
        "attachment_sha256": pdf_diagnostics.get("content_sha256"),
        "report_text_sha256": pdf_diagnostics.get("extracted_text_sha256"),
        "pdf_pages_sampled": pdf_diagnostics.get("pdf_pages_sampled"),
        "raw_report_text_persisted": False,
        "summary_table_confirmed": summary_confirmed,
        "documented_issue_in_table": documented_issue,
        "official_finding_count": finding_count,
        "disposition_terms": dispositions,
        "disposition_counts": disposition_counts,
        "risk_domains": sorted(domain_counts),
        "risk_domain_counts": domain_counts,
        "evidence_anchor": anchor,
        "freshness_days": freshness,
        "why_now": "NEW_OFFICIAL_REPORT" if freshness is not None and 0 <= freshness <= 30 else "RECENT_REPORT_SAMPLE",
    }
    if not anchor_ready:
        base.update(
            {
                "question_status": "HOLD",
                "hold_reason": "공개문 앞부분에서 지적 요약·처분 유형·문제 영역의 결합을 확인하지 못함",
                "verification_question": None,
                "source_frame": None,
                "editorial_addition": None,
                "public_interest_to_verify": None,
                "competing_hypotheses": [],
                "discriminating_test": None,
                "minimum_test_timebox": None,
                "discard_condition": None,
            }
        )
        return base
    components = question_components(subject, domain)
    count_phrase = f"{finding_count}건의 처분요구" if finding_count else "복수의 처분요구"
    base.update(
        {
            "question_status": "READY_FOR_HUMAN_REVIEW",
            "hold_reason": None,
            "source_frame": f"공개 감사보고서가 {subject}에서 {count_phrase}와 {', '.join(dispositions[:4])} 조치를 제시함",
            "editorial_addition": "지적의 존재를 반복하지 않고 감사 이후 실제 운영 변화와 반복 구조를 검증",
            "verification_question": components["verification_question"],
            "public_interest_to_verify": components["public_interest_to_verify"],
            "competing_hypotheses": [
                components["structural_hypothesis"],
                components["alternative_hypothesis"],
            ],
            "discriminating_test": components["minimum_test"],
            "minimum_test_timebox": "24시간 이내",
            "discard_condition": "후속 자료에서 지적이 단일 절차 오류로 종결됐고 실제 결과·반복성이 확인되지 않으면 질문을 폐기",
        }
    )
    return base


def failed_card(listing_record: dict, stage: str, error_code: str | None) -> dict:
    return {
        "source_record_id": listing_record["source_record_id"],
        "title": listing_record["title"],
        "detail_url": listing_record["detail_url"],
        "published_at": listing_record.get("published_at"),
        "question_status": "HOLD",
        "evidence_anchor": "UNRESOLVED",
        "failed_stage": stage,
        "hold_reason": error_code or "UNKNOWN_FAILURE",
        "verification_question": None,
        "raw_report_text_persisted": False,
    }


def validate_l3_output(payload: dict, registry: dict) -> list[str]:
    errors = []
    source = next(
        (row for row in registry.get("sources", []) if row.get("source_id") == payload.get("source_id")),
        None,
    )
    if not source:
        return ["source is not registered"]
    if source.get("maturity") != "L3":
        errors.append("L3 output requires registry maturity L3")
    if source.get("question_output") != "VERIFICATION_ONLY":
        errors.append("L3 output requires VERIFICATION_ONLY")
    if payload.get("briefing_output") != "NONE":
        errors.append("L3 output cannot create briefing output")
    if payload.get("automatic_ledger_write") is not False:
        errors.append("L3 output cannot write ledgers")
    cards = payload.get("cards")
    if not isinstance(cards, list) or len(cards) > MAX_DETAIL_RECORDS:
        errors.append("L3 output must contain at most three cards")
        return errors
    forbidden = FORBIDDEN_KEYS & set(walk_keys(payload))
    if forbidden:
        errors.append("forbidden L3 keys: " + ", ".join(sorted(forbidden)))
    for index, card in enumerate(cards):
        if card.get("raw_report_text_persisted") is not False:
            errors.append(f"cards[{index}] must not persist report text")
        if card.get("question_status") == "READY_FOR_HUMAN_REVIEW":
            if card.get("evidence_anchor") != "PROBLEM_SIGNAL":
                errors.append(f"cards[{index}] ready question lacks problem anchor")
            if not card.get("verification_question"):
                errors.append(f"cards[{index}] ready question is empty")
            if len(card.get("competing_hypotheses", [])) < 2:
                errors.append(f"cards[{index}] needs competing hypotheses")
            if not card.get("discriminating_test") or not card.get("discard_condition"):
                errors.append(f"cards[{index}] lacks a test or discard condition")
    return errors


def collect_l3(
    source: dict,
    observed_at: str,
    *,
    html_fetcher=fetch_html,
    pdf_fetcher=fetch_pdf,
    pdf_extractor=extract_pdf_text,
) -> dict:
    listing_status, listing_html, listing_diag = html_fetcher(source["official_url"])
    cards = []
    counters = {
        "detail_requested": 0,
        "pdf_found": 0,
        "pdf_extracted": 0,
        "ready_questions": 0,
        "held_questions": 0,
        "raw_reports_persisted": 0,
    }
    if listing_html is None:
        return {
            "schema": 1,
            "source_id": source["source_id"],
            "maturity": source["maturity"],
            "collected_at_kst": observed_at,
            "access_status": "FAILED",
            "coverage": "FIRST_LIST_PAGE_FIRST_3_PUBLIC_PDFS_FIRST_12_PAGES",
            "question_output": "VERIFICATION_ONLY",
            "briefing_output": "NONE",
            "automatic_ledger_write": False,
            "cards": [],
            "diagnostics": {**counters, "error_code": listing_diag.get("error_code")},
        }
    listing_records, listing_parse_diag = parse_audit(
        listing_html, source["official_url"], observed_at
    )
    for listing_record in listing_records[:MAX_DETAIL_RECORDS]:
        counters["detail_requested"] += 1
        detail_status, detail_html, detail_diag = html_fetcher(listing_record["detail_url"])
        if detail_html is None or detail_status == "FAILED":
            cards.append(failed_card(listing_record, "DETAIL_HTML", detail_diag.get("error_code")))
            continue
        detail_parser = DetailParser()
        detail_parser.feed(detail_html)
        if _title_match(detail_parser, listing_record["title"]) == "MISMATCH":
            cards.append(failed_card(listing_record, "DETAIL_MATCH", "TITLE_MISMATCH"))
            continue
        attachment = find_pdf_attachment(detail_html, listing_record["detail_url"])
        if not attachment:
            cards.append(failed_card(listing_record, "PDF_DISCOVERY", "OFFICIAL_PDF_NOT_FOUND"))
            continue
        counters["pdf_found"] += 1
        pdf_status, pdf_bytes, pdf_diag = pdf_fetcher(attachment)
        if pdf_bytes is None or pdf_status == "FAILED":
            cards.append(failed_card(listing_record, "PDF_FETCH", pdf_diag.get("error_code")))
            continue
        text_status, report_text, text_diag = pdf_extractor(pdf_bytes)
        combined_diag = {**pdf_diag, **text_diag}
        if report_text is None or text_status == "FAILED":
            cards.append(failed_card(listing_record, "PDF_TEXT", text_diag.get("error_code")))
            continue
        counters["pdf_extracted"] += 1
        card = build_card(listing_record, attachment, combined_diag, report_text)
        cards.append(card)

    counters["ready_questions"] = sum(
        card.get("question_status") == "READY_FOR_HUMAN_REVIEW" for card in cards
    )
    counters["held_questions"] = sum(card.get("question_status") == "HOLD" for card in cards)
    if listing_status != "SUCCESS" or not cards or counters["held_questions"]:
        access_status = "PARTIAL"
    else:
        access_status = "SUCCESS"
    return {
        "schema": 1,
        "source_id": source["source_id"],
        "maturity": source["maturity"],
        "collected_at_kst": observed_at,
        "access_status": access_status,
        "coverage": "FIRST_LIST_PAGE_FIRST_3_PUBLIC_PDFS_FIRST_12_PAGES",
        "question_output": "VERIFICATION_ONLY",
        "briefing_output": "NONE",
        "automatic_ledger_write": False,
        "cards": cards,
        "diagnostics": {
            **counters,
            "listing_candidate_count": listing_parse_diag.get("candidate_count", 0),
            "listing_error_code": listing_diag.get("error_code"),
        },
    }


def render_summary(payload: dict) -> str:
    d = payload["diagnostics"]
    lines = [
        "# 서울시 감사 결과 L3 의미 해석 시험",
        "",
        "감사 공개문 원문은 저장하지 않고, 앞 12쪽에서 파생한 요약 신호로 검증 질문만 만들었습니다.",
        "",
        f"- 접근: {payload['access_status']}",
        f"- 상세/PDF/텍스트 성공: {d.get('detail_requested', 0)}/{d.get('pdf_found', 0)}/{d.get('pdf_extracted', 0)}",
        f"- 사람 검토 질문/보류: {d.get('ready_questions', 0)}/{d.get('held_questions', 0)}",
        f"- 원문 저장: {d.get('raw_reports_persisted', 0)}건",
        "",
    ]
    for index, card in enumerate(payload["cards"], 1):
        lines.extend(
            [
                f"## {index}. {card['title']}",
                "",
                f"- 상태: {card['question_status']}",
                f"- 근거 앵커: {card['evidence_anchor']}",
                f"- 공식 지적 건수: {card.get('official_finding_count') if card.get('official_finding_count') is not None else '미확인'}",
                f"- 처분 유형: {', '.join(card.get('disposition_terms', [])) or '미확인'}",
                f"- 문제 영역: {', '.join(card.get('risk_domains', [])) or '미확인'}",
            ]
        )
        if card.get("verification_question"):
            lines.extend(
                [
                    "",
                    f"**검증 질문:** {card['verification_question']}",
                    "",
                    f"- 출처가 말한 것: {card['source_frame']}",
                    f"- 새로 확인할 것: {card['editorial_addition']}",
                    f"- 최소 판정: {card['discriminating_test']}",
                    f"- 폐기 조건: {card['discard_condition']}",
                ]
            )
        else:
            lines.append(f"- 보류 이유: {card.get('hold_reason', '미확인')}")
        lines.extend(["", f"[공식 상세 페이지]({card['detail_url']})", ""])
    lines.extend(
        [
            "- 이 질문은 기사 후보나 감사 결과의 재진술이 아니라 사람 검토 전 검증 과제입니다.",
            "- 독립 근거·시민 행동·반대 근거를 확인하기 전에는 브리핑과 장부로 이동하지 않습니다.",
            "",
        ]
    )
    return "\n".join(lines)


def run(output_dir: Path) -> dict:
    registry = load_registry()
    source = next(row for row in registry["sources"] if row["source_id"] == SOURCE_ID)
    payload = collect_l3(source, now_kst())
    errors = validate_l3_output(payload, registry)
    if errors:
        raise RuntimeError("; ".join(errors))
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "audit_l3.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "SUMMARY.md").write_text(render_summary(payload), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("source-onboarding-v1/output/audit-l3"),
    )
    args = parser.parse_args()
    payload = run(args.output_dir)
    print(render_summary(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
