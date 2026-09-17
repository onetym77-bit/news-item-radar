#!/usr/bin/env python3
"""Seven-day, read-only-to-editorial shadow evaluation of Seoul audit questions.

The workflow persists only bounded, derived cards. It never writes the item
ledger, the question-quality ledger, or the daily briefing. Human review is
supplied separately through an explicit CSV; machine checks are not substituted
for editorial judgment.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from collect_l1_batch import fetch_html, parse_audit
from interpret_audit_l3 import MAX_DETAIL_RECORDS, collect_l3, validate_l3_output
from thin_source_contract import FORBIDDEN_KEYS, load_registry, walk_keys

BASE = Path(__file__).resolve().parent
DEFAULT_STATE = BASE / "output" / "audit-l4" / "state_latest.json"
DEFAULT_REVIEWS = BASE / "audit_l4_reviews.csv"
SOURCE_ID = "seoul_audit_results"
MAX_LIST_PAGES = 2
MAX_RECORDS = 40
MAX_RUNS = 60
BACKFILL_DAYS = 365
FRESH_DAYS = 30
MIN_UNIQUE_DOCUMENTS = 12
MIN_OBSERVATION_DAYS = 7
SCORE_FIELDS = (
    "grounding", "scope", "citizen_impact", "specificity",
    "competing_hypotheses", "testability",
)
READY_VERDICTS = {"START_REPORTING", "VERIFY", "REJECT"}
HOLD_VERDICTS = {"CONFIRM_HOLD", "MISSED_VALUE"}
DOCUMENT_VALUES = {"VALUABLE", "WEAK", "NO_VALUE"}
ANGLE_SELECTIONS = {"RIGHT_ANGLE", "MISSED_STRONGER_FINDING", "NOT_APPLICABLE"}
CRITICAL_ERRORS = {
    "NONE", "SCOPE_AS_FACT", "VICTIM_INFERRED", "SCOPE_OVERREACH",
    "KEYWORD_DISTORTION", "UNTESTABLE", "PARAPHRASE_ONLY", "OTHER",
}
REVIEW_COLUMNS = (
    "source_record_id", "verdict", "document_value", "angle_selection",
    *SCORE_FIELDS, "critical_error",
)
SAFE_HOST = "news.seoul.go.kr"
RAW_KEYS = {"report_text", "pdf_bytes", "raw_pdf", "raw_report", "raw_html", "full_body"}


def kst_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Seoul"))


def initial_state(now: datetime) -> dict:
    return {
        "schema": 1,
        "source_id": SOURCE_ID,
        "maturity": "L3",
        "pilot": "L4_SHADOW_EVALUATION_NOT_PROMOTION",
        "started_at_kst": now.isoformat(timespec="seconds"),
        "briefing_output": "NONE",
        "automatic_ledger_write": False,
        "approved_for_production": False,
        "raw_reports_persisted": 0,
        "runs": [],
        "records": [],
    }


def load_state(path: Path, now: datetime) -> dict:
    if not path.exists():
        return initial_state(now)
    state = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_state(state)
    if errors:
        raise ValueError("invalid prior shadow state: " + "; ".join(errors))
    return state


def listing_url(base: str, page: int) -> str:
    parsed = urlparse(base)
    if parsed.scheme != "https" or parsed.hostname != SAFE_HOST or parsed.query:
        raise ValueError("unexpected audit listing URL")
    if page == 1:
        return base
    if page < 1 or page > MAX_LIST_PAGES:
        raise ValueError("listing page is outside the bounded sample")
    return base.rstrip("/") + f"/page/{page}"


def is_audit_result(row: dict, today: date) -> bool:
    title = row.get("title", "")
    published_at = row.get("published_at")
    if not published_at or "감사" not in title:
        return False
    if any(term in title for term in ("계획", "예정", "안내", "채용")):
        return False
    try:
        age = (today - date.fromisoformat(published_at)).days
    except ValueError:
        return False
    return 0 <= age <= BACKFILL_DAYS


def discover_records(source: dict, observed_at: str, today: date, fetcher=fetch_html) -> tuple[list[dict], dict]:
    records: list[dict] = []
    errors: list[str] = []
    successful_pages = 0
    seen: set[str] = set()
    for page in range(1, MAX_LIST_PAGES + 1):
        url = listing_url(source["official_url"], page)
        status, html, diagnostic = fetcher(url)
        if html is None or status == "FAILED":
            errors.append(f"PAGE_{page}_{diagnostic.get('error_code') or 'FAILED'}")
            continue
        successful_pages += 1
        parsed, _ = parse_audit(html, url, observed_at)
        for row in parsed:
            record_id = row["source_record_id"]
            if record_id not in seen and is_audit_result(row, today):
                seen.add(record_id)
                records.append(row)
    if not successful_pages:
        raise RuntimeError("all official audit listing pages failed: " + ", ".join(errors))
    records.sort(key=lambda row: (row["published_at"], row["source_record_id"]), reverse=True)
    return records, {
        "listing_pages_attempted": MAX_LIST_PAGES,
        "listing_pages_successful": successful_pages,
        "listing_errors": errors,
        "eligible_listing_records": len(records),
    }


def select_unseen(records: list[dict], seen_ids: set[str], today: date) -> list[dict]:
    unseen = [row for row in records if row["source_record_id"] not in seen_ids]
    fresh = [
        row for row in unseen
        if (today - date.fromisoformat(row["published_at"])).days <= FRESH_DAYS
    ]
    older = [row for row in unseen if row not in fresh]
    return (fresh + older)[:MAX_DETAIL_RECORDS]


def challenge_card(card: dict) -> list[str]:
    """Independent, conservative checks. These are flags, never a quality score."""
    flags = []
    if card.get("question_status") != "READY_FOR_HUMAN_REVIEW":
        return ["SOURCE_EVIDENCE_HELD"]
    question = card.get("verification_question") or ""
    if card.get("official_finding_count") is None:
        flags.append("FINDING_COUNT_UNCONFIRMED")
    if not card.get("discriminating_test"):
        flags.append("NO_DISCRIMINATING_TEST")
    if len(card.get("competing_hypotheses") or []) < 2:
        flags.append("NO_COMPETING_HYPOTHESES")
    if "관리·절차 지적" in question or "권리·안전 지적" in question:
        flags.append("GENERIC_ISSUE_FRAME")
    if card.get("freshness_days") is not None and card["freshness_days"] > FRESH_DAYS:
        flags.append("HISTORICAL_BACKFILL_NOT_TODAY")
    flags.append("HUMAN_CHECK_ACTUAL_CITIZEN_EFFECT")
    flags.append("HUMAN_CHECK_AUDIT_SCOPE_VS_FINDING")
    return flags


def read_reviews(path: Path, records: list[dict]) -> dict[str, dict]:
    if not path.exists():
        return {}
    allowed_ids = {row["source_record_id"]: row for row in records}
    reviews: dict[str, dict] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != REVIEW_COLUMNS:
            raise ValueError("review CSV columns do not match the fixed schema")
        for raw in reader:
            record_id = (raw.get("source_record_id") or "").strip()
            if not record_id:
                continue
            if record_id not in allowed_ids or record_id in reviews:
                raise ValueError(f"unknown or duplicate review ID: {record_id}")
            verdict = (raw.get("verdict") or "").strip().upper()
            card = allowed_ids[record_id]["card"]
            allowed = READY_VERDICTS if card["question_status"] == "READY_FOR_HUMAN_REVIEW" else HOLD_VERDICTS
            if verdict not in allowed:
                raise ValueError(f"invalid verdict for {record_id}")
            document_value = (raw.get("document_value") or "").strip().upper()
            angle_selection = (raw.get("angle_selection") or "").strip().upper()
            if document_value not in DOCUMENT_VALUES:
                raise ValueError(f"invalid document value for {record_id}")
            if angle_selection not in ANGLE_SELECTIONS:
                raise ValueError(f"invalid angle selection for {record_id}")
            if card["question_status"] == "READY_FOR_HUMAN_REVIEW" and angle_selection == "NOT_APPLICABLE":
                raise ValueError(f"ready record needs an angle judgment: {record_id}")
            if angle_selection == "MISSED_STRONGER_FINDING" and document_value != "VALUABLE":
                raise ValueError(f"missed stronger finding requires a valuable document: {record_id}")
            if verdict == "MISSED_VALUE" and (
                document_value != "VALUABLE" or angle_selection != "MISSED_STRONGER_FINDING"
            ):
                raise ValueError(f"missed value must identify a valuable document and missed angle: {record_id}")
            critical = (raw.get("critical_error") or "NONE").strip().upper()
            if critical not in CRITICAL_ERRORS:
                raise ValueError(f"invalid critical error for {record_id}")
            scores = {}
            for field in SCORE_FIELDS:
                value = (raw.get(field) or "").strip()
                if card["question_status"] == "READY_FOR_HUMAN_REVIEW":
                    if value not in {"0", "1", "2"}:
                        raise ValueError(f"missing or invalid {field} for {record_id}")
                    scores[field] = int(value)
                elif value:
                    raise ValueError(f"held record must not have {field} score: {record_id}")
            reviews[record_id] = {
                "verdict": verdict,
                "document_value": document_value,
                "angle_selection": angle_selection,
                "scores": scores,
                "critical_error": critical,
            }
    return reviews


def percent(numerator: int, denominator: int) -> float | None:
    return round(100 * numerator / denominator, 1) if denominator else None


def evaluate(state: dict, reviews: dict[str, dict]) -> dict:
    records = state["records"]
    ready = [item for item in records if item["card"]["question_status"] == "READY_FOR_HUMAN_REVIEW"]
    ready_reviews = [(item, reviews[item["source_record_id"]]) for item in ready if item["source_record_id"] in reviews]
    distinct_days = sorted({run["run_date_kst"] for run in state["runs"]})
    observed_span = (
        (date.fromisoformat(distinct_days[-1]) - date.fromisoformat(distinct_days[0])).days + 1
        if distinct_days else 0
    )
    attempted = sum(run["diagnostics"].get("detail_requested", 0) for run in state["runs"])
    extracted = sum(run["diagnostics"].get("pdf_extracted", 0) for run in state["runs"])
    grounded = sum(
        review["scores"]["grounding"] == 2 and review["scores"]["scope"] == 2
        for _, review in ready_reviews
    )
    startable = sum(review["verdict"] == "START_REPORTING" for _, review in ready_reviews)
    generic = sum(review["scores"]["specificity"] <= 1 for _, review in ready_reviews)
    angle_eligible = [
        review for _, review in ready_reviews
        if review["document_value"] in {"VALUABLE", "WEAK"}
    ]
    right_angle = sum(review["angle_selection"] == "RIGHT_ANGLE" for review in angle_eligible)
    missed_stronger = sum(
        review["angle_selection"] == "MISSED_STRONGER_FINDING"
        for review in reviews.values()
    )
    valuable_documents = sum(
        review["document_value"] == "VALUABLE" for review in reviews.values()
    )
    critical = sum(review["critical_error"] != "NONE" for review in reviews.values())
    complete = sum(
        bool(item["card"].get("verification_question"))
        and len(item["card"].get("competing_hypotheses") or []) >= 2
        and bool(item["card"].get("discriminating_test"))
        and bool(item["card"].get("discard_condition"))
        for item in ready
    )
    metrics = {
        "observed_dates": len(distinct_days),
        "observed_span_days": observed_span,
        "unique_documents": len(records),
        "ready_questions": len(ready),
        "held_documents": len(records) - len(ready),
        "human_reviews": len(reviews),
        "human_review_completion_pct": percent(len(reviews), len(records)),
        "ready_review_completion_pct": percent(len(ready_reviews), len(ready)),
        "pdf_extraction_success_pct": percent(extracted, attempted),
        "grounding_and_scope_exact_pct": percent(grounded, len(ready_reviews)),
        "reporting_start_value_pct": percent(startable, len(ready_reviews)),
        "angle_selection_accuracy_pct": percent(right_angle, len(angle_eligible)),
        "missed_stronger_findings": missed_stronger,
        "valuable_documents": valuable_documents,
        "generic_question_pct": percent(generic, len(ready_reviews)),
        "critical_errors": critical,
        "complete_question_structure_pct": percent(complete, len(ready)),
    }
    observation_ready = (
        len(distinct_days) >= MIN_OBSERVATION_DAYS
        and observed_span >= MIN_OBSERVATION_DAYS
        and len(records) >= MIN_UNIQUE_DOCUMENTS
    )
    human_ready = (
        metrics["human_review_completion_pct"] is not None
        and metrics["human_review_completion_pct"] >= 80
        and metrics["ready_review_completion_pct"] is not None
        and metrics["ready_review_completion_pct"] >= 80
    )
    if not observation_ready:
        outcome = "COLLECTING"
    elif not human_ready:
        outcome = "AWAITING_HUMAN_REVIEW"
    elif (
        (metrics["pdf_extraction_success_pct"] or 0) >= 80
        and (metrics["grounding_and_scope_exact_pct"] or 0) >= 90
        and (metrics["reporting_start_value_pct"] or 0) >= 60
        and (metrics["angle_selection_accuracy_pct"] or 0) >= 90
        and metrics["generic_question_pct"] is not None
        and metrics["generic_question_pct"] <= 20
        and metrics["critical_errors"] == 0
        and metrics["complete_question_structure_pct"] == 100
    ):
        outcome = "ELIGIBLE_FOR_EDITORIAL_L4_DECISION"
    else:
        outcome = "QUALITY_GATES_NOT_MET"
    return {"outcome": outcome, "metrics": metrics, "automatic_promotion": False}


def validate_state(state: dict) -> list[str]:
    errors = []
    if state.get("schema") != 1 or state.get("source_id") != SOURCE_ID:
        errors.append("unexpected shadow state identity")
    if state.get("maturity") != "L3" or state.get("briefing_output") != "NONE":
        errors.append("shadow state must remain L3 and outside briefing")
    if state.get("automatic_ledger_write") is not False or state.get("approved_for_production") is not False:
        errors.append("shadow state cannot edit ledgers or approve production")
    if state.get("raw_reports_persisted") != 0:
        errors.append("raw audit reports must not be persisted")
    records, runs = state.get("records"), state.get("runs")
    if not isinstance(records, list) or len(records) > MAX_RECORDS:
        return errors + ["shadow state record bound exceeded"]
    if not isinstance(runs, list) or len(runs) > MAX_RUNS:
        return errors + ["shadow state run bound exceeded"]
    ids = [item.get("source_record_id") for item in records]
    if len(ids) != len(set(ids)):
        errors.append("duplicate audit records in shadow state")
    if any(not isinstance(record_id, str) or not record_id.isdigit() for record_id in ids):
        errors.append("invalid source record ID")
    if (FORBIDDEN_KEYS | RAW_KEYS) & set(walk_keys(state)):
        errors.append("forbidden editorial or raw-data field in shadow state")
    for item in records:
        card = item.get("card") or {}
        if card.get("raw_report_text_persisted") is not False:
            errors.append("raw report text marker is not false")
        if card.get("source_record_id") != item.get("source_record_id"):
            errors.append("record and card IDs differ")
        url = urlparse(card.get("detail_url") or "")
        if url.scheme != "https" or url.hostname != SAFE_HOST:
            errors.append("non-official audit detail URL")
    return errors


def metric_text(value: float | None) -> str:
    return "판정 대기" if value is None else f"{value}%"


def concise_question(value: str, limit: int = 180) -> str:
    """Show the editorial question, not the attached evidence or test plan."""
    first = (value or "").split("?", 1)[0].strip()
    first = first.replace("감사 감사에서", "감사에서")
    question = first + "?" if first else "질문 미작성"
    return question if len(question) <= limit else question[: limit - 1].rstrip() + "…"


def review_label(review: dict | None, card: dict) -> str:
    if not review:
        return "편집 판정 대기" if card.get("verification_question") else "보류"
    labels = {
        "START_REPORTING": "취재 착수",
        "VERIFY": "추가 확인",
        "REJECT": "이번 질문 제외",
        "CONFIRM_HOLD": "보류 유지",
        "MISSED_VALUE": "가치 있는 지적 재탐색",
    }
    verdict = labels.get(review["verdict"], review["verdict"])
    if review.get("angle_selection") == "MISSED_STRONGER_FINDING":
        verdict += " · 더 강한 지적 재선택 필요"
    return verdict


def render_summary(state: dict, evaluation: dict, reviews: dict[str, dict]) -> str:
    """Keep the human-facing summary brief; detailed evidence stays in bounded state."""
    m = evaluation["metrics"]
    latest_run = state["runs"][-1] if state["runs"] else {}
    latest_ids = set(latest_run.get("selected_ids", []))
    recent = [
        item for item in state["records"]
        if item["source_record_id"] in latest_ids
    ]
    ready = [
        item for item in recent
        if item["card"]["question_status"] == "READY_FOR_HUMAN_REVIEW"
    ]
    held = [item for item in recent if item not in ready]
    prior_reviewed = [
        item for item in state["records"]
        if item["source_record_id"] not in latest_ids
        and item["source_record_id"] in reviews
    ]
    lines = [
        "# 서울시 감사 결과 · 편집 검토",
        "",
        (
            f"**현재 판단:** 평가 진행 중입니다. 서로 다른 {m['observed_dates']}일에 "
            f"{m['unique_documents']}개 문서를 살폈습니다. "
            "아직 L4 승격이나 기사 채택을 뜻하지 않습니다."
            if evaluation["outcome"] == "COLLECTING"
            else f"**현재 판단:** {evaluation['outcome']} — 사람의 최종 판단 전입니다."
        ),
        "",
        (
            f"이번 실행: 새 문서 {len(recent)}건 · 질문 초안 {len(ready)}건 · "
            f"보류 {len(held)}건"
        ),
        "",
        "## 이번에 볼 질문",
        "",
    ]
    if not ready:
        lines.extend(["- 없음", ""])
    else:
        for item in ready:
            card = item["card"]
            record_id = item["source_record_id"]
            lines.extend([
                f"### {card['title']}",
                "",
                f"- 핵심 질문: {concise_question(card.get('verification_question') or '')}",
                f"- 편집 판단: {review_label(reviews.get(record_id), card)}",
                f"- [서울시 공식 문서]({card['detail_url']})",
                "",
            ])
    lines.extend(["## 이번에 보류한 문서", ""])
    if not held:
        lines.extend(["- 없음", ""])
    else:
        for item in held:
            card = item["card"]
            reason = (
                "지적은 확인했지만 기획 질문 기준 미달"
                if card.get("documented_issue_in_table")
                else "감사 지적 목록 확인 실패"
            )
            lines.append(f"- [{card['title']}]({card['detail_url']}): {reason}")
        lines.append("")
    if prior_reviewed:
        lines.extend(["## 이전 문서의 사람 판정", ""])
        for item in prior_reviewed:
            card = item["card"]
            record_id = item["source_record_id"]
            lines.append(
                f"- [{card['title']}]({card['detail_url']}): "
                f"{review_label(reviews[record_id], card)}"
            )
        lines.append("")
    lines.extend([
        "## 평가 진행 상태",
        "",
        (
            f"- 사람 판정 {m['human_reviews']}/{m['unique_documents']}건. "
            "최소 7일·12개 문서와 충분한 사람 판정 전에는 품질 결론을 내리지 않습니다."
        ),
        "- 상세 근거·점검 표시·검증 절차는 이 요약에서 제외하고 내부 파생 상태에만 보존합니다.",
        "- 원문은 저장하지 않으며, 브리핑·아이템 장부로 자동 연결하지 않습니다.",
        "",
    ])
    return "\n".join(lines)


def run(output_dir: Path, state_path: Path, reviews_path: Path, now: datetime | None = None,
        fetcher=fetch_html, collector=collect_l3) -> dict:
    now = now or kst_now()
    today = now.date()
    state = load_state(state_path, now)
    registry = load_registry()
    source = next(row for row in registry["sources"] if row["source_id"] == SOURCE_ID)
    if source["maturity"] != "L3" or source["briefing_output"] != "NONE":
        raise RuntimeError("source registry is no longer L3 shadow-safe")
    if any(item["run_date_kst"] == today.isoformat() for item in state["runs"]):
        reviews = read_reviews(reviews_path, state["records"])
        result = evaluate(state, reviews)
    else:
        observed_at = now.isoformat(timespec="seconds")
        listing_records, listing_diag = discover_records(source, observed_at, today, fetcher)
        seen = {item["source_record_id"] for item in state["records"]}
        selected = select_unseen(listing_records, seen, today)[: max(0, MAX_RECORDS - len(state["records"]))]
        payload = collector(source, observed_at, selected_records=selected)
        errors = validate_l3_output(payload, registry)
        if errors:
            raise RuntimeError("invalid L3 payload: " + "; ".join(errors))
        by_id = {row["source_record_id"]: row for row in selected}
        for card in payload["cards"]:
            record_id = card["source_record_id"]
            published = date.fromisoformat(by_id[record_id]["published_at"])
            cohort = "NEW_30D" if (today - published).days <= FRESH_DAYS else "HISTORICAL_BACKFILL"
            state["records"].append({
                "source_record_id": record_id,
                "first_seen_kst": today.isoformat(),
                "cohort": cohort,
                "card": card,
                "challenge_flags": challenge_card(card),
            })
        state["runs"].append({
            "run_date_kst": today.isoformat(),
            "run_id": os.getenv("GITHUB_RUN_ID") or "MANUAL",
            "listing_status": "SUCCESS" if not listing_diag["listing_errors"] else "PARTIAL",
            "listing_diagnostics": listing_diag,
            "selected_ids": [row["source_record_id"] for row in selected],
            "diagnostics": payload["diagnostics"],
        })
        errors = validate_state(state)
        if errors:
            raise RuntimeError("invalid L4 shadow state: " + "; ".join(errors))
        reviews = read_reviews(reviews_path, state["records"])
        result = evaluate(state, reviews)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "state_latest.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "SUMMARY.md").write_text(render_summary(state, result, reviews), encoding="utf-8")
    print(render_summary(state, result, reviews))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_STATE.parent)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--reviews", type=Path, default=DEFAULT_REVIEWS)
    args = parser.parse_args()
    run(args.output_dir, args.state, args.reviews)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
