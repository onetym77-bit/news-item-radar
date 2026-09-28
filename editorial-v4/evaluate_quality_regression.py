#!/usr/bin/env python3
"""Evaluate fixed editorial-quality cases without calling a model."""

from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import date
from pathlib import Path


HERE = Path(__file__).resolve().parent
DEFAULT_CASES = HERE / "quality_regression_cases.json"


def load_pipeline():
    spec = importlib.util.spec_from_file_location("editorial_v4_pipeline", HERE / "pipeline.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def evaluate(path: Path = DEFAULT_CASES) -> dict:
    pipeline = load_pipeline()
    document = json.loads(path.read_text(encoding="utf-8"))
    results = []

    for case in document.get("cases", []):
        record = case["record"]
        expected = case["expected_result"]
        if case.get("future_date_check"):
            as_of = date.fromisoformat(case.get("as_of") or document["as_of"])
            actual = "HOLD" if pipeline.future_dated(record, today=as_of) else "PROPOSE"
            detail = "미래 문서일 차단" if actual == "HOLD" else "미래 문서일 아님"
        else:
            proposals, holds = pipeline.assess_result(
                [record],
                {"assessments": [case["assessment"]]},
            )
            actual = "PROPOSE" if proposals else "HOLD"
            detail = proposals[0]["title"] if proposals else holds[0]["reason"]

        results.append(
            {
                "id": case["id"],
                "description": case["description"],
                "expected": expected,
                "actual": actual,
                "passed": actual == expected,
                "detail": detail,
            }
        )

    failed = [row for row in results if not row["passed"]]
    return {
        "schema": document.get("schema", 1),
        "case_count": len(results),
        "passed_count": len(results) - len(failed),
        "failed_count": len(failed),
        "failed": failed,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    args = parser.parse_args()
    report = evaluate(args.cases)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["failed_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
