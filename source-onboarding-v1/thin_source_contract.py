#!/usr/bin/env python3
"""Shared fail-closed contract for thin source observations."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent
REGISTRY_PATH = BASE / "source_maturity_registry.json"

QUESTION_ORDER = {"NONE": 0, "VERIFICATION_ONLY": 1, "PRE_EDITORIAL": 2}
BRIEFING_ORDER = {"NONE": 0, "HUMAN_REVIEW_QUEUE": 1, "ACTIVE": 2}
SCHEDULE_ORDER = {"NONE": 0, "MANUAL_PR": 1, "SHADOW": 2, "PRODUCTION": 3}
PERSISTENCE_ORDER = {"NONE": 0, "DERIVED_ONLY": 1, "PRODUCTION_DERIVED": 2}

ACCESS = {"SUCCESS", "PARTIAL", "FAILED", "NOT_ATTEMPTED"}
BODY = {"NOT_FETCHED", "BOUNDED_TEXT", "STRUCTURED", "FAILED"}
DATE_STATUS = {"VERIFIED", "CANDIDATE", "UNKNOWN"}
FORBIDDEN_KEYS = {
    "article_candidate", "article_gate_pass", "harm_confirmed", "victim_count",
    "quality_score", "central_question", "citizen_stake", "full_body",
    "raw_html", "author_name", "email", "phone", "contact",
}
REQUIRED_SOURCE_FIELDS = {
    "source_id", "source_name", "official_url", "maturity", "candidate_role",
    "implementation_path", "question_output", "briefing_output", "schedule",
    "persistence", "automatic_ledger_write", "raw_personal_text_persisted",
    "approved_for_production", "evaluation", "note",
}
REQUIRED_RECORD_FIELDS = {
    "source_record_id", "title", "detail_url", "published_at",
    "published_at_status", "observed_at_kst", "access_status", "body_status",
    "content_fingerprint",
}

def load_registry(path: Path = REGISTRY_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def is_safe_https(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password

def walk_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from walk_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from walk_keys(nested)

def validate_registry(registry: dict, root: Path | None = None) -> list[str]:
    errors = []
    if registry.get("schema") != 1:
        errors.append("registry schema must be 1")
    levels = registry.get("levels")
    if not isinstance(levels, dict) or set(levels) != {f"L{i}" for i in range(6)}:
        errors.append("registry must define L0 through L5")
        levels = {}
    sources = registry.get("sources")
    if not isinstance(sources, list):
        return errors + ["sources must be a list"]
    seen = set()
    for index, source in enumerate(sources):
        where = f"sources[{index}]"
        missing = REQUIRED_SOURCE_FIELDS - set(source)
        if missing:
            errors.append(f"{where} missing fields: {', '.join(sorted(missing))}")
            continue
        source_id = source["source_id"]
        if source_id in seen:
            errors.append(f"duplicate source_id: {source_id}")
        seen.add(source_id)
        maturity = source["maturity"]
        policy = levels.get(maturity)
        if not policy:
            errors.append(f"{source_id}: unknown maturity {maturity}")
            continue
        if source["official_url"] is not None and not is_safe_https(source["official_url"]):
            errors.append(f"{source_id}: official_url must be a safe HTTPS URL or null")
        if maturity != "L0" and not source["official_url"] and not source.get("source_set_path"):
            errors.append(f"{source_id}: L1+ requires official_url or source_set_path")
        path = source.get("implementation_path")
        if path and root is not None and not (root / path).is_file():
            errors.append(f"{source_id}: implementation_path does not exist: {path}")
        source_set = source.get("source_set_path")
        if source_set and root is not None and not (root / source_set).is_file():
            errors.append(f"{source_id}: source_set_path does not exist: {source_set}")
        for field, order, cap_field in (
            ("question_output", QUESTION_ORDER, "max_question_output"),
            ("briefing_output", BRIEFING_ORDER, "max_briefing_output"),
            ("schedule", SCHEDULE_ORDER, "max_schedule"),
            ("persistence", PERSISTENCE_ORDER, "max_persistence"),
        ):
            value = source[field]
            cap = policy[cap_field]
            if value not in order:
                errors.append(f"{source_id}: unknown {field} {value}")
            elif cap not in order or order[value] > order[cap]:
                errors.append(f"{source_id}: {field}={value} exceeds {maturity} cap {cap}")
        if source["automatic_ledger_write"] is not False:
            errors.append(f"{source_id}: automatic ledger writes are forbidden")
        if source["raw_personal_text_persisted"] is not False:
            errors.append(f"{source_id}: raw personal text persistence is forbidden")
        evaluation = source["evaluation"]
        if maturity in {"L4", "L5"}:
            if not isinstance(evaluation, dict):
                errors.append(f"{source_id}: {maturity} requires evaluation")
            else:
                if evaluation.get("window_days", 0) < 7:
                    errors.append(f"{source_id}: evaluation window must be at least 7 days")
                if evaluation.get("review_completion_rate", 0) < 0.8:
                    errors.append(f"{source_id}: review completion rate must be at least 0.8")
        if maturity == "L5" and source["approved_for_production"] is not True:
            errors.append(f"{source_id}: L5 requires explicit production approval")
        if maturity != "L5" and source["approved_for_production"] is not False:
            errors.append(f"{source_id}: only L5 can be production approved")
    return errors

def validate_thin_observation(payload: dict, registry: dict) -> list[str]:
    errors = []
    required = {
        "schema", "source_id", "maturity", "collected_at_kst", "source_url",
        "access_status", "coverage", "records", "interpretation_status",
    }
    missing = required - set(payload)
    if missing:
        return [f"observation missing fields: {', '.join(sorted(missing))}"]
    if payload["schema"] != 1:
        errors.append("observation schema must be 1")
    entries = {row["source_id"]: row for row in registry.get("sources", [])}
    source = entries.get(payload["source_id"])
    if not source:
        errors.append("source_id is not registered")
        return errors
    if payload["maturity"] != source["maturity"]:
        errors.append("observation maturity differs from registry")
    if payload["source_url"] and not is_safe_https(payload["source_url"]):
        errors.append("source_url must be a safe HTTPS URL")
    if payload["access_status"] not in ACCESS:
        errors.append("invalid access_status")
    if payload["interpretation_status"] != "NOT_EVALUATED":
        errors.append("thin observations cannot contain editorial interpretation")
    forbidden = FORBIDDEN_KEYS & set(walk_keys(payload))
    if forbidden:
        errors.append("forbidden thin-observation keys: " + ", ".join(sorted(forbidden)))
    records = payload["records"]
    if not isinstance(records, list):
        return errors + ["records must be a list"]
    if len(records) > 20:
        errors.append("thin observation may contain at most 20 records")
    if payload["access_status"] == "FAILED" and records:
        errors.append("failed access cannot emit records")
    if source["maturity"] == "L0" and records:
        errors.append("L0 access probes cannot emit source records")
    seen_ids = set()
    seen_urls = set()
    for index, record in enumerate(records):
        where = f"records[{index}]"
        missing_record = REQUIRED_RECORD_FIELDS - set(record)
        if missing_record:
            errors.append(f"{where} missing fields: {', '.join(sorted(missing_record))}")
            continue
        record_id = str(record["source_record_id"]).strip()
        if not record_id:
            errors.append(f"{where} has empty source_record_id")
        elif record_id in seen_ids:
            errors.append(f"{where} duplicate source_record_id")
        seen_ids.add(record_id)
        url = record["detail_url"]
        if not is_safe_https(url):
            errors.append(f"{where} detail_url must be safe HTTPS")
        elif url in seen_urls:
            errors.append(f"{where} duplicate detail_url")
        seen_urls.add(url)
        if record["published_at_status"] not in DATE_STATUS:
            errors.append(f"{where} invalid published_at_status")
        if record["published_at_status"] == "VERIFIED" and not record["published_at"]:
            errors.append(f"{where} verified date is empty")
        if record["access_status"] not in ACCESS:
            errors.append(f"{where} invalid access_status")
        if record["body_status"] not in BODY:
            errors.append(f"{where} invalid body_status")
        excerpt = record.get("bounded_excerpt")
        if excerpt is not None and (not isinstance(excerpt, str) or len(excerpt) > 260):
            errors.append(f"{where} bounded_excerpt must be at most 260 characters")
    return errors

def main() -> int:
    root = BASE.parent
    registry = load_registry()
    errors = validate_registry(registry, root)
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors))
        return 1
    print(f"source maturity registry valid: {len(registry['sources'])} sources")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
