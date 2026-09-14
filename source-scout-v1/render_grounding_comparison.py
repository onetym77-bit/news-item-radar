#!/usr/bin/env python3
"""Render the fixed 2026-09-14 false-positive/recall comparison."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "output" / "grounding_comparison_latest.md"

CASES = [
    (
        "일반 의정 연설",
        "서울의 교육격차를 줄이고 안전한 학교를 만들기 위해 최선을 다하겠습니다",
        "MEASURED_PROBLEM_SIGNAL",
        "council",
    ),
    (
        "학생인권 우려 발언",
        "학생인권조례 폐지는 교육 격차와 갈등을 초래할 수 있어 우려됩니다",
        "MEASURED_PROBLEM_SIGNAL",
        "council",
    ),
    (
        "위원 선임 절차",
        "제4항과 제41조에 따라 11대 의회 상임위원을 선임하고 전자투표로 표결합니다",
        "DECOMPOSABLE_STRUCTURE",
        "council",
    ),
    (
        "열린데이터 메뉴",
        "본문 바로가기 메뉴 로그인 회원가입 분야 선택 파일내려받기 전체 설명보기",
        "검증 지도 진입",
        "open_data",
    ),
    (
        "서울연구원 제목",
        "집합건물 분쟁실태와 지원방안",
        "MEASURED_PROBLEM_SIGNAL",
        "research",
    ),
    (
        "값 없는 체불 표 제목",
        "2026.7월 지역별 체불 현황",
        "MEASURED_PROBLEM_SIGNAL",
        "labor",
    ),
    (
        "응답소 연락처 푸터",
        "서울특별시청 (04524) 서울특별시 중구 세종대로 110 · 문의 및 전화민원 신청: 02)120",
        "DIRECT_PROBLEM_SIGNAL",
        "council",
    ),
    (
        "정책 투입액 발표",
        "서울시는 1조 4,570억 원 추경을 편성해 교통비 부담을 낮추고 피해지원 재원을 투입했습니다",
        "MEASURED_PROBLEM_SIGNAL",
        "council",
    ),
    (
        "포털 표시 안내",
        "※ 가장 최근에 개방된 100개 데이터만 표시됩니다.",
        "검증 지도 진입",
        "open_data",
    ),
    (
        "민원 처리 요약 제목",
        "귀하의 민원내용은 도로시설물 단차 점검 및 보수·보강 요청에 관한 것입니다",
        "DIRECT_PROBLEM_SIGNAL",
        "council",
    ),
    (
        "교육 예산 약속",
        "교육복지를 강화하겠습니다. 3세 보육비 지원 확대에 111억 원을 편성하여 학부모 부담을 덜겠습니다",
        "MEASURED_PROBLEM_SIGNAL",
        "council",
    ),
    (
        "체불 표 구조 설명",
        "구분, 전체, 서울, 부산으로 구성된 26.7월 지역별(17개 시도) 체불 현황의 첫번째 테이블",
        "MEASURED_PROBLEM_SIGNAL",
        "labor",
    ),
    (
        "포털 제공기간 안내",
        "※ Sheet/OpenAPI는 최근 1개월치 데이터만 제공합니다.",
        "검증 지도 진입",
        "open_data",
    ),
    (
        "K-패스 가정값",
        "똑같이 100명의 서울시민이 이용한다고 했을 때 K-패스 서울시 부담률은 60%, 다른 카드는 100%입니다",
        "MEASURED_PROBLEM_SIGNAL",
        "council",
    ),
    (
        "출생아 증가",
        "서울 출생아 수는 2024년 4월 이후 26개월 연속 증가세를 보이고 있습니다",
        "MEASURED_PROBLEM_SIGNAL·문제 질문",
        "council",
    ),
    (
        "응답소 안내 푸터",
        "다 - 듣겠습니다 · 서울시 불편사항 응답소에 얘기해주세요. · 민원처리안내",
        "DIRECT_PROBLEM_SIGNAL",
        "council",
    ),
    (
        "의회 쟁점 언급과 발언시간",
        "삼성역 철근 누락 사고 이야기하겠습니다. 남은 시간이 12분입니다. 4년 동안 40분씩 1 대 1로 시정질문을 했습니다.",
        "MEASURED_PROBLEM_SIGNAL",
        "council",
    ),
    (
        "응답소 단순 접수 현황판",
        "(2026. 09. 14 현재) 민원 현황판 오늘 4,714건, 4월 234,504건, 5월 238,771건 · 월별 민원접수 건수",
        "DIRECT_PROBLEM_SIGNAL",
        "eungdapso",
    ),
    (
        "임금체불 증가",
        "서울 임금체불은 100건으로 급증하며 증가세를 보였습니다",
        "긍정 회복으로 오분류",
        "council",
    ),
    (
        "외국인 카드 총액",
        "서울 외국인 카드소비 총액 1조 원 자치구별·업종별 현황",
        "NONE",
        "council",
    ),
    (
        "UD택시 공급 제약",
        "서울 UD택시는 12대만 06~15시 운행해 요청과 매칭될 확률이 낮아 이용이 제한된다는 지적",
        "질문에 병원 이동·미배차를 사실처럼 추가",
        "council",
    ),
    (
        "버스 소송 추산",
        "서울 시내버스 소송 부담을 협회는 5,266억 원에서 1조 216억 원으로 추산했고 연간 적자지원은 8,915억 원이다",
        "원인을 관리 공백으로 단정",
        "council",
    ),
]

SOURCES = {
    "council": {"id": "council_minutes", "name": "서울시의회", "local": True, "voice": False, "role": "BOTH"},
    "open_data": {"id": "seoul_open_data", "name": "열린데이터", "local": True, "voice": False, "role": "VERIFICATION"},
    "research": {"id": "seoul_research", "name": "서울연구원", "local": True, "voice": False, "role": "BOTH"},
    "labor": {"id": "labor_arrears", "name": "체불통계", "local": False, "voice": False, "role": "BOTH"},
    "eungdapso": {"id": "eungdapso", "name": "응답소", "local": True, "voice": True, "role": "DISCOVERY"},
}


def load_scout():
    path = HERE / "scout_sources.py"
    spec = importlib.util.spec_from_file_location("source_scout_comparison", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    scout = load_scout()
    lines = [
        "# 질문 근거 검사 수정 전후 비교",
        "",
        "- 동일 자료: 2026-09-14 실제 실행에서 확인된 오탐·오분류 19건과 보존해야 할 양성 3건",
        "- 수정 전은 당시 실행 결과·질문을 요약했고, 수정 후는 현재 분류기를 같은 문장에 다시 적용한 값",
        "",
        "| 사례 | 수정 전 | 수정 후 | 자동 처리 |",
        "|---|---|---|---|",
    ]
    for name, evidence, before, source_key in CASES:
        source = SOURCES[source_key]
        _, _, _, signals = scout.score_text(evidence, source)
        payload = scout.build_question_payload(evidence, source["id"], signals)
        after = (
            f"{signals['precheck_status']} · {signals['content_class']} · "
            f"{signals['evidence_anchor']} · 질문 {payload['grounding_status']}"
        )
        action = (
            "후보 유지" if signals["evidence_anchor"] != "NONE" and payload["grounding_status"] == "PASS"
            else "검증자료만" if signals["verification_usable"]
            else "본문 확보 대기" if signals["precheck_status"] == "HOLD"
            else "자동 제외"
        )
        lines.append(f"| {name} | {before} | {after} | {action} |")
    lines.extend(
        [
            "",
            "수정 후 PASS는 기사 승인이 아니라 사람 판정 카드 진입 자격이다.",
            "HOLD는 현상이 없다는 뜻이 아니라 제목·주장만으로는 사실관계를 확정할 수 없다는 뜻이다.",
            "",
        ]
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"comparison={OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
