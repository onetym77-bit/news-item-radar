#!/usr/bin/env python3
"""Compare substantive audit findings and citizen-proposal claims fairly.

The trial reads three recent items per source. Audit evidence comes from public
PDF finding tables; citizen evidence comes from the official proposal body.
Only one redacted excerpt of at most 240 characters is persisted per item.
Labels are human supplied and never inferred automatically.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from collect_l2_equal_sample import load_citizen_module
from interpret_audit_l3 import collect_l3
from thin_source_contract import FORBIDDEN_KEYS, is_safe_https, load_registry, walk_keys

BASE = Path(__file__).resolve().parent
SAMPLE_SIZE = 3
SOURCE_IDS = ("seoul_audit_results", "citizen_proposals")
LABELS = {"PROMISING", "VERIFY", "NOISE", "DUPLICATE", "UNREADABLE"}
REVIEW_COLUMNS = ("source_id", "source_record_id", "label", "reviewed_on", "note")
RAW_KEYS = {"report_text", "pdf_bytes", "raw_pdf", "raw_report", "raw_html", "full_body"}


def now_kst() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def bounded_redacted(module, value: str | None) -> str | None:
    if not value:
        return None
    redacted = module.redact_anchor(value)
    if len(redacted) > 240:
        redacted = redacted[:237].rstrip() + "..."
    return redacted or None


def citizen_body_text(text: str) -> str | None:
    """Remove proposal-page controls and byline before selecting a review excerpt."""
    policy_at = text.find("정책분류")
    if 0 <= policy_at <= 3000 and "시민의견" in text[:policy_at]:
        remainder = text[policy_at + len("정책분류"):].strip()
        category_and_body = remainder.split(None, 1)
        if len(category_and_body) != 2:
            return None
        text = category_and_body[1]
    elif "스크랩 공유" in text[:1500] or "시민의견" in text[:1500]:
        # A changed page layout must not turn controls or an author byline into evidence.
        return None
    for boundary in ("관련 제안", "다른 제안", "댓글 목록", "의견 목록"):
        position = text.find(boundary)
        if position > 0:
            text = text[:position]
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) >= 30 else None


def citizen_review_excerpt(module, title: str, text: str, classified: dict) -> str | None:
    anchor = module.evidence_anchor(text, classified["statement_type"], classified["matched_basis"])
    if anchor.get("excerpt"):
        return bounded_redacted(module, anchor["excerpt"])
    basis = classified.get("matched_basis") or {}
    for group in ("friction_terms", "first_person_terms", "hearsay_terms", "idea_terms"):
        positions = [text.find(term) for term in basis.get(group, []) if term and text.find(term) >= 0]
        if positions:
            start = max(0, min(positions) - 40)
            return bounded_redacted(module, text[start:start + 340])
    return None


def audit_cards(source: dict, observed_at: str, *, collector=collect_l3, citizen_module=None) -> tuple[list[dict], dict]:
    module = citizen_module or load_citizen_module()
    payload = collector(source, observed_at)
    cards = []
    for row in payload.get("cards", [])[:SAMPLE_SIZE]:
        selected = row.get("selected_finding_title")
        excerpt = bounded_redacted(module, selected)
        finding_options = [
            bounded_redacted(module, title)
            for title in row.get("review_finding_titles", [])[:5]
        ]
        finding_options = [title for title in finding_options if title]
        if excerpt and excerpt not in finding_options:
            finding_options.insert(0, excerpt)
        finding_options = finding_options[:5]
        body_status = (
            "READABLE_FINDING"
            if excerpt and row.get("documented_issue_in_table")
            else "UNREADABLE"
        )
        cards.append({
            "source_id": source["source_id"],
            "source_record_id": str(row["source_record_id"]),
            "title": row["title"],
            "detail_url": row["detail_url"],
            "published_at": row.get("published_at"),
            "evidence_kind": "OFFICIAL_AUDIT_FINDING",
            "evidence_status": (
                "OFFICIAL_DOCUMENTED_FINDING"
                if body_status == "READABLE_FINDING"
                else "NOT_CONFIRMED_IN_SAMPLED_PAGES"
            ),
            "body_status": body_status,
            "review_excerpt": excerpt,
            "review_finding_options": finding_options,
            "raw_body_persisted": False,
            "human_label": None,
        })
    return cards, payload.get("diagnostics") or {}


def citizen_cards(source: dict, observed_at: str, *, module=None, fetcher=None) -> tuple[list[dict], dict]:
    module = module or load_citizen_module()
    fetcher = fetcher or module.fetch
    diagnostics = {
        "listing_error_code": None,
        "detail_requested": 0,
        "detail_readable": 0,
        "detail_failed": 0,
    }
    try:
        listing_html, _ = fetcher(source["official_url"])
        proposals = module.parse_list(listing_html, limit=SAMPLE_SIZE)
    except Exception as exc:
        diagnostics["listing_error_code"] = type(exc).__name__
        return [], diagnostics

    cards = []
    for proposal in proposals[:SAMPLE_SIZE]:
        diagnostics["detail_requested"] += 1
        try:
            detail_html, _ = fetcher(proposal["source_url"])
            detail_text = module.relevant_detail_text(detail_html, proposal["title"])
            detail_text = citizen_body_text(detail_text) if detail_text is not None else None
        except Exception:
            detail_text = None
        if detail_text is None:
            diagnostics["detail_failed"] += 1
            classified = {
                "statement_type": "UNRESOLVED",
                "matched_basis": {},
            }
            excerpt = None
        else:
            classified = module.classify_text(detail_text)
            excerpt = citizen_review_excerpt(module, proposal["title"], detail_text, classified)
            if excerpt:
                diagnostics["detail_readable"] += 1
            else:
                diagnostics["detail_failed"] += 1
        cards.append({
            "source_id": source["source_id"],
            "source_record_id": str(proposal["proposal_id"]),
            "title": proposal["title"],
            "detail_url": proposal["source_url"],
            "published_at": proposal.get("posted_date"),
            "evidence_kind": "CITIZEN_PROPOSAL_CLAIM",
            "evidence_status": "UNVERIFIED_CLAIM",
            "body_status": "READABLE_CLAIM" if excerpt else "UNREADABLE",
            "statement_type": classified["statement_type"],
            "review_excerpt": excerpt,
            "raw_body_persisted": False,
            "human_label": None,
        })
    return cards, diagnostics


def read_reviews(path: Path | None, cards: list[dict]) -> dict[tuple[str, str], dict]:
    if path is None or not path.exists():
        return {}
    allowed = {(row["source_id"], row["source_record_id"]) for row in cards}
    reviews = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not set(REVIEW_COLUMNS).issubset(reader.fieldnames or []):
            raise ValueError("review CSV is missing required columns")
        for line, raw in enumerate(reader, start=2):
            source_id = (raw.get("source_id") or "").strip()
            record_id = (raw.get("source_record_id") or "").strip()
            label = (raw.get("label") or "").strip().upper()
            if not label:
                continue
            key = (source_id, record_id)
            if key not in allowed:
                raise ValueError(f"review line {line}: record is not in the current sample")
            if key in reviews:
                raise ValueError(f"review line {line}: duplicate record")
            if label not in LABELS:
                raise ValueError(f"review line {line}: invalid label")
            reviews[key] = {
                "label": label,
                "reviewed_on": (raw.get("reviewed_on") or "").strip(),
                "note": (raw.get("note") or "").strip()[:300],
            }
    return reviews


def attach_reviews(cards: list[dict], reviews: dict[tuple[str, str], dict]) -> None:
    for card in cards:
        review = reviews.get((card["source_id"], card["source_record_id"]))
        card["human_label"] = review["label"] if review else None


def source_metrics(cards: list[dict], source_id: str) -> dict:
    rows = [row for row in cards if row["source_id"] == source_id]
    labels = Counter(row["human_label"] for row in rows if row["human_label"])
    reviewed = sum(labels.values())
    useful = labels["PROMISING"] + labels["VERIFY"]
    return {
        "source_id": source_id,
        "sample_target": SAMPLE_SIZE,
        "sample_count": len(rows),
        "readable_count": sum(row["body_status"] != "UNREADABLE" for row in rows),
        "reviewed_count": reviewed,
        "review_completion_rate": round(reviewed / len(rows), 4) if rows else None,
        "promising_count": labels["PROMISING"],
        "verify_count": labels["VERIFY"],
        "noise_count": labels["NOISE"],
        "duplicate_count": labels["DUPLICATE"],
        "unreadable_count": labels["UNREADABLE"],
        "useful_signal_rate": round(useful / reviewed, 4) if reviewed else None,
        "editorial_result": (
            "SOURCE_UNAVAILABLE" if not rows else
            "SAMPLE_INCOMPLETE" if len(rows) < SAMPLE_SIZE else
            "HUMAN_REVIEW_REQUIRED" if reviewed < len(rows) else
            "COMPARABLE_SAMPLE_COMPLETE"
        ),
    }


def validate_payload(payload: dict) -> list[str]:
    errors = []
    cards = payload.get("cards")
    if not isinstance(cards, list):
        return ["cards must be a list"]
    counts = Counter(row.get("source_id") for row in cards)
    for source_id in SOURCE_IDS:
        if counts[source_id] > SAMPLE_SIZE:
            errors.append(f"{source_id}: sample exceeds {SAMPLE_SIZE}")
    if (FORBIDDEN_KEYS | RAW_KEYS) & set(walk_keys(payload)):
        errors.append("raw or editorial output field found")
    seen = set()
    for index, card in enumerate(cards):
        key = (card.get("source_id"), card.get("source_record_id"))
        if key in seen:
            errors.append(f"cards[{index}] duplicate record")
        seen.add(key)
        if card.get("source_id") not in SOURCE_IDS:
            errors.append(f"cards[{index}] unexpected source")
        if not is_safe_https(card.get("detail_url")):
            errors.append(f"cards[{index}] unsafe detail URL")
        excerpt = card.get("review_excerpt")
        if excerpt is not None and (not isinstance(excerpt, str) or len(excerpt) > 240):
            errors.append(f"cards[{index}] review excerpt exceeds 240 chars")
        options = card.get("review_finding_options", [])
        if (
            not isinstance(options, list) or len(options) > 5
            or any(not isinstance(option, str) or len(option) > 240 for option in options)
        ):
            errors.append(f"cards[{index}] invalid bounded finding options")
        if card.get("raw_body_persisted") is not False:
            errors.append(f"cards[{index}] raw body marker must be false")
        if card.get("human_label") not in LABELS | {None}:
            errors.append(f"cards[{index}] invalid human label")
    return errors


def write_review_queue(cards: list[dict], path: Path) -> None:
    fieldnames = [
        "source_id", "source_record_id", "title", "detail_url", "published_at",
        "evidence_kind", "evidence_status", "review_excerpt", "other_findings",
        "label", "reviewed_on", "note",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in cards:
            writer.writerow({
                **{key: row.get(key) or "" for key in fieldnames},
                "other_findings": " | ".join(
                    option for option in row.get("review_finding_options", [])
                    if option != row.get("review_excerpt")
                ),
                "label": row.get("human_label") or "",
            })


def percent(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.0f}%"


def render_summary(payload: dict) -> str:
    labels = {
        "seoul_audit_results": "서울시 감사 결과",
        "citizen_proposals": "상상대로 서울 시민제안",
    }
    lines = [
        "# 실질 본문 기준 소스 비교",
        "",
        "감사 결과는 첨부 공개문의 공식 지적, 시민제안은 상세 화면의 제안자 주장을 각각 읽었습니다. 두 소스 모두 최근 3건을 같은 사람 판정표에 넣었으며 자동으로 아이템 가치를 판정하지 않았습니다.",
        "",
        "| 소스 | 목표/확보 | 읽을 수 있는 근거 | 사람 판정 | 유효 단서율 | 상태 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    metrics_by_id = {row["source_id"]: row for row in payload["metrics"]}
    for source_id in SOURCE_IDS:
        row = metrics_by_id[source_id]
        lines.append(
            f"| {labels[source_id]} | {row['sample_target']}/{row['sample_count']} | "
            f"{row['readable_count']} | {row['reviewed_count']} | "
            f"{percent(row['useful_signal_rate'])} | {row['editorial_result']} |"
        )
    lines.extend([
        "",
        "## 동일 판정 기준",
        "",
        "- PROMISING: 구체적 문제, 의미 있는 시민·공공 영향, 확인 가능한 기록이나 현장이 함께 보입니다.",
        "- VERIFY: 문제 가능성은 있으나 실제 사례·규모·책임 주체 중 하나 이상을 더 확인해야 합니다.",
        "- NOISE: 해결책 제안이나 일반 주장에 머물거나 공익적 영향이 약합니다.",
        "- DUPLICATE: 이미 본 사안과 사실상 같습니다.",
        "- UNREADABLE: 실질 본문 또는 판단 가능한 문장을 확보하지 못했습니다.",
        "",
        "공식 감사 지적은 사실성의 출발점이 강하고 시민제안은 당사자 주장과 현장 단서에 강할 수 있습니다. 출처의 공식성 자체를 PROMISING 점수로 바꾸지 않습니다.",
        "",
        "## 사람 검토 카드",
        "",
    ])
    for source_id in SOURCE_IDS:
        lines.extend([f"### {labels[source_id]}", ""])
        rows = [row for row in payload["cards"] if row["source_id"] == source_id]
        if not rows:
            lines.extend(["- 접근 실패 또는 표본 없음", ""])
            continue
        for row in rows:
            fact = "공식 지적" if row["evidence_kind"] == "OFFICIAL_AUDIT_FINDING" else "미확인 시민 주장"
            lines.extend([
                f"#### {row['title']}",
                "",
                f"- 근거 성격: {fact}",
                f"- 검토 문장: {row.get('review_excerpt') or '본문 확인 실패'}",
            ])
            alternatives = [
                option for option in row.get("review_finding_options", [])
                if option != row.get("review_excerpt")
            ]
            if alternatives:
                lines.append("- 같은 감사의 다른 지적 후보(최대 4개): " + " / ".join(alternatives))
            lines.extend([
                f"- 사람 판정: {row.get('human_label') or '대기'}",
                f"- [공식 원문]({row['detail_url']})",
                "",
            ])
    lines.extend([
        "## 해석 한계",
        "",
        "- 최신 3건 기준이라 두 소스의 게시 빈도와 같은 기간 생산량은 비교하지 않습니다. 감사 문서는 여러 지적이 묶인 단위이며 후보 표시는 최대 5건으로 제한됩니다.",
        "- 시민제안 문장은 사실 확인 전 주장이고, 감사 지적도 현재까지 문제가 계속된다는 뜻은 아닙니다.",
        "- 사람 판정이 끝나기 전에는 어느 소스가 더 유망하다고 결론 내리지 않습니다.",
        "- 이 결과는 질문·브리핑·아이템 장부로 자동 이동하지 않습니다.",
        "",
    ])
    return "\n".join(lines)


def collect(registry: dict, observed_at: str, *, audit_collector=collect_l3,
            citizen_module=None, citizen_fetcher=None) -> tuple[list[dict], dict]:
    sources = {row["source_id"]: row for row in registry["sources"]}
    module = citizen_module or load_citizen_module()
    audits, audit_diagnostics = audit_cards(
        sources["seoul_audit_results"], observed_at,
        collector=audit_collector, citizen_module=module,
    )
    citizens, citizen_diagnostics = citizen_cards(
        sources["citizen_proposals"], observed_at,
        module=module, fetcher=citizen_fetcher,
    )
    return audits + citizens, {
        "seoul_audit_results": audit_diagnostics,
        "citizen_proposals": citizen_diagnostics,
    }


def run(output_dir: Path, reviews_path: Path | None = None) -> dict:
    registry = load_registry()
    observed_at = now_kst()
    cards, diagnostics = collect(registry, observed_at)
    reviews = read_reviews(reviews_path, cards)
    attach_reviews(cards, reviews)
    payload = {
        "schema": 1,
        "trial": "SUBSTANTIVE_BODY_SOURCE_COMPARISON",
        "collected_at_kst": observed_at,
        "sample_size_per_source": SAMPLE_SIZE,
        "question_output": "NONE",
        "briefing_output": "NONE",
        "automatic_ledger_write": False,
        "raw_bodies_persisted": 0,
        "cards": cards,
        "metrics": [source_metrics(cards, source_id) for source_id in SOURCE_IDS],
        "diagnostics": diagnostics,
    }
    errors = validate_payload(payload)
    if errors:
        raise RuntimeError("; ".join(errors))
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "comparison.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_review_queue(cards, output_dir / "human_review_queue.csv")
    summary = render_summary(payload)
    (output_dir / "SUMMARY.md").write_text(summary, encoding="utf-8")
    print(summary)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BASE / "output" / "substantive-comparison",
    )
    parser.add_argument("--reviews-csv", type=Path)
    args = parser.parse_args()
    run(args.output_dir, args.reviews_csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
