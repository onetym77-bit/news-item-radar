#!/usr/bin/env python3
"""Pilot collector for testing non-YouTube source families.

The output is diagnostic. A heuristic-qualified lead is not an approved story item;
editors still have to test the question, counter-evidence and reporting feasibility.
"""

from __future__ import annotations

import csv
import json
from calendar import monthrange
import re
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from grounding import (
    DATA_ROW_SPECIFIC_VALUE_HEADERS,
    analyze_content,
    build_question_payload,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(__file__).resolve().parent / "output"
NOW_KST = datetime.now(timezone(timedelta(hours=9)))
TODAY = NOW_KST.date()
USER_AGENT = "Mozilla/5.0 (compatible; NewsItemRadar/1.0; +https://github.com/onetym77-bit/news-item-radar)"

FRESHNESS_POLICY_DAYS = {
    "daily": (3, 7),
    "continuous": (7, 14),
    "event_driven": (14, 28),
    "weekly": (14, 28),
    "monthly": (45, 90),
    "quarterly": (120, 180),
}


def freshness_metadata(
    source: dict,
    observed_date: str,
    *,
    basis: str = "document_date",
    today: date = TODAY,
) -> dict:
    cadence = source.get("cadence", "continuous")
    fresh_days, carryover_days = FRESHNESS_POLICY_DAYS.get(
        cadence, FRESHNESS_POLICY_DAYS["continuous"]
    )
    payload = {
        "source_date": observed_date or "",
        "freshness_days": None,
        "freshness_window_days": fresh_days,
        "carryover_until_days": carryover_days,
        "freshness_status": "FRESHNESS_UNKNOWN",
        "cadence": cadence,
        "freshness_basis": basis,
    }
    if not observed_date:
        return payload
    try:
        age = (today - date.fromisoformat(observed_date)).days
    except ValueError:
        return payload
    payload["freshness_days"] = age
    if age < 0:
        payload["freshness_status"] = "FUTURE_DATED"
    elif age <= fresh_days:
        payload["freshness_status"] = "FRESH"
    elif age <= carryover_days:
        payload["freshness_status"] = "STALE_CARRYOVER"
    else:
        payload["freshness_status"] = "ARCHIVED_STALE"
    return payload


SOURCES = [
    {
        "id": "eungdapso",
        "name": "서울시 응답소 공개민원",
        "url": "https://eungdapso.seoul.go.kr/main.do",
        "role": "DISCOVERY",
        "local": True,
        "voice": True,
        "follow": r"complaint_pub_vie\.do",
        "max_follow": 8,
    },
    {
        "id": "council_minutes",
        "name": "서울시의회 회의록",
        "url": "https://ms.smc.seoul.kr/kr/assembly/main.do",
        "role": "BOTH",
        "cadence": "event_driven",
        "local": True,
        "voice": False,
        "follow": r"recordView\.do",
        "max_follow": 6,
    },
    {
        "id": "seoul_open_data",
        "name": "서울 열린데이터 신규 데이터셋",
        "url": "https://data.seoul.go.kr/datasetRanking/new.do",
        "role": "VERIFICATION",
        "local": True,
        "voice": False,
        "follow": r"datasetView\.do",
        "max_follow": 6,
    },
    {
        "id": "seoul_bigdata",
        "name": "서울 빅데이터캠퍼스 갱신 데이터",
        "url": "https://bigdata.seoul.go.kr/main.do",
        "role": "VERIFICATION",
        "local": True,
        "voice": False,
        "follow": r"data/select.*Data",
        "max_follow": 4,
    },
    {
        "id": "seoul_research",
        "name": "서울연구원 정책·연구 자료",
        "url": "https://www.si.re.kr/bbs/list.do?key=2024100154",
        "role": "BOTH",
        "cadence": "monthly",
        "local": True,
        "scope_requires_content": True,
        "voice": False,
        "follow": r"bbs/view\.do",
        "max_follow": 6,
    },
    {
        "id": "labor_arrears",
        "name": "고용노동부 임금체불 통계",
        "url": "https://labor.moel.go.kr/arrstat/sttcStusList.do",
        "role": "BOTH",
        "cadence": "monthly",
        "local": False,
        "voice": False,
        "follow": "",
        "max_follow": 0,
        "timeout": 45,
        "retry": 1,
    },
    {
        "id": "consumer_agency",
        "name": "한국소비자원 피해·분쟁 자료",
        "url": "https://www.kca.go.kr/home/main.do",
        "role": "BOTH",
        "local": False,
        "voice": False,
        "follow": r"(?:mode=view|bbs|board|smartconsumer/sub\.do)",
        "max_follow": 6,
    },
]

PROBLEM_TERMS = (
    "격차", "불균형", "부족", "불편", "피해", "손실", "사고", "체불", "미지급", "폐업",
    "지연", "혼잡", "위험", "미달", "초과",
    "사각지대", "제한", "불용", "삭감", "적자", "위반", "민원", "환불", "해지",
    "부실", "제외", "갈등", "논란", "노후", "고령", "폭염",
    "침수", "붕괴", "과밀", "공백", "부담", "취약", "분쟁",
)
EVIDENCE_TERMS = (
    "통계", "현황", "실태", "조사", "예산", "결산", "감사", "분석",
    "집행률", "이용률", "증감", "건수", "비율", "측정값", "발생률",
)
IMPLEMENTATION_TERMS = (
    "대책", "지원", "운영", "제도", "조례", "정책", "사업", "집행", "대상",
    "기준", "계획", "시행", "관리", "점검", "배정", "공급",
)
LOSS_TERMS = (
    "비용", "요금", "부담", "손실", "피해", "체불", "미지급", "환불", "생계",
    "폐업", "소득",
)
ANCHOR_DEVIATION_TERMS = (
    "격차", "불균형", "급증", "급감", "증가", "감소", "지연", "미달", "초과",
    "불용", "삭감", "적자", "위반", "체불", "미지급", "폐업", "사고", "붕괴",
    "과밀", "공백", "분쟁", "반복", "연장", "변경", "취소",
)
OBSERVED_CHANGE_TERMS = (
    "격차", "불균형", "급증", "급감", "증가", "감소", "지연", "미달", "초과",
    "불용", "삭감", "적자", "위반", "반복", "연장", "변경", "취소",
)
STRUCTURAL_DATA_TERMS = (
    "총액", "평균", "비율", "건수", "이용률", "집행률", "발생률", "통계", "현황",
    "실태", "조사", "지역별", "자치구별", "대상별", "업종별", "연령별", "성별",
    "월별", "시간대별", "채널별", "전년", "전월", "지난해", "추이", "분포", "돌파",
)
STRUCTURAL_AXIS_TERMS = (
    "지역별", "자치구별", "대상별", "업종별", "연령별", "성별", "월별",
    "시간대별", "채널별", "전년", "전월", "지난해", "추이", "분포",
)
ROUTINE_STRUCTURAL_ESCAPE_TERMS = STRUCTURAL_AXIS_TERMS + (
    "건수", "이용률", "집행률", "발생률",
)
DIRECT_EXPERIENCE_TERMS = (
    "겪", "불편", "피해", "못하", "못했", "거절", "대기", "부담", "위험", "민원",
    "문의", "이용 포기", "우회",
)
ROUTINE_ACTION_TERMS = (
    "조성", "정비", "보수", "개선", "설치", "개관", "준공", "지원사업",
)
ROUTINE_PURPOSE_TERMS = (
    "예방", "방지", "대응", "해소", "개선", "지원", "보호", "저감",
    "위한", "위해", "목표",
)
ROUTINE_ACTION_RE = re.compile(
    r"(?:공사비|공사\s*기간|공사\s*계약|착공|준공|"
    r"(?:예방|방지|대응|해소|저감|개선|정비|보수|설치|조성)\s*공사)"
)
PURPOSE_CLAUSE_RE = re.compile(
    r"(?:사고|피해|민원|붕괴|분쟁|체불|미지급|위험|장애|침수)"
    r"(?:을|를)?\s*(?:예방|방지|대응|해소|개선|지원|보호|저감)"
    r"(?:공사|사업|시설|대책)?"
    r"|(?:격차|불균형|사고|피해|민원|위험|증가|감소|지연)"
    r"(?:을|를)?\s*(?:줄이기\s*)?(?:위한|위해|목표(?:로)?)"
    r"|(?:사고|피해|민원|위험)(?:을|를)?\s*(?:줄이|낮추|막기)"
)
OBSERVED_EVENT_RE = re.compile(
    r"(?:사고|피해|민원|붕괴|분쟁|체불|미지급).{0,24}"
    r"(?:\d[\d,]*(?:건|명|회)|발생|접수|확인|반복|증가|감소|지연|초과|미달)"
)

LOW_VALUE_TERMS = (
    "행사", "축제", "공연", "공모", "모집", "채용", "홍보", "관광", "견학",
    "체험", "수상", "기념", "개최", "캠페인", "전시",
)
NAV_TERMS = (
    "본문 바로가기", "메뉴", "로그인", "회원가입", "개인정보처리방침", "누리집",
    "페이스북", "인스타그램", "유튜브", "맨위로", "이전", "다음", "더보기",
)
BOILERPLATE_TERMS = (
    "검색어 입력", "분야 선택", "페이지", "리스트", "조회수", "파일내려받기",
    "전체 설명보기", "오류신고", "신청기간",
)
KOREAN_RE = re.compile(r"[가-힣]")
NUMBER_RE = re.compile(r"(?:\d[\d,]*(?:\.\d+)?\s*(?:%|명|건|원|억|조|대|곳|개|일|개월|년))")
DATE_RE = re.compile(r"(?<!\d)(20\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})(?:일)?")
YEAR_MONTH_RE = re.compile(
    r"(?<!\d)(20\d{2})\s*(?:[.\-/]\s*(\d{1,2})|년\s*(\d{1,2})\s*월)(?!\s*\d)"
)
SHORT_YEAR_MONTH_RE = re.compile(
    r"['’](\d{2})\s*[.\-/년]\s*(\d{1,2})\s*월?"
)
SPACE_RE = re.compile(r"\s+")


@dataclass
class FetchResult:
    url: str
    ok: bool
    status: int
    elapsed_ms: int
    byte_count: int
    text: str
    error: str = ""


class VisibleHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.href: str | None = None
        self.anchor_parts: list[str] = []
        self.anchors: list[tuple[str, str]] = []
        self.chunks: list[str] = []
        self.date_hints: list[str] = []
        self.tables: list[list[list[tuple[str, str]]]] = []
        self.table_depth = 0
        self.current_table: list[list[tuple[str, str]]] = []
        self.current_row: list[tuple[str, str]] | None = None
        self.current_cell_tag: str | None = None
        self.current_cell_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        attrs_map = {key.lower(): value or "" for key, value in attrs}
        if tag == "time" and attrs_map.get("datetime"):
            self.date_hints.append(attrs_map["datetime"])
        elif tag == "meta":
            meta_name = (attrs_map.get("name") or attrs_map.get("property") or "").lower()
            if any(token in meta_name for token in ("date", "publish", "modified", "created", "updated")):
                content = attrs_map.get("content", "")
                if content:
                    self.date_hints.append(content)
        if tag == "table":
            if self.table_depth == 0:
                self.current_table = []
            self.table_depth += 1
        elif tag == "tr" and self.table_depth == 1:
            self.current_row = []
        elif (
            tag in {"th", "td"}
            and self.table_depth == 1
            and self.current_row is not None
        ):
            self.current_cell_tag = tag
            self.current_cell_parts = []
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.anchor_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            if self.skip_depth:
                self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if (
            tag in {"th", "td"}
            and self.current_cell_tag == tag
            and self.current_row is not None
        ):
            self.current_row.append(
                (tag, normalize(" ".join(self.current_cell_parts)))
            )
            self.current_cell_tag = None
            self.current_cell_parts = []
        elif tag == "tr" and self.table_depth == 1:
            if self.current_row and any(value for _, value in self.current_row):
                self.current_table.append(self.current_row)
            self.current_row = None
        elif tag == "table" and self.table_depth:
            if self.table_depth == 1:
                if self.current_table:
                    self.tables.append(self.current_table)
                self.current_table = []
                self.current_row = None
                self.current_cell_tag = None
                self.current_cell_parts = []
            self.table_depth -= 1
        if tag == "a" and self.href is not None:
            label = normalize(" ".join(self.anchor_parts))
            if label:
                self.anchors.append((self.href, label))
            self.href = None
            self.anchor_parts = []

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        cleaned = normalize(data)
        if not cleaned:
            return
        self.chunks.append(cleaned)
        if self.href is not None:
            self.anchor_parts.append(cleaned)
        if self.current_cell_tag is not None:
            self.current_cell_parts.append(cleaned)


def normalize(value: str) -> str:
    return SPACE_RE.sub(" ", value or "").strip()


def fetch(url: str, timeout: int = 22) -> FetchResult:
    started = time.perf_counter()
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = getattr(response, "status", 200)
            charset = response.headers.get_content_charset()
            decoded = None
            for encoding in [charset, "utf-8", "cp949", "euc-kr"]:
                if not encoding:
                    continue
                try:
                    decoded = raw.decode(encoding)
                    break
                except (UnicodeDecodeError, LookupError):
                    continue
            if decoded is None:
                decoded = raw.decode("utf-8", errors="replace")
            return FetchResult(
                url=url,
                ok=200 <= status < 400,
                status=status,
                elapsed_ms=round((time.perf_counter() - started) * 1000),
                byte_count=len(raw),
                text=decoded,
            )
    except HTTPError as exc:
        return FetchResult(
            url=url,
            ok=False,
            status=exc.code,
            elapsed_ms=round((time.perf_counter() - started) * 1000),
            byte_count=0,
            text="",
            error=f"HTTP {exc.code}",
        )
    except (URLError, TimeoutError, OSError) as exc:
        return FetchResult(
            url=url,
            ok=False,
            status=0,
            elapsed_ms=round((time.perf_counter() - started) * 1000),
            byte_count=0,
            text="",
            error=f"{type(exc).__name__}: {exc}",
        )


def parse_html(html: str) -> VisibleHTML:
    parser = VisibleHTML()
    parser.feed(html)
    parser.close()
    return parser


TABLE_AXIS_HEADERS = (
    "구분", "자치구", "지역", "구분", "행정동", "법정동", "연령", "성별", "업종",
    "대상", "시설", "측정소", "노선", "기간", "년월", "일자", "시간대",
)
TABLE_VALUE_HEADERS = (
    "건수", "인원수", "인원", "금액", "피해액", "비율", "이용률", "발생률",
    "이용자수", "발생건수", "승하차", "매출", "소비", "농도", "지수",
    "측정값", "합계", "평균",
)
TABLE_FILE_METADATA_HEADERS = ("파일명", "용량", "수정일", "내려받기", "다운로드")
TABLE_INFO_METADATA_HEADERS = (
    "공개일자", "개방일", "갱신일", "제공기관", "제공부서", "담당자",
    "연락처", "원본시스템",
)
TABLE_NUMERIC_CELL_RE = re.compile(
    r"^[+-]?\d[\d,]*(?:\.\d+)?"
    r"(?:\s*(?:%|원|명|건|가구|대|곳|개|회|시간|분|개월|km|㎞))?$"
)


def _matching_header_indexes(headers: list[str], terms: tuple[str, ...]) -> list[int]:
    return [
        index
        for index, header in enumerate(headers)
        if any(term in header for term in terms)
    ]


def static_verification_rows(parser: VisibleHTML, limit: int = 80) -> list[str]:
    """Return only source-visible statistical rows, never portal metadata tables."""
    results: list[str] = []
    seen: set[str] = set()
    for table in parser.tables:
        header_position = next(
            (
                index
                for index, row in enumerate(table)
                if len(row) >= 2
                and all(tag == "th" and value for tag, value in row)
            ),
            None,
        )
        if header_position is None:
            continue
        headers = [value for _, value in table[header_position]]
        file_meta_hits = sum(
            any(term in header for header in headers)
            for term in TABLE_FILE_METADATA_HEADERS
        )
        info_meta_hits = sum(
            any(term in header for header in headers)
            for term in TABLE_INFO_METADATA_HEADERS
        )
        if file_meta_hits >= 2 or info_meta_hits >= 2:
            continue
        axis_indexes = _matching_header_indexes(headers, TABLE_AXIS_HEADERS)
        value_indexes = _matching_header_indexes(headers, TABLE_VALUE_HEADERS)
        specific_value_indexes = _matching_header_indexes(
            headers, DATA_ROW_SPECIFIC_VALUE_HEADERS
        )
        if not axis_indexes or not specific_value_indexes:
            continue
        value_indexes = specific_value_indexes
        selected_indexes = sorted(set(axis_indexes + value_indexes))
        for row in table[header_position + 1 :]:
            cells = [value for _, value in row]
            if len(cells) != len(headers):
                continue
            if not any(cells[index] for index in axis_indexes):
                continue
            numeric_value_indexes = [
                index
                for index in value_indexes
                if cells[index] and TABLE_NUMERIC_CELL_RE.fullmatch(cells[index])
            ]
            if not numeric_value_indexes:
                continue
            included = sorted(set(axis_indexes + numeric_value_indexes))
            row_text = normalize(
                " · ".join(
                    f"{headers[index]}: {cells[index]}"
                    for index in included
                    if cells[index]
                )
            )
            key = re.sub(r"[^0-9A-Za-z가-힣]", "", row_text).lower()
            if (
                len(row_text) < 12
                or len(row_text) > 280
                or not KOREAN_RE.search(row_text)
                or not key
                or key in seen
            ):
                continue
            seen.add(key)
            results.append(row_text)
            if len(results) >= limit:
                return results
    return results


def labor_region_rows(parser: VisibleHTML) -> list[str]:
    """Convert the official wide 17-province table into a Seoul-vs-national row."""
    region_names = {
        "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
        "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
    }
    period = latest_period_label(
        chunk
        for chunk in parser.chunks
        if "체불" in chunk and ("지역별" in chunk or "시도" in chunk)
    )
    results: list[str] = []
    for table in parser.tables:
        header_position = next(
            (
                index
                for index, row in enumerate(table)
                if len(row) >= 4 and all(tag == "th" and value for tag, value in row)
            ),
            None,
        )
        if header_position is None:
            continue
        headers = [value for _, value in table[header_position]]
        if "서울" not in headers or "전체" not in headers:
            continue
        if sum(header in region_names for header in headers) < 3:
            continue
        seoul_index = headers.index("서울")
        total_index = headers.index("전체")
        for row in table[header_position + 1 :]:
            cells = [value for _, value in row]
            if len(cells) != len(headers):
                continue
            seoul_value = cells[seoul_index]
            total_value = cells[total_index]
            if not (
                TABLE_NUMERIC_CELL_RE.fullmatch(seoul_value)
                and TABLE_NUMERIC_CELL_RE.fullmatch(total_value)
            ):
                continue
            period_label = "기준월" if len(period) == 7 else "기준일"
            prefix = f"{period_label}: {period} · " if period else ""
            results.append(
                f"{prefix}지역: 서울 · 체불액(억 원): {seoul_value} · "
                f"전국 체불액(억 원): {total_value}"
            )
            break
    return results


def valid_candidate(text: str) -> bool:
    if len(text) < 12 or len(text) > 280 or not KOREAN_RE.search(text):
        return False
    if any(term in text for term in NAV_TERMS):
        return False
    if text.count("|") > 5:
        return False
    return True


def context_windows(chunks: list[str], limit: int = 45) -> list[str]:
    """Build local neighbour windows without merging unrelated page-wide text."""
    windows: list[str] = []
    seen: set[str] = set()
    trigger_terms = PROBLEM_TERMS + EVIDENCE_TERMS
    for index, chunk in enumerate(chunks):
        if not any(term in chunk for term in trigger_terms):
            continue
        left = max(0, index - 1)
        right = min(len(chunks), index + 2)
        window = normalize(" · ".join(chunks[left:right])).strip(" ·")
        key = re.sub(r"[^0-9A-Za-z가-힣]", "", window).lower()[:180]
        if valid_candidate(window) and key and key not in seen:
            seen.add(key)
            windows.append(window)
        if len(windows) >= limit:
            break
    return windows



def is_routine_action(text: str) -> bool:
    """Detect an administrative action without treating 기관명 속 '공사' as a project."""
    return any(term in text for term in ROUTINE_ACTION_TERMS) or bool(
        ROUTINE_ACTION_RE.search(text)
    )


def classify_evidence_anchor(
    text: str,
    source: dict,
    *,
    problem: bool,
    evidence: bool,
    loss: bool,
    record_kind: str = "PAGE_CHUNK",
) -> str:
    """Return an evidence route after semantic precheck."""
    routine_action = is_routine_action(text)
    purpose_only = routine_action and (
        bool(PURPOSE_CLAUSE_RE.search(text))
        or any(term in text for term in ROUTINE_PURPOSE_TERMS)
    )
    analysis = analyze_content(
        text,
        source,
        record_kind,
        problem=problem,
        loss=loss,
        routine_action=routine_action,
        purpose_only=purpose_only,
    )
    return analysis["evidence_anchor"]



def classify_scope(
    text: str,
    source: dict,
    record_kind: str = "PAGE_CHUNK",
) -> tuple[str, str, bool]:
    """Separate an institution's location from the geography actually measured."""
    if source.get("local") and not source.get("scope_requires_content", False):
        return "SEOUL_SOURCE_TRUSTED", "서울 행정·의정 원문 자체가 관측 범위를 한정", True

    normalized = normalize(text)
    if re.search(r"지역\s*[:：]\s*서울(?:\s|·|$)", normalized):
        scope_class = (
            "NATIONAL_COMPARISON_WITH_SEOUL_ROW"
            if any(marker in normalized for marker in ("전국", "전체"))
            else "SEOUL_VALUE_BOUND"
        )
        return scope_class, "구조화 행에서 서울 값이 직접 결합", True

    if "수도권" in normalized and "서울" not in normalized:
        return "METRO_ONLY", "수도권은 서울 단독 관측값이 아님", False

    excluded_context = re.search(
        r"(?:서울연구원|서울(?:에서|에|소재|주소|연락처|본사|지사).{0,18}"
        r"(?:설명회|세미나|행사|회의|개최|주소|전화|문의|본사|지사))",
        normalized,
    )
    unbound_national = re.search(
        r"서울\s*(?:등|포함).{0,12}(?:전국|전역|전\s*지역)",
        normalized,
    )
    if excluded_context or unbound_national:
        return "NATIONAL_OR_UNBOUND", "서울이 행사·기관·전국 열거에만 등장", False

    seoul_marker = re.compile(
        r"(?:서울특별시|서울시|서울지역|서울\s*(?:시민|주민|근로자|노동자|"
        r"소비자|피해자|사업장|자치구)|서울)"
    )
    numeric = re.compile(
        r"\d[\d,]*(?:\.\d+)?\s*(?:%|％|원|억원|억\s*원|조원|조\s*원|"
        r"건|명|가구|개|곳|회|시간|분|일|개월|배)"
    )
    metric_terms = (
        *PROBLEM_TERMS,
        "체불액", "피해액", "건수", "인원", "금액", "비율",
        "증가율", "감소율", "사업장", "근로자", "소비자",
    )
    for segment in re.split(r"[.!?。]|\n", normalized):
        if (
            seoul_marker.search(segment)
            and numeric.search(segment)
            and any(term in segment for term in metric_terms)
        ):
            return "SEOUL_VALUE_BOUND", "같은 문장에서 서울·문제지표·실제 값이 결합", True
    return "NATIONAL_OR_UNBOUND", "서울 관측값이 실질 지표와 직접 결합되지 않음", False


def direct_seoul_scope(text: str) -> bool:
    return classify_scope(
        text,
        {"local": False, "scope_requires_content": True},
    )[2]


def score_text(
    text: str,
    source: dict,
    record_kind: str = "PAGE_CHUNK",
) -> tuple[int, list[str], bool, dict]:
    score = 0
    reasons: list[str] = []
    scope_class, scope_reason, seoul_scope = classify_scope(
        text, source, record_kind
    )
    explicit_seoul = scope_class in {
        "SEOUL_VALUE_BOUND", "NATIONAL_COMPARISON_WITH_SEOUL_ROW"
    }
    operational_interruption = bool(
        re.search(
            r"(?:운행|서비스|지원|급식|공급|진료|돌봄|전산|통신|시설)"
            r".{0,16}(?:장애|중단)"
            r"|(?:장애|중단).{0,16}"
            r"(?:운행|서비스|지원|급식|공급|진료|돌봄|전산|통신|시설)",
            text,
        )
    )
    waiting_harm = bool(
        re.search(
            r"(?:\d[\d,]*(?:\.\d+)?\s*(?:시간|분).{0,12}대기(?!오염|질|환경)"
            r"|대기(?!오염|질|환경).{0,12}\d[\d,]*(?:\.\d+)?\s*(?:시간|분)"
            r"|장시간\s*대기(?!오염|질|환경)|대기\s*(?:행렬|줄))",
            text,
        )
    )
    problem = (
        any(term in text for term in PROBLEM_TERMS)
        or operational_interruption
        or waiting_harm
    )
    implementation = any(term in text for term in IMPLEMENTATION_TERMS)
    loss = any(term in text for term in LOSS_TERMS) or waiting_harm
    low_value = any(term in text for term in LOW_VALUE_TERMS)
    routine_action = is_routine_action(text)
    purpose_only = routine_action and (
        bool(PURPOSE_CLAUSE_RE.search(text))
        or any(term in text for term in ROUTINE_PURPOSE_TERMS)
    )
    analysis = analyze_content(
        text,
        source,
        record_kind,
        problem=problem,
        loss=loss,
        routine_action=routine_action,
        purpose_only=purpose_only,
    )
    evidence = bool(analysis["substantive_values"]) or analysis["evidence_anchor"] != "NONE"
    evidence_anchor = analysis["evidence_anchor"]
    boilerplate = analysis["content_class"] == "NAVIGATION"

    if seoul_scope:
        score += 2 if explicit_seoul else 1
        reasons.append("서울 범위")
    if problem:
        score += 2
        reasons.append("문제·변화")
    if evidence:
        score += 2
        if (
            source["role"] == "VERIFICATION"
            and not analysis["verification_usable"]
            and (
                analysis["verification_schema_lead"]
                or analysis["verification_metadata_lead"]
            )
        ):
            reasons.append("데이터 구조·갱신 설명")
        else:
            reasons.append("실제 수치·관찰근거")
    if evidence_anchor == "DECOMPOSABLE_STRUCTURE" and not problem:
        score += 2
        reasons.append("분해 가능한 구조 자료")
    if evidence_anchor == "NONE" and routine_action:
        reasons.append("사업·공사명 단독")
    if implementation:
        score += 1
        reasons.append("제도·집행")
    if loss:
        score += 1
        reasons.append("시민 손실")
    if source["voice"] and ("?" in text or "문의" in text or "민원" in text):
        score += 1
        reasons.append("시민 직접질문")
    if source["role"] == "BOTH":
        score += 1
        reasons.append("원문 근거 소스")
    elif source["role"] == "VERIFICATION":
        score += 1
        reasons.append("후속 검증 데이터 경로")
    if low_value:
        penalty = 1 if evidence_anchor != "NONE" else 3
        score -= penalty
        reasons.append("행사·홍보 맥락 감점" if penalty == 1 else "행사·홍보 감점")
    if analysis["precheck_status"] == "HOLD":
        score -= 2
        reasons.append("본문 근거 확인 대기")
    elif analysis["precheck_status"] == "FAIL":
        score -= 6
        reasons.append("절차·연설·메뉴 제외")
    if boilerplate:
        score -= 3
        reasons.append("목록·반복문구 감점")

    signals = {
        "problem": problem,
        "evidence": evidence,
        "implementation": implementation,
        "loss": loss,
        "low_value": low_value,
        "boilerplate": boilerplate,
        "scope_class": scope_class,
        "scope_reason": scope_reason,
        "evidence_anchor": evidence_anchor,
        "routine_action": routine_action,
        **analysis,
    }
    return score, reasons, seoul_scope, signals



def question_for(text: str, source: dict, record_kind: str = "PAGE_CHUNK") -> str:
    problem = any(term in text for term in PROBLEM_TERMS)
    loss = any(term in text for term in LOSS_TERMS)
    routine_action = is_routine_action(text)
    purpose_only = routine_action and (
        bool(PURPOSE_CLAUSE_RE.search(text))
        or any(term in text for term in ROUTINE_PURPOSE_TERMS)
    )
    analysis = analyze_content(
        text,
        source,
        record_kind,
        problem=problem,
        loss=loss,
        routine_action=routine_action,
        purpose_only=purpose_only,
    )
    return build_question_payload(text, source.get("id", ""), analysis)["question"]



def select_follow_links(parser: VisibleHTML, base_url: str, source: dict) -> list[str]:
    if not source["follow"]:
        return []
    pattern = re.compile(source["follow"], re.I)
    base_host = urlparse(base_url).netloc
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    for href, label in parser.anchors:
        absolute = urljoin(base_url, href)
        if absolute == base_url or urlparse(absolute).netloc != base_host:
            continue
        if absolute in seen or not pattern.search(absolute):
            continue
        if source["id"] == "consumer_agency":
            relevance = sum(
                term in label
                for term in ("피해", "분쟁", "환불", "안전", "주의", "상담", "급증", "실태")
            )
            if relevance == 0:
                continue
        elif source["id"] == "seoul_research":
            relevance = sum(
                term in label
                for term in ("정책리포트", "연구", "서울경제동향", "인포그래픽", "실태", "분석")
            )
            if relevance == 0 or any(term in label for term in LOW_VALUE_TERMS):
                continue
        else:
            relevance = 1
        seen.add(absolute)
        ranked.append((relevance, absolute))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [url for _, url in ranked[: source["max_follow"]]]


def source_url_allowed(source_id: str, url: str) -> bool:
    if source_id == "eungdapso":
        return "/exp/pub/complaint_pub_vie.do" in url or url.rstrip("/") == "https://eungdapso.seoul.go.kr/main.do"
    if source_id == "council_minutes":
        return "recordView.do" in url or "appendixDownload.do" in url or "/kr/assembly/main.do" in url
    if source_id == "seoul_open_data":
        return "datasetView.do" in url or "datasetRanking/new.do" in url
    if source_id == "seoul_bigdata":
        return "/data/" in url or url.rstrip("/") == "https://bigdata.seoul.go.kr/main.do"
    if source_id == "seoul_research":
        return "/bbs/view.do" in url or "/bbs/list.do" in url
    return True


def extract_records(
    parser: VisibleHTML,
    page_url: str,
    source: dict,
    include_windows: bool,
) -> list[dict]:
    texts: list[tuple[str, str, str]] = []
    if source["role"] == "VERIFICATION" or source["id"] in {"labor_arrears", "consumer_agency"}:
        for row_text in static_verification_rows(parser):
            texts.append((row_text, page_url, "DATA_ROW"))
    if source["id"] == "labor_arrears":
        for row_text in labor_region_rows(parser):
            texts.append((row_text, page_url, "DATA_ROW"))
    for href, label in parser.anchors:
        absolute = urljoin(page_url, href)
        if valid_candidate(label) and source_url_allowed(source["id"], absolute):
            texts.append((label, absolute, "LINK_LABEL"))
    for chunk in parser.chunks:
        if valid_candidate(chunk):
            texts.append((chunk, page_url, "PAGE_CHUNK"))
    if include_windows:
        for window in context_windows(parser.chunks, limit=20):
            texts.append((window, page_url, "CONTEXT_WINDOW"))

    records: list[dict] = []
    seen: set[str] = set()
    for text, url, record_kind in texts:
        key = re.sub(r"[^0-9A-Za-z가-힣]", "", text).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        score, reasons, seoul_scope, signals = score_text(text, source, record_kind)
        if score < 2 and signals["precheck_status"] == "PASS":
            continue
        if source["role"] == "VERIFICATION":
            quality_gate = signals["verification_usable"]
            qualified = score >= 4 and seoul_scope and quality_gate
        else:
            quality_gate = (
                signals["precheck_status"] == "PASS"
                and signals["evidence_anchor"] != "NONE"
                and (signals["problem"] or signals["evidence_anchor"] == "DECOMPOSABLE_STRUCTURE")
            )
            qualified = score >= 6 and seoul_scope and quality_gate
        localization_threshold = (
            6
            if record_kind == "DATA_ROW"
            or (
                not source["local"]
                and signals["evidence_anchor"] in {
                    "MEASURED_PROBLEM_SIGNAL", "DECOMPOSABLE_STRUCTURE"
                }
            )
            else 7
        )
        localization_lead = (
            score >= localization_threshold
            and not seoul_scope
            and quality_gate
        )
        question_payload = build_question_payload(text, source.get("id", ""), signals)
        if question_payload["grounding_status"] != "PASS":
            qualified = False
            localization_lead = False
        records.append(
            {
                "source_id": source["id"],
                "source_name": source["name"],
                "role": source["role"],
                "record_kind": record_kind,
                "text": text,
                "url": url,
                "score": score,
                "ranking_score_note": "수집 정렬점수이며 편집 승인 점수가 아님",
                "reasons": reasons,
                "signals": signals,
                "content_class": signals["content_class"],
                "precheck_status": signals["precheck_status"],
                "precheck_reason": signals["precheck_reason"],
                "substantive_values": signals["substantive_values"],
                "claim_status": signals["claim_status"],
                "verification_usable": signals["verification_usable"],
                "verification_metadata_lead": signals.get("verification_metadata_lead", False),
                "verification_schema_lead": signals.get("verification_schema_lead", False),
                "evidence_anchor": signals["evidence_anchor"],
                "seoul_scope": seoul_scope,
                "scope_class": signals.get("scope_class", "NATIONAL_OR_UNBOUND"),
                "scope_reason": signals.get("scope_reason", ""),
                "qualified": qualified,
                "localization_lead": localization_lead,
                **question_payload,
            }
        )
    records.sort(
        key=lambda row: (
            row["qualified"],
            row["precheck_status"] == "PASS",
            row["score"],
            len(row["text"]),
        ),
        reverse=True,
    )
    return records[:240]



def canonical_url(url: str, fallback: str) -> str:
    if url.startswith(("javascript:", "mailto:", "#")):
        return fallback
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return fallback
    return parsed._replace(fragment="").geturl()

def latest_date_from(chunks: Iterable[str]) -> str:
    found: list[date] = []
    for text in chunks:
        for year, month, day in DATE_RE.findall(text):
            try:
                parsed = date(int(year), int(month), int(day))
            except ValueError:
                continue
            if parsed <= TODAY + timedelta(days=3):
                found.append(parsed)
        without_full_dates = DATE_RE.sub(" ", text)
        for year, dotted_month, korean_month in YEAR_MONTH_RE.findall(without_full_dates):
            month = dotted_month or korean_month
            try:
                parsed = date(int(year), int(month), monthrange(int(year), int(month))[1])
            except ValueError:
                continue
            if parsed.year == TODAY.year and parsed.month == TODAY.month:
                parsed = TODAY
            if parsed <= TODAY + timedelta(days=3):
                found.append(parsed)
        for short_year, month in SHORT_YEAR_MONTH_RE.findall(without_full_dates):
            year = 2000 + int(short_year)
            try:
                parsed = date(year, int(month), monthrange(year, int(month))[1])
            except ValueError:
                continue
            if parsed.year == TODAY.year and parsed.month == TODAY.month:
                parsed = TODAY
            if parsed <= TODAY + timedelta(days=3):
                found.append(parsed)
    return max(found).isoformat() if found else ""



def latest_period_label(chunks: Iterable[str]) -> str:
    """Return a stable canonical period label for source text and revision hashes."""
    found: list[tuple[date, str]] = []
    for text in chunks:
        for year, month, day in DATE_RE.findall(text):
            try:
                parsed = date(int(year), int(month), int(day))
            except ValueError:
                continue
            if parsed <= TODAY + timedelta(days=3):
                found.append((parsed, parsed.isoformat()))
        without_full_dates = DATE_RE.sub(" ", text)
        for year, dotted_month, korean_month in YEAR_MONTH_RE.findall(without_full_dates):
            month = int(dotted_month or korean_month)
            try:
                effective = date(int(year), month, monthrange(int(year), month)[1])
            except ValueError:
                continue
            if effective.year == TODAY.year and effective.month == TODAY.month:
                effective = TODAY
            if effective <= TODAY + timedelta(days=3):
                found.append((effective, f"{int(year):04d}-{month:02d}"))
        for short_year, month_raw in SHORT_YEAR_MONTH_RE.findall(without_full_dates):
            year = 2000 + int(short_year)
            month = int(month_raw)
            try:
                effective = date(year, month, monthrange(year, month)[1])
            except ValueError:
                continue
            if effective.year == TODAY.year and effective.month == TODAY.month:
                effective = TODAY
            if effective <= TODAY + timedelta(days=3):
                found.append((effective, f"{year:04d}-{month:02d}"))
    return max(found, key=lambda item: item[0])[1] if found else ""


DOCUMENT_DATE_LABEL_RE = re.compile(
    r"(?:게시일|등록일|작성일|발행일|공개일|수정일|회의일|회의일시|개최일|일\s*시)"
)


def document_date_from(parser: VisibleHTML) -> str:
    """Return a page publication/meeting date, never an arbitrary cited statistic date."""
    hinted = latest_date_from(parser.date_hints)
    if hinted:
        return hinted
    candidates: list[str] = []
    for index, chunk in enumerate(parser.chunks):
        if DOCUMENT_DATE_LABEL_RE.search(chunk):
            candidates.extend(parser.chunks[index : index + 2])
    return latest_date_from(candidates)


def youtube_baseline() -> dict:
    path = ROOT / "interest-radar-v2" / "output" / "youtube_signal_ledger_v2_1.json"
    result = {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "available": path.exists(),
        "total": 0,
        "direct_voice_or_field": 0,
        "seoul": 0,
        "direct_and_seoul": 0,
        "direct_and_seoul_rate": 0.0,
    }
    if not path.exists():
        return result
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        result["available"] = False
        return result
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = next(
            (payload[key] for key in ("records", "items", "signals", "videos") if isinstance(payload.get(key), list)),
            [],
        )
    else:
        rows = []
    direct_labels = {"당사자 가능성", "현장·운영자", "상담·지원", "당사자", "현장"}
    result["total"] = len(rows)
    for row in rows:
        if not isinstance(row, dict):
            continue
        archetype = str(row.get("source_archetype", ""))
        direct = archetype in direct_labels or any(label in archetype for label in ("당사자", "현장", "상담"))
        places = row.get("seoul_place_terms", [])
        seoul = bool(places) or "서울" in str(row.get("title", ""))
        result["direct_voice_or_field"] += int(direct)
        result["seoul"] += int(seoul)
        result["direct_and_seoul"] += int(direct and seoul)
    if result["total"]:
        result["direct_and_seoul_rate"] = round(result["direct_and_seoul"] / result["total"] * 100, 1)
    return result


TOPIC_MARKERS = {
    "전세사기", "임차보증금", "피해가구",
    "기후동행카드", "교통공사", "손실금", "전가",
    "미지급", "통상임금", "지연이자",
    "출생아", "난임", "부모급여",
    "시내버스", "소송", "보조금",
    "정비사업", "전담인력",
}


DIVERSITY_STOPWORDS = {
    "서울", "서울시", "시장님", "의원님", "그리고", "그러나", "대해서", "관련", "말씀",
    "지금", "이렇게", "있습니다", "것입니다", "합니다", "했습니다", "대한",
}


def record_rank(row: dict) -> tuple:
    return (
        row["qualified"],
        row.get("freshness_status") == "FRESH",
        row["precheck_status"] == "PASS",
        row["grounding_status"] == "PASS",
        row["score"],
        len(row["text"]),
    )


def content_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[0-9A-Za-z가-힣]{2,}", (text or "").lower())
        if token not in DIVERSITY_STOPWORDS
    }


def near_duplicate_context(left: dict, right: dict) -> bool:
    left_text = re.sub(r"\s+", " ", left.get("text", "")).strip()
    right_text = re.sub(r"\s+", " ", right.get("text", "")).strip()
    if not left_text or not right_text:
        return False
    if left_text in right_text or right_text in left_text:
        return True
    left_topics = {term for term in TOPIC_MARKERS if term in left_text}
    right_topics = {term for term in TOPIC_MARKERS if term in right_text}
    if len(left_topics & right_topics) >= 2:
        return True
    left_tokens = content_tokens(left_text)
    right_tokens = content_tokens(right_text)
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))
    return overlap >= 0.66


def select_distinct_council_records(records: list[dict], source_url: str) -> list[dict]:
    """Keep multiple issues per minutes URL while collapsing overlapping windows."""
    grouped: dict[str, list[dict]] = {}
    for row in records:
        row["url"] = canonical_url(row["url"], source_url)
        grouped.setdefault(row["url"], []).append(row)
    selected: list[dict] = []
    for rows in grouped.values():
        chosen: list[dict] = []
        for row in sorted(rows, key=record_rank, reverse=True):
            if any(near_duplicate_context(row, prior) for prior in chosen):
                continue
            chosen.append(row)
            if len(chosen) >= 3:
                break
        selected.extend(chosen)
    return selected


def run_source(source: dict) -> tuple[dict, list[dict]]:
    timeout = int(source.get("timeout", 22))
    main = fetch(source["url"], timeout=timeout)
    fetches = [main]
    for _ in range(int(source.get("retry", 0))):
        if main.ok:
            break
        main = fetch(source["url"], timeout=timeout)
        fetches.append(main)
    if not main.ok:
        return (
            {
                "id": source["id"],
                "name": source["name"],
                "role": source["role"],
                "cadence": source.get("cadence", "continuous"),
                "main_url": source["url"],
                "http_ok": False,
                "status": main.status,
                "status_detail": "FETCH_FAILED",
                "error": main.error,
                "requests": len(fetches),
                "failed_requests": sum(not item.ok for item in fetches),
                "latency_ms": sum(item.elapsed_ms for item in fetches),
                "bytes": 0,
                "latest_date": "",
                "freshness_days": None,
                "extracted": 0,
                "precheck_pass": 0,
                "grounded": 0,
                "verification_usable": 0,
                "verification_metadata_leads": 0,
                "verification_schema_leads": 0,
                "qualified": 0,
                "localization_leads": 0,
                "strong": 0,
                "qualified_rate": 0.0,
                "median_score": 0,
                "fresh_qualified": 0,
                "fresh_strong": 0,
                "fresh_localization_leads": 0,
                "stale_carryover": 0,
                "archived_stale": 0,
                "freshness_unknown": 0,
            },
            [],
        )

    main_parser = parse_html(main.text)
    pages: list[tuple[str, VisibleHTML]] = [(main.url, main_parser)]
    for detail_url in select_follow_links(main_parser, main.url, source):
        detail = fetch(detail_url, timeout=timeout)
        fetches.append(detail)
        if detail.ok:
            pages.append((detail.url, parse_html(detail.text)))

    records: list[dict] = []
    page_dates: dict[str, str] = {}
    for index, (page_url, parser) in enumerate(pages):
        canonical_page = canonical_url(page_url, source["url"])
        page_dates[canonical_page] = document_date_from(parser)
        include_windows = index > 0 or source["id"] in {
            "labor_arrears", "eungdapso", "seoul_research"
        }
        records.extend(extract_records(parser, page_url, source, include_windows))

    for row in records:
        canonical_record = canonical_url(row.get("url", ""), source["url"])
        document_date = page_dates.get(canonical_record, "")
        reference_period = latest_period_label([row.get("text", "")])
        reference_effective_date = latest_date_from([row.get("text", "")])
        if (
            source["id"] in {"labor_arrears", "consumer_agency"}
            and row.get("record_kind") == "DATA_ROW"
            and reference_effective_date
        ):
            observed_date = reference_effective_date
            freshness_basis = "reference_period"
        else:
            observed_date = document_date
            freshness_basis = "document_date"
        row["document_date"] = document_date
        row["reference_period"] = reference_period
        row["reference_period_effective_date"] = reference_effective_date
        row.update(
            freshness_metadata(
                source,
                observed_date,
                basis=freshness_basis,
            )
        )

    if source["id"] == "council_minutes":
        item_records = select_distinct_council_records(records, source["url"])
    else:
        best_by_item: dict[str, dict] = {}
        for row in records:
            canonical = canonical_url(row["url"], source["url"])
            item_key = canonical
            if source["role"] == "VERIFICATION" and row.get("record_kind") == "DATA_ROW":
                text_key = re.sub(r"[^0-9A-Za-z가-힣]", "", row["text"]).lower()
                item_key = f"{canonical}#data-row:{text_key}"
            current = best_by_item.get(item_key)
            if current is None or record_rank(row) > record_rank(current):
                row["url"] = canonical
                best_by_item[item_key] = row
        if source["id"] == "eungdapso" and any(
            key != source["url"] and row["qualified"] for key, row in best_by_item.items()
        ):
            best_by_item.pop(source["url"], None)
        item_records = list(best_by_item.values())
        if source["role"] == "VERIFICATION":
            deduped: dict[str, dict] = {}
            for row in item_records:
                text_key = re.sub(r"[^0-9A-Za-z가-힣]", "", row["text"]).lower()
                current = deduped.get(text_key)
                if current is None or (row["qualified"], row["score"]) > (
                    current["qualified"], current["score"]
                ):
                    deduped[text_key] = row
            item_records = list(deduped.values())
    records = sorted(
        item_records,
        key=lambda item: (
            item["qualified"],
            item.get("freshness_status") == "FRESH",
            item["precheck_status"] == "PASS",
            item["grounding_status"] == "PASS",
            item["localization_lead"],
            item["score"],
        ),
        reverse=True,
    )[:120]

    known_dates = [
        value
        for value in (
            list(page_dates.values())
            + [row.get("source_date", "") for row in records]
        )
        if value
    ]
    latest = max(known_dates) if known_dates else ""
    freshness = (TODAY - date.fromisoformat(latest)).days if latest else None
    scores = [row["score"] for row in records]
    qualified = sum(row["qualified"] for row in records)
    verification_usable = sum(row["verification_usable"] for row in records)
    verification_metadata_leads = sum(
        row.get("verification_metadata_lead", False) for row in records
    )
    verification_schema_leads = sum(
        row.get("verification_schema_lead", False) for row in records
    )
    values_found = sum(bool(row["substantive_values"]) for row in records)
    status_detail = "OK"
    if (
        source["role"] == "VERIFICATION"
        and records
        and not verification_usable
        and verification_schema_leads
    ):
        status_detail = "DEGRADED_SCHEMA_ONLY"
    elif (
        source["role"] == "VERIFICATION"
        and records
        and not verification_usable
        and verification_metadata_leads
    ):
        status_detail = "DEGRADED_METADATA_ONLY"
    elif source["role"] == "VERIFICATION" and records and not verification_usable:
        status_detail = "DEGRADED_NO_DATASET_TEXT"
    elif source["id"] == "labor_arrears" and records and not values_found:
        status_detail = "DEGRADED_NO_VALUES"
    metric = {
        "id": source["id"],
        "name": source["name"],
        "role": source["role"],
        "cadence": source.get("cadence", "continuous"),
        "main_url": source["url"],
        "http_ok": True,
        "status": main.status,
        "status_detail": status_detail,
        "error": "",
        "requests": len(fetches),
        "failed_requests": sum(not item.ok for item in fetches),
        "latency_ms": sum(item.elapsed_ms for item in fetches),
        "bytes": sum(item.byte_count for item in fetches),
        "latest_date": latest,
        "freshness_days": freshness,
        "extracted": len(records),
        "precheck_pass": sum(row["precheck_status"] == "PASS" for row in records),
        "grounded": sum(row["grounding_status"] == "PASS" for row in records),
        "verification_usable": verification_usable,
        "verification_metadata_leads": verification_metadata_leads,
        "verification_schema_leads": verification_schema_leads,
        "qualified": qualified,
        "localization_leads": sum(row["localization_lead"] for row in records),
        "strong": sum(row["qualified"] and row["score"] >= 8 for row in records),
        "qualified_rate": round(qualified / len(records) * 100, 1) if records else 0.0,
        "median_score": round(statistics.median(scores), 1) if scores else 0,
        "fresh_qualified": sum(
            row["qualified"] and row.get("freshness_status") == "FRESH"
            for row in records
        ),
        "fresh_strong": sum(
            row["qualified"]
            and row.get("freshness_status") == "FRESH"
            and row["score"] >= 8
            for row in records
        ),
        "fresh_localization_leads": sum(
            row["localization_lead"] and row.get("freshness_status") == "FRESH"
            for row in records
        ),
        "stale_carryover": sum(
            row.get("freshness_status") == "STALE_CARRYOVER" for row in records
        ),
        "archived_stale": sum(
            row.get("freshness_status") == "ARCHIVED_STALE" for row in records
        ),
        "freshness_unknown": sum(
            row.get("freshness_status") in {"FRESHNESS_UNKNOWN", "FUTURE_DATED"}
            for row in records
        ),
    }
    return metric, records



def recommendation(metric: dict) -> str:
    fresh_qualified = metric.get("fresh_qualified", metric.get("qualified", 0))
    if metric.get("status_detail", "").startswith("DEGRADED_"):
        return "보류: 본문 값·데이터 설명 추출 개선 필요"
    if not metric["http_ok"] or metric["failed_requests"] > max(1, metric["requests"] // 2):
        return "보류: 접속 안정성 개선 필요"
    if (
        metric["role"] == "VERIFICATION"
        and metric.get("verification_usable", 0) >= 1
        and metric.get("qualified", 0) >= 1
    ):
        return "검증 데이터 지도에 편입"
    if metric.get("cadence") == "monthly" and fresh_qualified >= 1:
        return "월간 구조신호로 시험 편입"
    if fresh_qualified >= 5 and metric.get("fresh_strong", 0) >= 2:
        return "발굴 수집원 시험 편입"
    if fresh_qualified >= 2 or metric.get("fresh_localization_leads", 0) >= 2:
        return "보조 탐색원으로 추가 검증"
    return "보류: 유효 후보 부족"


def write_outputs(metrics: list[dict], records: list[dict], baseline: dict) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for metric in metrics:
        metric["recommendation"] = recommendation(metric)

    payload = {
        "generated_at_kst": NOW_KST.isoformat(timespec="seconds"),
        "method": {
            "qualified": "사업명과 독립된 문제 징후 또는 분해 가능한 구조 자료를 갖춘 서울형 사안",
            "strong": "유효후보 중 휴리스틱 8점 이상인 사안",
            "warning": "자동 점수는 편집 승인 점수가 아니며 상위 후보를 사람이 재검토해야 함",
        },
        "youtube_baseline": baseline,
        "sources": metrics,
        "records": records,
    }
    (OUTPUT / "performance_latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    csv_fields = [
        "source_id", "source_name", "role", "record_kind", "score", "content_class",
        "precheck_status", "precheck_reason", "evidence_anchor", "claim_status",
        "substantive_values", "verification_usable", "verification_metadata_lead", "verification_schema_lead",
        "seoul_scope", "scope_class", "scope_reason", "qualified",
        "localization_lead", "document_date", "reference_period",
        "reference_period_effective_date", "source_date", "freshness_days", "freshness_window_days", "carryover_until_days",
        "freshness_status", "cadence", "freshness_basis",
        "question_basis", "question", "verification_axes",
        "grounding_status", "grounding_issues", "text", "reasons", "url",
    ]
    with (OUTPUT / "candidates_latest.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_fields)
        writer.writeheader()
        for row in records:
            export = {key: row.get(key, "") for key in csv_fields}
            export["reasons"] = ", ".join(row["reasons"])
            for field in ("substantive_values", "verification_axes", "grounding_issues"):
                if isinstance(export.get(field), list):
                    export[field] = ", ".join(export[field])
            writer.writerow(export)

    lines = [
        "# 새 소스 성능 시험",
        "",
        f"- 실행 시각: {NOW_KST:%Y-%m-%d %H:%M} KST",
        "- 판정 단위: 접속성, 추출량, 서울형 유효후보, 강한 후보, 최신성, 수집비용",
        "- 주의: 자동 점수는 후보 정렬용이며 아이템 통과 판정이 아닙니다.",
        "",
        "## 결과 요약",
        "",
        "| 소스 | 역할 | 접속 상태 | 요청/실패 | 추출 | 사전통과 | 질문일치 | 유효후보 | 신선 유효 | STALE | 날짜미상 | 최신일 | 판단 |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for metric in metrics:
        access = (f"HTTP {metric['status']} · {metric['status_detail']}"
                  if metric["http_ok"] else metric["error"])
        lines.append(
            f"| {metric['name']} | {metric['role']} | {access} | "
            f"{metric['requests']}/{metric['failed_requests']} | {metric['extracted']} | "
            f"{metric['precheck_pass']} | {metric['grounded']} | {metric['qualified']} | "
            f"{metric.get('fresh_qualified', 0)} | {metric.get('stale_carryover', 0)} | "
            f"{metric.get('freshness_unknown', 0)} | {metric['latest_date'] or '-'} | "
            f"{metric['recommendation']} |"
        )

    lines.extend(
        [
            "",
            "## 기존 YouTube 기준선",
            "",
            f"- 전체 레코드: {baseline['total']}",
            f"- 당사자·현장·상담형: {baseline['direct_voice_or_field']}",
            f"- 서울 단서: {baseline['seoul']}",
            f"- 당사자·현장형이면서 서울 단서 보유: {baseline['direct_and_seoul']} "
            f"({baseline['direct_and_seoul_rate']}%)",
            "",
            "이 비교는 동일한 정답률 비교가 아니라, 기존 수집원의 취약 지점인 "
            "직접 목소리·현장성과 서울성을 새 소스가 보완하는지 보는 기준선입니다.",
        ]
    )

    for metric in metrics:
        subset = [
            row for row in records
            if row["source_id"] == metric["id"]
            and (
                row["qualified"]
                or row["localization_lead"]
                or row.get("verification_schema_lead")
                or row.get("verification_metadata_lead")
            )
        ][:6]
        lines.extend(["", f"## {metric['name']}", ""])
        if not subset:
            lines.append("- 검토할 수준의 후보를 추출하지 못했습니다.")
            continue
        for index, row in enumerate(subset, 1):
            tag = (
                "검증 자산" if row["role"] == "VERIFICATION" and row["qualified"]
                else "스키마 확인·값 미수집" if row.get("verification_schema_lead")
                else "데이터셋 제목·스키마 미확인" if row.get("verification_metadata_lead")
                else "서울형 유효후보" if row["qualified"]
                else "서울 현지화 필요"
            )
            lines.extend(
                [
                    f"### {index}. {tag} · 수집 정렬점수 {row['score']}",
                    "",
                    f"- 단서: {row['text']}",
                    f"- 내용 사전판정: {row['precheck_status']} · {row['content_class']}",
                    f"- 근거 앵커: {row['evidence_anchor']} ({row['claim_status']})",
                    f"- 질문 근거: {row['question_basis']}",
                    f"- 붙일 질문: {row['question']}",
                    f"- 추가 확인 변수: {', '.join(row['verification_axes']) or '-'}",
                    f"- 질문-근거 일치: {row['grounding_status']}",
                    f"- 근거 요소: {', '.join(row['reasons'])}",
                    f"- 원문: {row['url']}",
                    "",
                ]
            )

    lines.extend(
        [
            "## 정식 편입 전 사람 검토 항목",
            "",
            "1. 상위 후보 20개 중 실제 기획 질문으로 발전하는 비율",
            "2. 같은 사안을 되풀이한 중복 문구 비율",
            "3. 4시간 안에 원자료·반대 근거·당사자 접촉 경로를 확보할 수 있는지",
            "4. 서울 단서가 소스 이름에만 있고 실제 내용에는 없는 허위 서울성 여부",
            "5. 행사·홍보·단순 민원 안내가 다시 섞이는 비율",
            "",
        ]
    )
    (OUTPUT / "performance_latest.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    metrics: list[dict] = []
    records: list[dict] = []
    for source in SOURCES:
        metric, source_records = run_source(source)
        metrics.append(metric)
        records.extend(source_records)
        print(
            f"{source['id']}: status={metric['status']} requests={metric['requests']} "
            f"extracted={metric['extracted']} qualified={metric['qualified']} "
            f"strong={metric['strong']}"
        )
    records.sort(key=lambda row: (row["qualified"], row["localization_lead"], row["score"]), reverse=True)
    write_outputs(metrics, records, youtube_baseline())
    accessible = sum(metric["http_ok"] for metric in metrics)
    if accessible < 3:
        print(f"Only {accessible}/{len(metrics)} sources were accessible.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
