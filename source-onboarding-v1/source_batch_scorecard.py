#!/usr/bin/env python3
"""Compare thin-source samples without promoting them into editorial output."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from thin_source_contract import load_registry, validate_thin_observation

REVIEW_LABELS = {"PROMISING", "VERIFY", "NOISE", "DUPLICATE", "UNREADABLE"}
BODY_AVAILABLE = {"BOUNDED_TEXT", "STRUCTURED"}
ACCESS_AVAILABLE = {"SUCCESS", "PARTIAL"}


def ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def load_observations(paths: list[Path]) -> list[dict]:
    observations: list[dict] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("observations"), list):
            observations.extend(payload["observations"])
        elif isinstance(payload, dict) and "source_id" in payload:
            observations.append(payload)
        else:
            raise ValueError(f"{path}: observation or observation bundle required")
    return observations


def load_reviews(path: Path | None) -> tuple[list[dict], list[str]]:
    if path is None:
        return [], []
    errors: list[str] = []
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"source_id", "source_record_id", "label", "reviewed_on", "note"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            return [], ["review CSV missing fields: " + ", ".join(sorted(missing))]
        for line_number, row in enumerate(reader, start=2):
            source_id = (row.get("source_id") or "").strip()
            record_id = (row.get("source_record_id") or "").strip()
            label = (row.get("label") or "").strip().upper()
            key = (source_id, record_id)
            if not source_id or not record_id:
                errors.append(f"review line {line_number}: source_id and source_record_id required")
                continue
            if label not in REVIEW_LABELS:
                errors.append(f"review line {line_number}: invalid label {label!r}")
                continue
            if key in seen:
                errors.append(f"review line {line_number}: duplicate review key")
                continue
            seen.add(key)
            rows.append({
                "source_id": source_id,
                "source_record_id": record_id,
                "label": label,
                "reviewed_on": (row.get("reviewed_on") or "").strip(),
                "note": (row.get("note") or "").strip(),
            })
    return rows, errors


def technical_gate(observation: dict, sample_count: int, body_rate: float | None) -> str:
    access = observation.get("access_status")
    if access in {"FAILED", "NOT_ATTEMPTED"}:
        return "RETRY_ACCESS"
    maturity = observation.get("maturity", "L0")
    if maturity == "L0":
        return "L0_PROBE_ONLY"
    if sample_count == 0:
        return "FIX_LISTING"
    if maturity == "L1":
        return "READY_FOR_L2_SAMPLE"
    if body_rate is None or body_rate < 0.6:
        return "FIX_BODY_EXTRACTION"
    return "READY_FOR_EDITORIAL_SAMPLE"


def editorial_gate(sample_count: int, counts: Counter) -> tuple[str, dict]:
    reviewed = sum(counts.values())
    completion = ratio(reviewed, sample_count)
    useful = counts["PROMISING"] + counts["VERIFY"]
    useful_rate = ratio(useful, reviewed)
    noise_rate = ratio(counts["NOISE"], reviewed)
    duplicate_rate = ratio(counts["DUPLICATE"], reviewed)
    unreadable_rate = ratio(counts["UNREADABLE"], reviewed)
    metrics = {
        "reviewed_count": reviewed,
        "review_completion_rate": completion,
        "promising_count": counts["PROMISING"],
        "verify_count": counts["VERIFY"],
        "noise_count": counts["NOISE"],
        "duplicate_count": counts["DUPLICATE"],
        "unreadable_count": counts["UNREADABLE"],
        "useful_signal_rate": useful_rate,
        "noise_rate": noise_rate,
        "duplicate_rate": duplicate_rate,
        "unreadable_rate": unreadable_rate,
    }
    if reviewed == 0:
        return "NOT_EVALUATED", metrics
    minimum_reviews = min(10, sample_count)
    if reviewed < minimum_reviews or completion is None or completion < 0.8:
        return "INSUFFICIENT_REVIEW", metrics
    if useful_rate is not None and useful_rate >= 0.35 and (noise_rate or 0) <= 0.5:
        return "DEEPEN_CANDIDATE", metrics
    if useful_rate is not None and useful_rate >= 0.15:
        return "AUXILIARY_CANDIDATE", metrics
    return "STOP_OR_VERIFY_ONLY_CANDIDATE", metrics


def score_observation(observation: dict, registry: dict, reviews: list[dict]) -> dict:
    source_id = str(observation.get("source_id") or "UNKNOWN")
    errors = validate_thin_observation(observation, registry)
    if isinstance(observation.get("records"), list) and len(observation["records"]) > 20:
        errors.append("wide screening sample exceeds 20 records")
    if errors:
        return {
            "source_id": source_id,
            "access_status": observation.get("access_status"),
            "content_availability": "UNKNOWN_INVALID_OBSERVATION",
            "technical_gate": "INVALID_OBSERVATION",
            "editorial_gate": "NOT_EVALUATED",
            "errors": errors,
        }

    records = observation["records"]
    sample_count = len(records)
    failed_access = observation["access_status"] in {"FAILED", "NOT_ATTEMPTED"}
    verified_dates = sum(row["published_at_status"] == "VERIFIED" for row in records)
    detail_attempts = sum(row["body_status"] != "NOT_FETCHED" for row in records)
    accessible = sum(
        row["access_status"] in ACCESS_AVAILABLE
        for row in records if row["body_status"] != "NOT_FETCHED"
    )
    body_available = sum(row["body_status"] in BODY_AVAILABLE for row in records)
    unique_fingerprints = len({row["content_fingerprint"] for row in records if row["content_fingerprint"]})
    body_rate = ratio(body_available, detail_attempts)

    record_ids = {str(row["source_record_id"]) for row in records}
    matching_reviews = [
        row for row in reviews
        if row["source_id"] == source_id and row["source_record_id"] in record_ids
    ]
    counts = Counter(row["label"] for row in matching_reviews)
    editorial, review_metrics = editorial_gate(sample_count, counts)
    if observation["maturity"] in {"L0", "L1"} or body_rate is None or body_rate < 0.6:
        editorial = "NOT_READY_FOR_EDITORIAL_REVIEW"
    diagnostics = observation.get("diagnostics") or {}
    candidate_count = diagnostics.get("candidate_count")
    unresolved = diagnostics.get("unresolved_detail_url_count")

    return {
        "source_id": source_id,
        "maturity": observation["maturity"],
        "access_status": observation["access_status"],
        "content_availability": (
            "UNKNOWN_DUE_TO_ACCESS_FAILURE" if failed_access
            else ("SAMPLED" if sample_count else "NO_SAFE_SAMPLE")
        ),
        "sample_count": sample_count,
        "candidate_count": None if failed_access else candidate_count,
        "record_access_rate": None if failed_access else ratio(accessible, detail_attempts),
        "detail_attempt_count": detail_attempts,
        "verified_date_rate": None if failed_access else ratio(verified_dates, sample_count),
        "body_available_rate": None if failed_access else body_rate,
        "unique_content_rate": None if failed_access else ratio(unique_fingerprints, sample_count),
        "unresolved_detail_url_rate": (
            None if failed_access or not isinstance(candidate_count, int)
            else ratio(int(unresolved or 0), candidate_count)
        ),
        "technical_gate": technical_gate(observation, sample_count, body_rate),
        "editorial_gate": "NOT_EVALUATED" if failed_access else editorial,
        "editorial_metrics": review_metrics,
        "errors": [],
    }


def build_scorecard(observations: list[dict], registry: dict, reviews: list[dict]) -> dict:
    seen: set[str] = set()
    sources: list[dict] = []
    for observation in observations:
        source_id = str(observation.get("source_id") or "UNKNOWN")
        if source_id in seen:
            sources.append({
                "source_id": source_id,
                "content_availability": "UNKNOWN_DUPLICATE_OBSERVATION",
                "technical_gate": "INVALID_OBSERVATION",
                "editorial_gate": "NOT_EVALUATED",
                "errors": ["duplicate source observation in comparison batch"],
            })
            continue
        seen.add(source_id)
        sources.append(score_observation(observation, registry, reviews))
    return {
        "schema": 1,
        "evaluation_mode": "THIN_SOURCE_COMPARISON",
        "automatic_maturity_transition": False,
        "question_output": "NONE",
        "briefing_output": "NONE",
        "sources": sources,
    }


def percent(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.0f}%"


def render_summary(scorecard: dict) -> str:
    lines = [
        "# 신규 소스 비교 점수표",
        "",
        "기술 상태와 편집 가치를 분리했습니다. 이 결과는 성숙도 승격·질문 생성·브리핑 편입을 자동 수행하지 않습니다.",
        "",
        "| 소스 | 접근 | 표본 | 본문 확보 | 날짜 검증 | 사람 검토 | 유효 단서 | 기술 판정 | 편집 판정 |",
        "|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in scorecard["sources"]:
        metrics = row.get("editorial_metrics") or {}
        sample = row.get("sample_count")
        sample_text = "-" if sample is None else str(sample)
        lines.append(
            f"| {row['source_id']} | {row.get('access_status') or '-'} | {sample_text} | "
            f"{percent(row.get('body_available_rate'))} | {percent(row.get('verified_date_rate'))} | "
            f"{percent(metrics.get('review_completion_rate'))} | {percent(metrics.get('useful_signal_rate'))} | "
            f"{row['technical_gate']} | {row['editorial_gate']} |"
        )
        for error in row.get("errors") or []:
            lines.append(f"| ↳ 검증 오류 |  |  |  |  |  |  | {error} |  |")
    lines.extend([
        "",
        "## 판정 해석",
        "",
        "- RETRY_ACCESS는 자료 0건이 아니라 접근 실패로 인한 미판정입니다.",
        "- READY_FOR_L2_SAMPLE은 본문 표본 단계로 이동할 기술 조건만 뜻합니다.",
        "- DEEPEN_CANDIDATE·AUXILIARY_CANDIDATE·STOP_OR_VERIFY_ONLY_CANDIDATE는 사람 검토 표본에 근거한 제안이며 자동 승격이 아닙니다.",
        "- 편집 판정에는 표본의 80% 이상과 최소 10건(전체 표본이 10건 미만이면 전수) 검토가 필요합니다.",
        "",
    ])
    return "\n".join(lines)


def run(observation_paths: list[Path], reviews_path: Path | None, output_dir: Path) -> dict:
    registry = load_registry()
    observations = load_observations(observation_paths)
    reviews, review_errors = load_reviews(reviews_path)
    if review_errors:
        raise ValueError("; ".join(review_errors))
    observed_keys = {
        (observation["source_id"], str(record["source_record_id"]))
        for observation in observations for record in observation.get("records", [])
    }
    unknown_reviews = [
        (row["source_id"], row["source_record_id"]) for row in reviews
        if (row["source_id"], row["source_record_id"]) not in observed_keys
    ]
    if unknown_reviews:
        raise ValueError(f"reviews do not match current sample: {unknown_reviews[:5]}")
    scorecard = build_scorecard(observations, registry, reviews)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "source_scorecard.json").write_text(
        json.dumps(scorecard, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "SUMMARY.md").write_text(render_summary(scorecard), encoding="utf-8")
    return scorecard


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observation", type=Path, action="append", required=True)
    parser.add_argument("--reviews-csv", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("source-onboarding-v1/output/source-scorecard"))
    args = parser.parse_args()
    print(render_summary(run(args.observation, args.reviews_csv, args.output_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
