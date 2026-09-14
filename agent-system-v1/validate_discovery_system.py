from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYSTEM = ROOT / "agent-system-v1"
LEDGER = SYSTEM / "ITEM_LEDGER.csv"
CONFIG = ROOT / "interest-radar-v2" / "config" / "editorial_lenses.json"
QUESTION_AUDIT = SYSTEM / "QUESTION_QUALITY_AUDIT.csv"

REQUIRED_FILES = [
    SYSTEM / "SYSTEM_MANIFEST.md",
    SYSTEM / "AGENT_POLICY.md",
    SYSTEM / "QUESTION_QUALITY_GATE.md",
    SYSTEM / "ORIGINALITY_AND_TEST_GATE.md",
    QUESTION_AUDIT,
    SYSTEM / "SOURCE_FAMILY_REGISTRY.md",
    SYSTEM / "RUN_METRICS_TEMPLATE.md",
    SYSTEM / "EDITOR_FEEDBACK.md",
    ROOT / "daily-briefing-v4" / "EDITORIAL_GATE.md",
    ROOT / "daily-briefing-v4" / "OUTPUT_TEMPLATE.md",
    ROOT / "interest-radar-v2" / "DESIGN.md",
    CONFIG,
    ROOT / "interest-radar-v2" / "collect_source_material_v2_1.py",
]

REQUIRED_COLUMNS = {
    "item_id",
    "canonical_topic",
    "status",
    "stage_s",
    "editorial_e",
    "production_p",
    "source_report",
    "source_families",
    "scene_status",
    "upstream_gate",
    "structural_question",
    "question_gate",
    "question_hypothesis",
}
VALID_STAGES = {"S0", "S1", "S2", "S3"}
VALID_EDITORIAL = {"E0", "E1", "E2", "E3"}
VALID_PRODUCTION = {"미판정", "P0", "P1", "P2", "P3"}
VALID_SCENES = {"관찰됨", "당사자 진술", "간접 보도", "취재 예정", "없음"}
VALID_FAMILIES = {
    "PRICE",
    "BEHAVIOR",
    "VOICE",
    "FIELD",
    "INDUSTRY",
    "PUBLIC",
    "MEDIA",
    "SOCIAL",
}
S2_SCENES = {"관찰됨", "당사자 진술"}
VALID_UPSTREAM_GATES = {"PASS", "HOLD", "FAIL"}
REQUIRED_CORE_AGENDAS = {
    "HOUSING",
    "LABOR",
    "CARE_HEALTH",
    "MOBILITY",
    "COST_OF_LIVING",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="서울 기획 아이템 발굴 시스템 v1.6 검증")
    parser.add_argument("--briefing", type=Path, help="계측 모순까지 확인할 브리핑 파일")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument(
        "--allow-missing-source-reports",
        action="store_true",
        help="온라인 스냅샷에서 제외된 과거 source_report 파일의 존재 검사를 생략",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    errors: list[str] = []
    warnings: list[str] = []

    for path in REQUIRED_FILES:
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"필수 파일 누락 또는 빈 파일: {path.relative_to(ROOT)}")

    rows: list[dict[str, str]] = []
    if LEDGER.is_file():
        with LEDGER.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = set(reader.fieldnames or [])
            missing = REQUIRED_COLUMNS - columns
            if missing:
                errors.append("장부 필수 열 누락: " + ", ".join(sorted(missing)))
            rows = list(reader)

    seen_ids: set[str] = set()
    seen_topics: dict[str, str] = {}
    missing_source_reports = 0
    for row_number, row in enumerate(rows, start=2):
        item_id = (row.get("item_id") or "").strip()
        topic = (row.get("canonical_topic") or "").strip()
        stage = (row.get("stage_s") or "").strip()
        editorial = (row.get("editorial_e") or "").strip()
        production = (row.get("production_p") or "").strip()
        scene = (row.get("scene_status") or "").strip()
        upstream_gate = (row.get("upstream_gate") or "").strip()
        structural_question = (row.get("structural_question") or "").strip()
        question_gate = (row.get("question_gate") or "").strip()
        question_hypothesis = (row.get("question_hypothesis") or "").strip()
        family_text = (row.get("source_families") or "").strip()
        families = {part.strip() for part in family_text.split("|") if part.strip()}

        if not item_id:
            errors.append(f"{row_number}행: item_id 없음")
        elif item_id in seen_ids:
            errors.append(f"{row_number}행: 중복 item_id {item_id}")
        seen_ids.add(item_id)

        if topic in seen_topics:
            warnings.append(
                f"{row_number}행: 정규화 주제 중복 가능 {topic} "
                f"({seen_topics[topic]}, {item_id})"
            )
        elif topic:
            seen_topics[topic] = item_id

        if stage not in VALID_STAGES:
            errors.append(f"{item_id}: 잘못된 stage_s {stage!r}")
        if editorial not in VALID_EDITORIAL:
            errors.append(f"{item_id}: 잘못된 editorial_e {editorial!r}")
        if production not in VALID_PRODUCTION:
            errors.append(f"{item_id}: 잘못된 production_p {production!r}")
        if scene not in VALID_SCENES:
            errors.append(f"{item_id}: 잘못된 scene_status {scene!r}")
        if upstream_gate not in VALID_UPSTREAM_GATES:
            errors.append(f"{item_id}: 잘못된 upstream_gate {upstream_gate!r}")
        if question_gate not in VALID_UPSTREAM_GATES:
            errors.append(f"{item_id}: 잘못된 question_gate {question_gate!r}")

        unknown_families = families - VALID_FAMILIES
        if unknown_families:
            errors.append(
                f"{item_id}: 알 수 없는 source_families "
                + "|".join(sorted(unknown_families))
            )
        if stage in {"S1", "S2", "S3"} and not families:
            errors.append(f"{item_id}: S1 이상인데 source_families 없음")
        if stage in {"S1", "S2", "S3"} and not structural_question:
            errors.append(f"{item_id}: S1 이상인데 structural_question 없음")
        if stage in {"S1", "S2", "S3"} and question_gate != "PASS":
            errors.append(f"{item_id}: {stage}인데 question_gate={question_gate}")
        if question_gate == "PASS" and not question_hypothesis:
            errors.append(f"{item_id}: question_gate=PASS인데 question_hypothesis 없음")
        if stage in {"S0", "S1"} and production != "미판정":
            errors.append(f"{item_id}: {stage}인데 production_p={production}")
        if stage in {"S2", "S3"}:
            if upstream_gate != "PASS":
                errors.append(f"{item_id}: {stage}인데 기사 게이트(upstream_gate)={upstream_gate}")
            if len(families) < 2:
                errors.append(f"{item_id}: {stage}인데 독립 출처군이 2개 미만")
            if scene not in S2_SCENES:
                errors.append(f"{item_id}: {stage}인데 scene_status={scene}")

        report = (row.get("source_report") or "").strip()
        if report and not (ROOT / report).is_file():
            if args.allow_missing_source_reports:
                missing_source_reports += 1
            else:
                errors.append(f"{item_id}: source_report 파일 없음 {report}")

        review_by = (row.get("review_by") or "").strip()
        if review_by:
            try:
                due = date.fromisoformat(review_by)
                if due < args.as_of and row.get("status") not in {"탈락", "채택"}:
                    warnings.append(f"{item_id}: review_by 경과 {review_by}")
            except ValueError:
                errors.append(f"{item_id}: 잘못된 review_by {review_by!r}")

    if missing_source_reports:
        warnings.append(
            "온라인 스냅샷에서 제외된 source_report "
            f"{missing_source_reports}건의 파일 존재 검사를 생략함"
        )

    audit_rows: dict[str, dict[str, str]] = {}
    if QUESTION_AUDIT.is_file():
        with QUESTION_AUDIT.open("r", encoding="utf-8-sig", newline="") as handle:
            audit_reader = csv.DictReader(handle)
            required_audit_columns = {
                "item_id",
                "reviewed_on",
                "quality_gate",
                "quality_score",
                "central_question",
                "citizen_stake",
                "competing_hypotheses",
                "decision_rule",
            }
            missing_audit_columns = required_audit_columns - set(audit_reader.fieldnames or [])
            if missing_audit_columns:
                errors.append("질문 품질 장부 필수 열 누락: " + ", ".join(sorted(missing_audit_columns)))
            for audit_row in audit_reader:
                audit_id = (audit_row.get("item_id") or "").strip()
                if audit_id in audit_rows:
                    errors.append(f"질문 품질 장부 중복 item_id {audit_id}")
                audit_rows[audit_id] = audit_row
                gate = (audit_row.get("quality_gate") or "").strip()
                score_text = (audit_row.get("quality_score") or "").strip()
                if score_text == "N/A":
                    if gate not in {"HOLD", "FAIL"}:
                        errors.append(f"{audit_id}: 품질 {gate}인데 점수가 N/A")
                    score = None
                else:
                    try:
                        score = int(score_text)
                    except ValueError:
                        errors.append(f"{audit_id}: 질문 품질 점수가 정수 또는 N/A가 아님")
                        continue
                    if not 0 <= score <= 12:
                        errors.append(f"{audit_id}: 질문 품질 점수 범위 오류 {score}")
                    if gate == "PASS" and score < 8:
                        errors.append(f"{audit_id}: 품질 PASS인데 점수 {score}/12")
                    if gate == "HOLD" and score < 5:
                        errors.append(f"{audit_id}: 품질 HOLD인데 점수 {score}/12")
                    if gate == "FAIL" and score > 4:
                        errors.append(f"{audit_id}: 품질 FAIL인데 점수 {score}/12")
                if gate not in VALID_UPSTREAM_GATES:
                    errors.append(f"{audit_id}: 잘못된 quality_gate {gate!r}")
                if gate == "PASS":
                    for field in ("central_question", "citizen_stake", "competing_hypotheses", "decision_rule"):
                        if not (audit_row.get(field) or "").strip():
                            errors.append(f"{audit_id}: 품질 PASS인데 {field} 없음")
                    hypotheses = (audit_row.get("competing_hypotheses") or "")
                    if "A:" not in hypotheses or "B:" not in hypotheses:
                        errors.append(f"{audit_id}: 경쟁 가설 A/B가 모두 없음")
                    decision_rule = (audit_row.get("decision_rule") or "")
                    for path_label in ("전환:", "축소:", "폐기:"):
                        if path_label not in decision_rule:
                            errors.append(f"{audit_id}: 판정선에 {path_label} 없음")

    for row in rows:
        item_id = (row.get("item_id") or "").strip()
        if row.get("status") in {"탈락", "채택"}:
            continue
        ledger_gate = (row.get("question_gate") or "").strip()
        audit_row = audit_rows.get(item_id)
        if not audit_row:
            errors.append(f"{item_id}: 활성 후보인데 질문 품질 재심사 장부에 없음")
            continue
        audit_gate = (audit_row.get("quality_gate") or "").strip()
        if ledger_gate != audit_gate:
            errors.append(f"{item_id}: ITEM_LEDGER question_gate={ledger_gate}, 품질 장부={audit_gate}")

    if CONFIG.is_file():
        try:
            config = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
            if config.get("system_version") != "1.6":
                errors.append("관심 레이더 system_version은 1.6이어야 함")
            agendas = {
                entry.get("code")
                for entry in config.get("agenda_domains", [])
                if isinstance(entry, dict) and entry.get("core_daily") is True
            }
            missing_agendas = REQUIRED_CORE_AGENDAS - agendas
            if missing_agendas:
                errors.append(
                    "관심 레이더 핵심 생활 의제 설정 누락: "
                    + ", ".join(sorted(missing_agendas))
                )
            framework = config.get("question_framework", {})
            required_axes = set(framework.get("required_axes", [])) if isinstance(framework, dict) else set()
            missing_axes = {"분포", "비교", "원인·결과"} - required_axes
            if missing_axes:
                errors.append("질문 프레임 필수 축 누락: " + ", ".join(sorted(missing_axes)))
            entry_requirements = set(framework.get("entry_requirements", []))
            missing_entries = {"근거 앵커", "객관적 현상", "시민 이해관계", "검증 경로"} - entry_requirements
            if missing_entries:
                errors.append("질문 품질 진입 조건 누락: " + ", ".join(sorted(missing_entries)))
            quality_dimensions = set(framework.get("quality_dimensions", []))
            required_quality_dimensions = {
                "긴장·반전",
                "시민 손실·권리",
                "분포·배제",
                "경쟁 가설",
                "책임·변경 가능성",
                "반증·판정선",
            }
            missing_quality = required_quality_dimensions - quality_dimensions
            if missing_quality:
                errors.append("질문 품질 평가 항목 누락: " + ", ".join(sorted(missing_quality)))
            mandatory_dimensions = set(framework.get("mandatory_dimensions", []))
            required_mandatory = {"시민 손실·권리", "경쟁 가설", "반증·판정선"}
            if not required_mandatory.issubset(mandatory_dimensions):
                errors.append("질문 품질 필수 항목 설정 누락")
            if framework.get("evidence_anchor_required") is not True:
                errors.append("질문 점수 전 근거 앵커가 필요함")
            if set(framework.get("evidence_anchor_routes", [])) != {"구체적인 문제 징후", "분해 가능한 구조 자료"}:
                errors.append("근거 앵커는 문제 징후·구조 자료 두 경로여야 함")
            if framework.get("administrative_record_alone_fails") is not True:
                errors.append("사업명·단일 행정기록만인 질문은 진입 FAIL이어야 함")
            if framework.get("unscored_gate_value") != "N/A":
                errors.append("진입 전 미채점 값은 N/A여야 함")
            if framework.get("pass_score") != 8 or framework.get("max_score") != 12:
                errors.append("질문 품질 PASS 기준은 8/12여야 함")
            if framework.get("minimum_competing_hypotheses") != 2:
                errors.append("질문 PASS의 최소 경쟁 가설 수는 2여야 함")
            if framework.get("central_question_limit") != 1:
                errors.append("후보별 중심 질문은 1개여야 함")
            if set(framework.get("required_decision_paths", [])) != {"기사 전환", "축소", "폐기"}:
                errors.append("질문 판정선은 기사 전환·축소·폐기를 모두 포함해야 함")
            if framework.get("template_question_score_cap") != 7:
                errors.append("템플릿 질문 점수 상한은 7이어야 함")
            if framework.get("originality_gate_required") is not True:
                errors.append("질문 우선 검증 전 독창성 게이트가 필요함")
            if framework.get("minimum_test_max_hours") != 24:
                errors.append("일일 우선 검증 최소 판정은 24시간 이내여야 함")
            if set(framework.get("required_evidence_searches", [])) != {"시민 손실", "반대 근거"}:
                errors.append("우선 검증은 시민 손실·반대 근거 검색을 모두 포함해야 함")
            if framework.get("public_origin_correction_threshold") != 0.6:
                errors.append("공공 출발 편중 보정 임계값은 0.6이어야 함")
            youtube = config.get("youtube_discovery", {})
            if youtube.get("version") != "2.3":
                errors.append("유튜브 발견 활성 버전은 2.3이어야 함")
            if youtube.get("queries_per_run") != 4:
                errors.append("유튜브 예약 회차 검색 의제 수는 4여야 함")
            if youtube.get("expressions_per_agenda_per_run") != 2:
                errors.append("유튜브 의제별 회차 검색 표현 수는 2여야 함")
            if youtube.get("lookback_days") != 30:
                errors.append("유튜브 검색창은 누적 관찰창과 같은 30일이어야 함")
            if youtube.get("persistence_days") != 30:
                errors.append("유튜브 반복 현상 관찰창은 30일이어야 함")
            query_agendas = {
                row.get("agenda") for row in config.get("youtube_cluster_queries", [])
                if isinstance(row, dict)
            }
            all_agendas = {
                row.get("code") for row in config.get("agenda_domains", [])
                if isinstance(row, dict)
            }
            missing_youtube_queries = all_agendas - query_agendas
            if missing_youtube_queries:
                errors.append("유튜브 시민 표현 검색이 없는 의제: " + ", ".join(sorted(missing_youtube_queries)))
            required_lanes = {"BEHAVIOR", "EVIDENCE", "SCENE", "SOURCE"}
            invalid_lane_rows = []
            for row in config.get("youtube_cluster_queries", []):
                lanes = row.get("search_lanes", [])
                lane_names = {lane.get("lane") for lane in lanes if isinstance(lane, dict)}
                if lane_names != required_lanes or any(not lane.get("query") for lane in lanes if isinstance(lane, dict)):
                    invalid_lane_rows.append(row.get("cluster", "이름 없음"))
            if invalid_lane_rows:
                errors.append("유튜브 행동·증거·장면·당사자 검색 레인이 불완전한 군집: " + ", ".join(invalid_lane_rows))
            missing_anchor_rows = [
                row.get("cluster", "이름 없음")
                for row in config.get("youtube_cluster_queries", [])
                if not isinstance(row.get("anchor_terms"), list) or len(row.get("anchor_terms", [])) < 2
            ]
            if missing_anchor_rows:
                errors.append("유튜브 검색 결과 재검사용 주제 앵커가 부족한 군집: " + ", ".join(missing_anchor_rows))
            if len(config.get("youtube_seoul_place_terms", [])) < 25:
                errors.append("유튜브 서울 장소 사전은 25개 자치구 이상을 포함해야 함")
            if youtube.get("query_health_min_runs") != 3:
                errors.append("유튜브 검색식 건강도 최소 관찰 횟수는 3회여야 함")
        except (json.JSONDecodeError, OSError) as exc:
            errors.append(f"관심 레이더 설정을 읽을 수 없음: {exc}")

    if args.briefing:
        briefing = args.briefing.resolve()
        if not briefing.is_file():
            errors.append(f"브리핑 파일 없음: {briefing}")
        else:
            text = briefing.read_text(encoding="utf-8-sig")
            has_shortfall = bool(
                re.search(r"질문 게이트 PASS/HOLD 원석 5~10건:\s*미달", text)
                or re.search(r"질문 게이트 PASS 우선 검증 2~4건:\s*미달", text)
            )
            reports_pass = bool(
                re.search(r"탐색 수행 판정:\s*PASS", text)
                or re.search(r"작업량 종합 판정:\s*PASS", text)
            )
            if has_shortfall and reports_pass:
                errors.append("브리핑 계측 모순: 작업량 미달인데 탐색 수행 PASS")
            if "탐색 수행 판정:" not in text:
                warnings.append("브리핑에 v1.5 탐색 수행 판정이 없음")
            if "편집 산출 판정:" not in text:
                warnings.append("브리핑에 v1.5 편집 산출 판정이 없음")
            has_question_rows = bool(
                re.search(r"질문 게이트[:\s|]+PASS", text)
                or re.search(r"질문 품질 PASS\s*/\s*HOLD\s*/\s*FAIL:\s*[1-9]", text)
            )
            if has_question_rows:
                required_quality_labels = [
                    "근거 앵커",
                    "질문 품질 점수",
                    "중심 질문",
                    "시민 손실 가설",
                    "경쟁 가설",
                    "판정선",
                    "출처 프레임",
                    "편집적 추가",
                    "독창성 게이트",
                    "왜 지금 유형",
                    "질문 가족",
                    "시민 손실 근거 탐색",
                    "반대 근거 탐색",
                    "최소 판정 실험",
                ]
                for label in required_quality_labels:
                    if label not in text:
                        errors.append(f"브리핑 질문 품질 필드 누락: {label}")

    print(f"검증 장부 행: {len(rows)}")
    print(f"오류: {len(errors)} / 경고: {len(warnings)}")
    for message in errors:
        print(f"ERROR: {message}")
    for message in warnings:
        print(f"WARN: {message}")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
