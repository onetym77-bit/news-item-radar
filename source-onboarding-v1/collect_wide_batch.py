#!/usr/bin/env python3
"""Read-only first comparison batch across distinct onboarding source families."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
sys.path.insert(0, str(BASE))

from collect_l1_batch import collect_one as collect_audit_listing, fetch_html as fetch_listing_html, parse_environment
from probe_l0_batch import build_observation as probe_access, fetch_url
from source_batch_scorecard import build_scorecard, render_summary
from thin_source_contract import load_registry, validate_thin_observation

TARGET_IDS = (
    "environment_assessment",
    "opengov_approvals",
    "seoul_audit_results",
    "citizen_proposals",
    "district_councils_25",
)
MAX_RECORDS = 20


def now_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")


def load_citizen_module():
    path = ROOT / "citizen-proposal-pilot" / "watch.py"
    spec = importlib.util.spec_from_file_location("citizen_proposal_watch", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("citizen proposal adapter unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record_fingerprint(record_id: str, title: str, url: str, date: str | None) -> str:
    data = "\x1f".join((record_id, title, url, date or ""))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def safe_error_code(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        return f"HTTP_{exc.code}"
    if isinstance(exc, (TimeoutError, URLError)):
        return "NETWORK_OR_TIMEOUT"
    if isinstance(exc, ValueError):
        return "LIST_PARSE_ERROR"
    return "FETCH_OR_ADAPTER_ERROR"


def collect_citizen(source: dict, observed_at: str, fetcher=None, parser=None) -> dict:
    module = load_citizen_module() if fetcher is None or parser is None else None
    fetcher = fetcher or module.fetch
    parser = parser or module.parse_list
    source_url = source["official_url"]
    try:
        html_text, page_hash = fetcher(source_url)
    except Exception as exc:
        return {
            "schema": 1, "source_id": source["source_id"], "maturity": source["maturity"],
            "collected_at_kst": observed_at, "source_url": source_url,
            "access_status": "FAILED", "coverage": "FIRST_OFFICIAL_LIST_PAGE_MAX_20",
            "records": [], "interpretation_status": "NOT_EVALUATED",
            "diagnostics": {"error_code": safe_error_code(exc), "candidate_count": None},
        }
    try:
        proposals = parser(html_text, limit=MAX_RECORDS)
    except Exception as exc:
        proposals = []
        error_code = safe_error_code(exc)
    else:
        error_code = None
    records = []
    for proposal in proposals[:MAX_RECORDS]:
        record_id = str(proposal["proposal_id"])
        title = str(proposal["title"])
        url = str(proposal["source_url"])
        published_at = proposal.get("posted_date")
        records.append({
            "source_record_id": record_id,
            "title": title,
            "detail_url": url,
            "published_at": published_at,
            "published_at_status": "CANDIDATE" if published_at else "UNKNOWN",
            "observed_at_kst": observed_at,
            "access_status": "SUCCESS",
            "body_status": "NOT_FETCHED",
            "content_fingerprint": record_fingerprint(record_id, title, url, published_at),
        })
    return {
        "schema": 1, "source_id": source["source_id"], "maturity": source["maturity"],
        "collected_at_kst": observed_at, "source_url": source_url,
        "access_status": "SUCCESS" if records else "PARTIAL",
        "coverage": "FIRST_OFFICIAL_LIST_PAGE_MAX_20",
        "records": records, "interpretation_status": "NOT_EVALUATED",
        "diagnostics": {
            "error_code": error_code,
            "candidate_count": len(proposals) if records else None,
            "list_sha256": page_hash,
        },
    }


def probe_environment_l1_readiness(source: dict, observed_at: str, fetcher=fetch_listing_html) -> dict:
    status, html_text, fetch_diagnostics = fetcher(source["official_url"])
    diagnostics = dict(fetch_diagnostics)
    if html_text is None:
        resolved = []
        parse_diagnostics = {
            "candidate_count": None,
            "unresolved_detail_url_count": None,
            "date_missing_count": None,
        }
    else:
        resolved, parse_diagnostics = parse_environment(
            html_text, source["official_url"], observed_at
        )
    diagnostics.update(parse_diagnostics)
    diagnostics["resolved_detail_url_count"] = len(resolved)
    readiness = (
        "READY_FOR_L1_PROMOTION"
        if resolved and not parse_diagnostics.get("unresolved_detail_url_count")
        else "L1_ADAPTER_REVIEW"
    )
    return {
        "schema": 1,
        "source_id": source["source_id"],
        "maturity": source["maturity"],
        "collected_at_kst": observed_at,
        "source_url": source["official_url"],
        "access_status": status if html_text is not None else "FAILED",
        "coverage": "ACCESS_ONLY_L1_LINK_READINESS",
        "records": [],
        "interpretation_status": "NOT_EVALUATED",
        "technical_readiness": readiness,
        "diagnostics": diagnostics,
    }


def probe_district(source: dict, observed_at: str, fetcher=fetch_url, source_set: list[dict] | None = None) -> dict:
    if source_set is None:
        source_set = json.loads((ROOT / source["source_set_path"]).read_text(encoding="utf-8"))
    if len(source_set) != 25 or len({row["id"] for row in source_set}) != 25:
        raise ValueError("district source registry must contain 25 unique councils")

    def one(council: dict) -> tuple[str, str, str | None]:
        try:
            status, details = fetcher(council["list_url"], timeout=8)
            return council["id"], status, details.get("error_code")
        except Exception as exc:
            return council["id"], "FAILED", safe_error_code(exc)

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(one, source_set))
    success = sum(status == "SUCCESS" for _, status, _ in outcomes)
    partial = sum(status == "PARTIAL" for _, status, _ in outcomes)
    failed = sum(status == "FAILED" for _, status, _ in outcomes)
    access = "SUCCESS" if success == len(outcomes) else "PARTIAL" if success or partial else "FAILED"
    failed_rows = [
        {"id": council_id, "access_status": status, "error_code": error}
        for council_id, status, error in outcomes if status != "SUCCESS"
    ]
    return {
        "schema": 1, "source_id": source["source_id"], "maturity": source["maturity"],
        "collected_at_kst": observed_at, "source_url": source_set[0]["list_url"],
        "access_status": access, "coverage": "ACCESS_ONLY_25_COUNCIL_LISTS",
        "records": [], "interpretation_status": "NOT_EVALUATED",
        "technical_readiness": "GROUP_ACCESS_REVIEW" if success or partial else "KEEP_L0",
        "diagnostics": {
            "council_total": len(outcomes),
            "council_access_success": success,
            "council_access_partial": partial,
            "council_access_failed": failed,
            "council_failure_summary": ", ".join(
                f"{row['id']}:{row['error_code'] or row['access_status']}"
                for row in failed_rows
            )[:500],
            "councils": [
                {"id": council_id, "access_status": status, "error_code": error}
                for council_id, status, error in outcomes
            ],
        },
    }


def failed_observation(source: dict, observed_at: str, stage: str, exc: Exception) -> dict:
    return {
        "schema": 1, "source_id": source["source_id"], "maturity": source["maturity"],
        "collected_at_kst": observed_at,
        "source_url": source.get("official_url"),
        "access_status": "FAILED", "coverage": stage,
        "records": [], "interpretation_status": "NOT_EVALUATED",
        "diagnostics": {"error_code": safe_error_code(exc), "candidate_count": None},
    }


def collect(registry: dict, observed_at: str, *,
            access_probe=probe_access,
            environment_probe=probe_environment_l1_readiness,
            audit_collector=collect_audit_listing,
            citizen_collector=collect_citizen,
            district_probe=probe_district) -> list[dict]:
    sources = {row["source_id"]: row for row in registry["sources"]}
    observations = []
    for source_id in TARGET_IDS:
        source = sources[source_id]
        stage = "ACCESS_ONLY" if source_id in {
            "environment_assessment", "opengov_approvals", "district_councils_25"
        } else "FIRST_OFFICIAL_LIST_PAGE_MAX_20"
        try:
            if source_id == "environment_assessment":
                row = environment_probe(source, observed_at)
            elif source_id == "opengov_approvals":
                row = access_probe(source, collected_at=observed_at)
            elif source_id == "seoul_audit_results":
                row = audit_collector(source, observed_at)
            elif source_id == "citizen_proposals":
                row = citizen_collector(source, observed_at)
            else:
                row = district_probe(source, observed_at)
        except Exception as exc:
            row = failed_observation(source, observed_at, stage, exc)
        errors = validate_thin_observation(row, registry)
        if errors:
            row = failed_observation(source, observed_at, stage, ValueError("INVALID_OBSERVATION"))
            row["diagnostics"]["validation_errors"] = errors
        observations.append(row)
    return observations


def run(output_dir: Path) -> dict:
    registry = load_registry()
    observed_at = now_kst()
    observations = collect(registry, observed_at)
    scorecard = build_scorecard(observations, registry, [])
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle = {
        "schema": 1,
        "probe": "MULTI_SOURCE_THIN_BATCH",
        "collected_at_kst": observed_at,
        "observations": observations,
    }
    (output_dir / "observations.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "source_scorecard.json").write_text(
        json.dumps(scorecard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary = render_summary(scorecard)
    summary += "\n25개 자치구의회는 이번 실행에서 접속만 시험했습니다. 회의록 표본·편집 가치는 미평가입니다.\n"
    (output_dir / "SUMMARY.md").write_text(summary, encoding="utf-8")
    return scorecard


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=BASE / "output" / "wide-batch")
    args = parser.parse_args()
    print(render_summary(run(args.output_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
