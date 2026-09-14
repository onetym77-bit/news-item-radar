#!/usr/bin/env python3
"""Pilot collector for testing non-YouTube source families.

The output is diagnostic. A heuristic-qualified lead is not an approved story item;
editors still have to test the question, counter-evidence and reporting feasibility.
"""

from __future__ import annotations

import csv
import json
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


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(__file__).resolve().parent / "output"
NOW_KST = datetime.now(timezone(timedelta(hours=9)))
TODAY = NOW_KST.date()
USER_AGENT = "Mozilla/5.0 (compatible; NewsItemRadar/1.0; +https://github.com/onetym77-bit/news-item-radar)"

SOURCES = [
    {
        "id": "eungdapso",
        "name": "서울시 응답소 공개민원",
        "url": "https://eungdapso.seoul.go.kr/exp/pub/complaint_pub_lis.do",
        "role": "DISCOVERY",
        "local": True,
        "voice": True,
        "follow": r"complaint.*(?:view|vie|read|detail)|complaint_pub.*\.do",
        "max_follow": 8,
    },
    {
        "id": "council_minutes",
        "name": "서울시의회 회의록",
        "url": "https://ms.smc.seoul.kr/kr/assembly/main.do",
        "role": "BOTH",
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
        "id": "labor_arrears",
        "name": "고용노동부 임금체불 통계",
        "url": "https://labor.moel.go.kr/arrstat/sttcStusList.do",
        "role": "BOTH",
        "local": False,
        "voice": False,
        "follow": "",
        "max_follow": 0,
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
    "격차", "불균형", "부족", "불편", "피해", "사고", "체불", "미지급", "폐업",
    "급증", "급감", "증가", "감소", "지연", "혼잡", "위험", "미달", "초과",
    "사각지대", "제한", "불용", "삭감", "적자", "위반", "민원", "환불", "해지",
    "부실", "제외", "중단", "갈등", "논란", "노후", "고령", "장애", "폭염",
    "침수", "붕괴", "과밀", "공백", "부담", "취약", "분쟁",
)
EVIDENCE_TERMS = (
    "통계", "현황", "실태", "조사", "예산", "결산", "감사", "분석", "결과",
    "집행률", "이용률", "증감", "건수", "비율", "측정값", "발생률",
)
IMPLEMENTATION_TERMS = (
    "대책", "지원", "운영", "제도", "조례", "정책", "사업", "집행", "대상",
    "기준", "계획", "시행", "관리", "점검", "배정", "공급",
)
LOSS_TERMS = (
    "비용", "요금", "부담", "손실", "피해", "체불", "미지급", "환불", "생계",
    "폐업", "소득", "안전", "대기", "시간",
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

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
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


def valid_candidate(text: str) -> bool:
    if len(text) < 12 or len(text) > 280 or not KOREAN_RE.search(text):
        return False
    if any(term in text for term in NAV_TERMS):
        return False
    if text.count("|") > 5:
        return False
    return True


def context_windows(chunks: list[str], limit: int = 45) -> list[str]:
    joined = " · ".join(chunks)
    windows: list[str] = []
    seen: set[str] = set()
    for term in PROBLEM_TERMS + EVIDENCE_TERMS:
        start = 0
        while len(windows) < limit:
            pos = joined.find(term, start)
            if pos < 0:
                break
            left = max(0, pos - 95)
            right = min(len(joined), pos + 155)
            window = normalize(joined[left:right]).strip(" ·")
            key = window[:160]
            if valid_candidate(window) and key not in seen:
                seen.add(key)
                windows.append(window)
            start = pos + len(term)
        if len(windows) >= limit:
            break
    return windows


def score_text(text: str, source: dict) -> tuple[int, list[str], bool, dict]:
    score = 0
    reasons: list[str] = []
    explicit_seoul = any(marker in text for marker in ("서울", "자치구", "한강", "수도권"))
    seoul_scope = source["local"] or explicit_seoul
    problem = any(term in text for term in PROBLEM_TERMS)
    evidence = any(term in text for term in EVIDENCE_TERMS) or bool(NUMBER_RE.search(text))
    implementation = any(term in text for term in IMPLEMENTATION_TERMS)
    loss = any(term in text for term in LOSS_TERMS)
    low_value = any(term in text for term in LOW_VALUE_TERMS)
    boilerplate = any(term in text for term in BOILERPLATE_TERMS)

    if seoul_scope:
        score += 2 if explicit_seoul else 1
        reasons.append("서울 범위")
    if problem:
        score += 2
        reasons.append("문제·변화")
    if evidence:
        score += 2
        reasons.append("수치·공개근거")
    if implementation:
        score += 1
        reasons.append("제도·집행")
    if loss:
        score += 1
        reasons.append("시민 손실")
    if source["voice"] and ("?" in text or "문의" in text or "민원" in text):
        score += 1
        reasons.append("시민 직접질문")
    if source["role"] in {"BOTH", "VERIFICATION"}:
        score += 1
        reasons.append("독립 검증원")
    if low_value:
        score -= 3
        reasons.append("행사·홍보 감점")
    if boilerplate or text.count("·") > 10:
        score -= 3
        reasons.append("목록·반복문구 감점")

    signals = {
        "problem": problem,
        "evidence": evidence,
        "implementation": implementation,
        "loss": loss,
        "low_value": low_value,
        "boilerplate": boilerplate,
    }
    return score, reasons, seoul_scope, signals

def question_for(text: str, source: dict) -> str:
    if source["voice"]:
        return "이 불편은 개인 사례인가, 반복되는 제도 공백인가?"
    if any(term in text for term in ("격차", "불균형", "집중", "편중")):
        return "지역·대상별 격차는 얼마나 크고, 제도 설계가 이를 키우는가?"
    if any(term in text for term in ("예산", "집행", "불용", "삭감")):
        return "예산 규모와 실제 집행·수혜 사이에 누수나 배제는 없는가?"
    if NUMBER_RE.search(text) or any(term in text for term in ("통계", "현황", "조사")):
        return "공개된 총량 뒤에 어떤 지역·대상·업종 집중이 가려져 있는가?"
    if any(term in text for term in LOSS_TERMS):
        return "누가 비용·시간·안전의 손실을 떠안고 있으며 왜 지금 드러났는가?"
    return "이 변화는 일시적 사례인가, 구조적으로 반복되는 현상인가?"


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
        else:
            relevance = 1
        seen.add(absolute)
        ranked.append((relevance, absolute))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [url for _, url in ranked[: source["max_follow"]]]


def extract_records(
    parser: VisibleHTML,
    page_url: str,
    source: dict,
    include_windows: bool,
) -> list[dict]:
    texts: list[tuple[str, str]] = []
    for href, label in parser.anchors:
        if valid_candidate(label):
            texts.append((label, urljoin(page_url, href)))
    for chunk in parser.chunks:
        if valid_candidate(chunk):
            texts.append((chunk, page_url))
    if include_windows:
        for window in context_windows(parser.chunks, limit=20):
            texts.append((window, page_url))

    records: list[dict] = []
    seen: set[str] = set()
    for text, url in texts:
        key = re.sub(r"[^0-9A-Za-z가-힣]", "", text).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        score, reasons, seoul_scope, signals = score_text(text, source)
        if score < 2:
            continue
        if source["role"] == "VERIFICATION":
            quality_gate = signals["evidence"] and (signals["implementation"] or signals["problem"])
        else:
            quality_gate = signals["problem"] and (signals["evidence"] or signals["loss"])
        qualified = score >= 6 and seoul_scope and quality_gate and not signals["low_value"]
        localization_lead = score >= 7 and not seoul_scope and quality_gate and not signals["low_value"]
        records.append(
            {
                "source_id": source["id"],
                "source_name": source["name"],
                "role": source["role"],
                "text": text,
                "url": url,
                "score": score,
                "reasons": reasons,
                "signals": signals,
                "seoul_scope": seoul_scope,
                "qualified": qualified,
                "localization_lead": localization_lead,
                "question": question_for(text, source),
            }
        )
    records.sort(key=lambda row: (row["qualified"], row["score"], len(row["text"])), reverse=True)
    return records[:80]


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
    return max(found).isoformat() if found else ""


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


def run_source(source: dict) -> tuple[dict, list[dict]]:
    main = fetch(source["url"])
    fetches = [main]
    if not main.ok:
        return (
            {
                "id": source["id"],
                "name": source["name"],
                "role": source["role"],
                "main_url": source["url"],
                "http_ok": False,
                "status": main.status,
                "error": main.error,
                "requests": 1,
                "failed_requests": 1,
                "latency_ms": main.elapsed_ms,
                "bytes": 0,
                "latest_date": "",
                "freshness_days": None,
                "extracted": 0,
                "qualified": 0,
                "localization_leads": 0,
                "strong": 0,
                "qualified_rate": 0.0,
                "median_score": 0,
            },
            [],
        )

    main_parser = parse_html(main.text)
    pages: list[tuple[str, VisibleHTML]] = [(main.url, main_parser)]
    for detail_url in select_follow_links(main_parser, main.url, source):
        detail = fetch(detail_url)
        fetches.append(detail)
        if detail.ok:
            pages.append((detail.url, parse_html(detail.text)))

    records: list[dict] = []
    for index, (page_url, parser) in enumerate(pages):
        include_windows = index > 0 or source["id"] == "labor_arrears"
        records.extend(extract_records(parser, page_url, source, include_windows))

    # Performance is measured per distinct source item/page, not per matching sentence.
    # This prevents one long council speech or dataset description from inflating yield.
    best_by_item: dict[str, dict] = {}
    for row in records:
        item_key = canonical_url(row["url"], source["url"])
        current = best_by_item.get(item_key)
        if current is None or (row["qualified"], row["score"], len(row["text"])) > (
            current["qualified"], current["score"], len(current["text"])
        ):
            row["url"] = item_key
            best_by_item[item_key] = row
    records = sorted(
        best_by_item.values(),
        key=lambda item: (item["qualified"], item["localization_lead"], item["score"]),
        reverse=True,
    )[:120]

    all_chunks = [chunk for _, parser in pages for chunk in parser.chunks]
    latest = latest_date_from(all_chunks)
    freshness = (TODAY - date.fromisoformat(latest)).days if latest else None
    scores = [row["score"] for row in records]
    qualified = sum(row["qualified"] for row in records)
    metric = {
        "id": source["id"],
        "name": source["name"],
        "role": source["role"],
        "main_url": source["url"],
        "http_ok": True,
        "status": main.status,
        "error": "",
        "requests": len(fetches),
        "failed_requests": sum(not item.ok for item in fetches),
        "latency_ms": sum(item.elapsed_ms for item in fetches),
        "bytes": sum(item.byte_count for item in fetches),
        "latest_date": latest,
        "freshness_days": freshness,
        "extracted": len(records),
        "qualified": qualified,
        "localization_leads": sum(row["localization_lead"] for row in records),
        "strong": sum(row["qualified"] and row["score"] >= 8 for row in records),
        "qualified_rate": round(qualified / len(records) * 100, 1) if records else 0.0,
        "median_score": round(statistics.median(scores), 1) if scores else 0,
    }
    return metric, records


def recommendation(metric: dict) -> str:
    if not metric["http_ok"] or metric["failed_requests"] > max(1, metric["requests"] // 2):
        return "보류: 접속 안정성 개선 필요"
    if metric["role"] == "VERIFICATION" and metric["extracted"] >= 3:
        return "검증 데이터 지도에 편입"
    if metric["qualified"] >= 5 and metric["strong"] >= 2:
        return "발굴 수집원 시험 편입"
    if metric["qualified"] >= 2 or metric["localization_leads"] >= 2:
        return "보조 탐색원으로 추가 검증"
    return "보류: 유효 후보 부족"


def write_outputs(metrics: list[dict], records: list[dict], baseline: dict) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for metric in metrics:
        metric["recommendation"] = recommendation(metric)

    payload = {
        "generated_at_kst": NOW_KST.isoformat(timespec="seconds"),
        "method": {
            "qualified": "서로 다른 원문 단위로 문제성과 근거 또는 시민손실을 함께 충족한 서울형 사안",
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
        "source_id", "source_name", "role", "score", "seoul_scope", "qualified",
        "localization_lead", "text", "question", "reasons", "url",
    ]
    with (OUTPUT / "candidates_latest.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_fields)
        writer.writeheader()
        for row in records:
            export = {key: row.get(key, "") for key in csv_fields}
            export["reasons"] = ", ".join(row["reasons"])
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
        "| 소스 | 역할 | 접속 | 요청/실패 | 추출 | 유효후보 | 강한후보 | 유효율 | 최신일 | 판단 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for metric in metrics:
        access = f"HTTP {metric['status']}" if metric["http_ok"] else metric["error"]
        lines.append(
            f"| {metric['name']} | {metric['role']} | {access} | "
            f"{metric['requests']}/{metric['failed_requests']} | {metric['extracted']} | "
            f"{metric['qualified']} | {metric['strong']} | {metric['qualified_rate']}% | "
            f"{metric['latest_date'] or '-'} | {metric['recommendation']} |"
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
            if row["source_id"] == metric["id"] and (row["qualified"] or row["localization_lead"])
        ][:6]
        lines.extend(["", f"## {metric['name']}", ""])
        if not subset:
            lines.append("- 검토할 수준의 후보를 추출하지 못했습니다.")
            continue
        for index, row in enumerate(subset, 1):
            tag = "서울형 유효후보" if row["qualified"] else "서울 현지화 필요"
            lines.extend(
                [
                    f"### {index}. {tag} · {row['score']}점",
                    "",
                    f"- 단서: {row['text']}",
                    f"- 붙일 질문: {row['question']}",
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
