#!/usr/bin/env python3
"""Semantic precheck and question-grounding helpers for source discovery."""

from __future__ import annotations

import re

SPACE_RE = re.compile(r"\s+")
MEASUREMENT_RE = re.compile(
    r"(?<![0-9A-Za-z가-힣])\d[\d,]*(?:\.\d+)?\s*"
    r"(?:%|조\s*원|억\s*원|백만\s*원|만\s*원|천\s*원|원|조|억|명|가구|건|대|곳|개|회|시간|분|개월|km|㎞)"
)
TIME_RANGE_RE = re.compile(r"(?<!\d)\d{1,2}\s*[~-]\s*\d{1,2}\s*시")
LAW_RE = re.compile(r"제\s*\d+\s*(?:조|항|호)")
ORDINAL_RE = re.compile(r"\d+\s*대\s*(?:의회|국회|대통령|전략|과제|통계)")
DATE_TOKEN_RE = re.compile(
    r"(?<!\d)(?:19|20)\d{2}(?:\s*년|[.\-/]\s*\d{1,2}(?:\s*월|[.\-/]\s*\d{1,2}\s*일?)?)?"
)

NAV_TERMS = (
    "본문 바로가기", "검색어 입력", "메뉴", "로그인", "회원가입", "개인정보처리방침",
    "페이스북", "인스타그램", "유튜브", "맨위로", "전체 설명보기", "오류신고",
    "파일내려받기", "분야 선택",
)
CONTACT_RE = re.compile(r"(?:\(?0\d{1,2}\)?[- )]\d{2,4}[- ]?\d{3,4}|\(0\d{4,5}\)|우편번호)")
PLATFORM_NOTICE_TERMS = (
    "가장 최근에 개방된", "데이터만 표시", "최대", "노출됩니다",
    "전체 데이터는 CSV", "내려받아 확인", "sheet는", "Sheet/OpenAPI", "최근 1개월치",
)
POLICY_ACTION_TERMS = (
    "예산을 편성", "추경을 편성", "지원한", "지원했습니다", "재원을 투입",
    "발행을 확대", "지원 확대", "편성", "반영하여", "시행", "도입", "조성공사", "설치공사",
)

PROCEDURE_TERMS = (
    "의사봉", "상정", "표결", "전자투표", "위원 선임", "위원을 선임", "안건 처리",
    "개의하겠습니다", "산회를 선포", "회의규칙",
)
CONCERN_TERMS = (
    "우려", "수 있다", "가능성이", "전망", "예상", "주장", "촉구", "반대한다",
    "필요하다", "필요합니다",
)
SPEECH_TERMS = (
    "바랍니다", "챙기겠습니다", "노력하겠습니다", "추진하겠습니다", "당부", "비전",
    "출발선", "과제입니다", "목표로", "하겠습니다",
)
DATASET_TERMS = (
    "데이터셋", "공공데이터", "원자료", "csv", "api", "테이블", "컬럼", "분포",
    "지역별", "자치구별", "업종별", "연령별", "성별", "시간대별", "월별",
)
STRUCTURAL_TERMS = (
    "총액", "평균", "비율", "건수", "이용률", "집행률", "발생률", "지역별",
    "자치구별", "대상별", "업종별", "연령별", "성별", "월별", "시간대별",
    "채널별", "전년", "전월", "지난해", "추이", "분포", "돌파",
)
OBSERVED_TERMS = (
    "발생", "접수", "확인", "기록", "집계", "증가", "감소", "급증", "급감",
    "초과", "미달", "체불", "미지급", "적자", "소송", "피해",
    "불편", "대기", "중단", "분쟁", "낮아", "높아",
)
ATTRIBUTION_TERMS = ("주장", "추산", "추정", "예상", "전망", "우려", "밝혔다", "밝혔", "협회")
DIRECT_TERMS = ("겪", "불편", "피해", "못하", "거절", "대기", "이용 포기", "우회")
AXIS_MAP = {
    "지역별": "지역", "자치구별": "자치구", "대상별": "대상", "업종별": "업종",
    "연령별": "연령", "성별": "성별", "월별": "월", "시간대별": "시간대",
    "채널별": "채널", "주택유형": "주택유형", "운송사": "운송사",
}


def normalize(text: str) -> str:
    return SPACE_RE.sub(" ", text or "").strip()


def extract_substantive_values(text: str) -> list[str]:
    """Extract measurements after removing legal, ordinal and calendar numbers."""
    cleaned = LAW_RE.sub(" ", text or "")
    cleaned = ORDINAL_RE.sub(" ", cleaned)
    cleaned = DATE_TOKEN_RE.sub(" ", cleaned)
    values: list[str] = []
    for match in list(TIME_RANGE_RE.finditer(cleaned)) + list(MEASUREMENT_RE.finditer(cleaned)):
        value = normalize(match.group(0))
        if value and value not in values:
            values.append(value)
    return values


def numeric_keys(text: str) -> set[str]:
    return {re.sub(r"[\s,]", "", value) for value in extract_substantive_values(text)}


def _axis_terms(text: str) -> list[str]:
    axes: list[str] = []
    for token, label in AXIS_MAP.items():
        if token in text and label not in axes:
            axes.append(label)
    return axes


def analyze_content(
    text: str,
    source: dict,
    record_kind: str = "PAGE_CHUNK",
    *,
    problem: bool = False,
    loss: bool = False,
    routine_action: bool = False,
    purpose_only: bool = False,
) -> dict:
    text = normalize(text)
    values = extract_substantive_values(text)
    nav_hits = [term for term in NAV_TERMS if term in text]
    procedure_hits = [term for term in PROCEDURE_TERMS if term in text]
    axes = _axis_terms(text)
    source_id = source.get("id", "")
    role = source.get("role", "")
    purpose_change = bool(re.search(r"(?:증가|감소|격차|사고).{0,20}(?:위한|위해|목표)", text))
    observed_text = text.replace("피해지원", " ").replace("피해 지원", " ")
    observed = any(term in observed_text for term in OBSERVED_TERMS) and not purpose_change
    cost_problem = bool(
        re.search(
            r"(?:부담|피해액|손실|체불|미지급|적자|소송).{0,28}\d"
            r"|\d.{0,28}(?:부담|피해액|손실|체불|미지급|적자|소송)",
            text,
        )
    )
    concern = any(term in text for term in CONCERN_TERMS)
    speech = any(term in text for term in SPEECH_TERMS)

    content_class = "REPORTABLE_TEXT"
    precheck_status = "PASS"
    precheck_reason = "구체 문장"
    if (
        ("문의" in text or "전화" in text or "민원처리 안내" in text)
        and (CONTACT_RE.search(text) or "서울특별시청" in text)
    ):
        content_class, precheck_status = "CONTACT_BOILERPLATE", "FAIL"
        precheck_reason = "기관 연락처·푸터"
    elif any(term in text for term in PLATFORM_NOTICE_TERMS):
        content_class, precheck_status = "PLATFORM_NOTICE", "FAIL"
        precheck_reason = "데이터 포털 이용 안내"
    elif len(nav_hits) >= 2 or (text.count("·") >= 9 and not values):
        content_class, precheck_status = "NAVIGATION", "FAIL"
        precheck_reason = "메뉴·반복 문구"
    elif len(procedure_hits) >= 2 or (
        any(term in text for term in ("위원 선임", "위원을 선임", "전자투표"))
        and (LAW_RE.search(text) or ORDINAL_RE.search(text))
    ):
        content_class, precheck_status = "PARLIAMENTARY_PROCEDURE", "FAIL"
        precheck_reason = "회의 진행 절차"
    elif source_id == "labor_arrears" and (
        "테이블" in text or "구분, 전체" in text
    ):
        content_class, precheck_status = "TABLE_SCHEMA_WITHOUT_VALUE", "HOLD"
        precheck_reason = "표 구조 설명만 있고 실제 지역 값 없음"
    elif (
        values
        and (any(term in text for term in POLICY_ACTION_TERMS) or speech)
        and not observed
    ):
        content_class, precheck_status = "POLICY_ANNOUNCEMENT", "HOLD"
        precheck_reason = "정책 투입액만 있고 결과 관찰값 없음"
    elif not values and concern:
        content_class, precheck_status = "CONCERN_OR_ATTRIBUTED_CLAIM", "HOLD"
        precheck_reason = "전망·우려만 있고 관찰값 없음"
    elif not values and speech:
        content_class, precheck_status = "SPEECH_PROMISE", "FAIL"
        precheck_reason = "일반 연설·목표"
    elif not values and source_id == "labor_arrears" and any(
        term in text for term in ("현황", "통계", "지역별", "표")
    ):
        content_class, precheck_status = "TABLE_SCHEMA_WITHOUT_VALUE", "HOLD"
        precheck_reason = "표 제목만 있고 값 없음"
    elif not values and role == "VERIFICATION" and any(term in text.lower() for term in DATASET_TERMS):
        content_class, precheck_status = "DATASET_METADATA", "PASS"
        precheck_reason = "검증용 데이터 설명"
    elif not values and len(text) <= 100 and any(
        term in text for term in ("실태", "현황", "분석", "연구", "지원방안", "보고서")
    ):
        content_class, precheck_status = "DOCUMENT_TITLE_ONLY", "HOLD"
        precheck_reason = "보고서 제목만 있고 본문 근거 없음"

    direct = (
        source.get("voice", False)
        and problem
        and any(term in text for term in DIRECT_TERMS)
        and not purpose_only
    )
    measured = (
        bool(values)
        and problem
        and (observed or cost_problem)
        and not (routine_action and purpose_only and not observed)
    )
    structural = bool(values) and any(term in text for term in STRUCTURAL_TERMS)

    anchor = "NONE"
    if precheck_status == "PASS":
        if direct:
            anchor = "DIRECT_PROBLEM_SIGNAL"
        elif measured:
            anchor = "MEASURED_PROBLEM_SIGNAL"
        elif structural:
            anchor = "DECOMPOSABLE_STRUCTURE"

    claim_status = "ATTRIBUTED_CLAIM" if any(term in text for term in ATTRIBUTION_TERMS) else (
        "OBSERVED_OR_PUBLISHED" if anchor != "NONE" else "UNRESOLVED"
    )
    verification_usable = (
        precheck_status == "PASS"
        and role == "VERIFICATION"
        and (
            content_class == "DATASET_METADATA"
            or bool(axes)
            or (
                bool(values)
                and any(term in text.lower() for term in STRUCTURAL_TERMS + DATASET_TERMS)
            )
        )
    )
    anchor_facts = [text] if anchor != "NONE" else []
    return {
        "record_kind": record_kind,
        "content_class": content_class,
        "precheck_status": precheck_status,
        "precheck_reason": precheck_reason,
        "substantive_values": values,
        "breakdown_axes": axes,
        "anchor_facts": anchor_facts,
        "evidence_anchor": anchor,
        "claim_status": claim_status,
        "verification_usable": verification_usable,
    }


def build_question_payload(text: str, source_id: str, analysis: dict) -> dict:
    text = normalize(text)
    anchor = analysis.get("evidence_anchor", "NONE")
    basis = text if anchor != "NONE" or analysis.get("verification_usable") else ""
    existing_axes = list(analysis.get("breakdown_axes", []))

    if anchor == "NONE" and not analysis.get("verification_usable"):
        question = "근거 앵커 없음 — 질문 점수 평가 제외"
        proposed_axes: list[str] = []
    elif source_id == "seoul_open_data" or analysis.get("verification_usable"):
        question = "이 자료의 실제 값과 분류항목으로 기존 발표의 총량 또는 집중 현상을 검증할 수 있는가?"
        proposed_axes = existing_axes or ["지역", "대상", "시간"]
    elif "장애인콜택시" in text or "UD택시" in text:
        question = "공급량과 운영시간을 실제 요청량 자료와 대조하면 어느 시간대와 지역에서 수요·공급 차이가 나타나는가?"
        proposed_axes = existing_axes or ["시간대", "지역", "요청량"]
    elif "전세사기" in text:
        question = "확인된 피해 규모를 자치구·주택유형별로 나누면 집중이 있는가? 지원 대상·금액 분포와 일치하는가?"
        proposed_axes = existing_axes or ["자치구", "주택유형", "지원 대상"]
    elif "시내버스" in text and ("소송" in text or "준공영제" in text):
        question = "제시된 소송 부담 추산은 운송사별·회계연도별로 어디에 집중되는가? 보조금·계약자료로 추산을 확인할 수 있는가?"
        proposed_axes = existing_axes or ["운송사", "회계연도", "보조금"]
    elif anchor == "DECOMPOSABLE_STRUCTURE":
        question = "원문 수치를 지역·대상·시간 등 확인 가능한 분류항목으로 나누면 어떤 집중이나 격차가 나타나는가?"
        proposed_axes = existing_axes or ["지역", "대상", "시간"]
    elif analysis.get("claim_status") == "ATTRIBUTED_CLAIM":
        question = "이 주장의 수치와 비교 기준을 원자료로 재현할 수 있는가? 다른 설명을 적용해도 차이가 남는가?"
        proposed_axes = existing_axes or ["원자료", "비교 기준", "대안 설명"]
    else:
        question = "확인된 문제 징후는 어느 범위에서 반복되며, 정상 변동과 구분할 비교자료는 무엇인가?"
        proposed_axes = existing_axes or ["범위", "기간", "비교집단"]

    source_numbers = numeric_keys(text)
    question_numbers = numeric_keys(question)
    issues: list[str] = []
    if basis and basis not in text:
        issues.append("질문 근거가 원문과 불일치")
    unsupported = sorted(question_numbers - source_numbers)
    if unsupported:
        issues.append("질문에 원문 밖 수치: " + ", ".join(unsupported))
    if anchor == "NONE" and not analysis.get("verification_usable"):
        issues.append("근거 앵커 없음")
    grounding_status = "PASS" if not issues else "HOLD"
    return {
        "question_basis": basis,
        "question": question,
        "verification_axes": proposed_axes,
        "grounding_status": grounding_status,
        "grounding_issues": issues,
    }
