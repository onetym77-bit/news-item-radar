#!/usr/bin/env python3
"""Collect and quality-gate public interest signals from Google News RSS and Naver DataLab."""
from __future__ import annotations
import json, os, re, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "interest-signal-pilot" / "output" / "interest_signals_latest.json"
QUERIES = ["서울 민원", "서울 건설 공사 지연", "서울 안전 사고", "서울 재개발 갈등", "서울 교통 불편", "서울 주거 피해", "서울 복지 공백", "서울 자치구 논란"]
SEOUL_AREAS = ["서울", "종로", "중구", "용산", "성동", "광진", "동대문", "중랑", "성북", "강북", "도봉", "노원", "은평", "서대문", "마포", "양천", "강서", "구로", "금천", "영등포", "동작", "관악", "서초", "강남", "송파", "강동"]
SEOUL_NAME_ONLY = ("서울뉴스", "서울연구원", "서울본부", "서울자치신문", "서울뉴스통신")
ROUTINE_TERMS = ("운영", "확대 운영", "제공", "개최", "안내", "홍보", "캠페인", "연휴", "발급기", "챗봇", "종합대책", "예방 총력", "시행…")
IMPACT_TERMS = ("갈등", "논란", "지연", "피해", "공백", "부담", "반발", "폐쇄", "위험", "사고", "누락", "사기", "예산", "책임")
CONSTRUCTION_TERMS = ("건설", "착공", "준공", "공기", "지하차도", "도로 공사", "사업 지연", "공사비")
TRANSIT_TERMS = ("열차", "지하철", "운행", "출발", "역사", "또타", "지연 정보", "지연정보")
RSS_TEMPLATE = "https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
NAVER_URL = "https://openapi.naver.com/v1/datalab/search"
USER_AGENT = "news-item-radar/interest-signal-pilot"

def clean(value: str | None) -> str:
    return " ".join((value or "").split())

def title_key(value: str) -> str:
    value = value.lower()
    value = re.sub(r"\[[^]]+\]|【[^】]+】|\([^)]*\)", " ", value)
    value = re.sub(r"[^0-9a-z가-힣]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def seoul_relevance(title: str, summary: str) -> tuple[bool, str]:
    headline = re.split(r"\s[-|]\s", title, maxsplit=1)[0].strip()
    for area in SEOUL_AREAS:
        if area not in headline:
            continue
        if area == "서울" and any(name in headline for name in SEOUL_NAME_ONLY):
            continue
        return True, f"기사 제목의 지역 표현: {area}"
    return False, "기사 제목에서 서울·자치구 명칭 미확인"

def classify_editorial_signal(title: str, summary: str) -> tuple[bool, str]:
    text = f"{title} {summary}"
    is_transit_delay = "지연" in text and any(term in text for term in TRANSIT_TERMS) and not any(term in text for term in CONSTRUCTION_TERMS)
    if is_transit_delay:
        return False, "교통 운행 지연으로 건설사업 지연과 구분 필요"
    has_impact = any(term in text for term in IMPACT_TERMS)
    strong_routine = any(term in text for term in ("종합대책", "예방 총력", "명절 대책", "안전관리 강화"))\n    is_routine = any(term in text for term in ROUTINE_TERMS) and (not has_impact or strong_routine)
    if is_routine:
        return False, "기관 운영·홍보성 안내로 기획 후보 우선순위 하향"
    if has_impact or any(term in text for term in CONSTRUCTION_TERMS):
        return True, "갈등·지연·피해·책임 또는 건설사업 단서 확인"
    return False, "시민 영향·갈등·책임 단서 부족"


def fetch_news(query: str) -> list[dict]:
    request = urllib.request.Request(RSS_TEMPLATE.format(query=urllib.parse.quote_plus(query)), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        root = ET.fromstring(response.read())
    rows = []
    for item in root.findall("./channel/item"):
        title, link = clean(item.findtext("title")), clean(item.findtext("link"))
        if not title or not link:
            continue
        summary = clean(re.sub("<[^>]+>", " ", item.findtext("description") or ""))[:500]
        relevant, reason = seoul_relevance(title, summary)
        editorial_eligible, editorial_reason = classify_editorial_signal(title, summary)
        rows.append({"query": query, "title": title, "url": link, "published_at": clean(item.findtext("pubDate")), "summary": summary, "seoul_relevant": relevant, "relevance_reason": reason, "editorial_eligible": editorial_eligible, "editorial_reason": editorial_reason, "signal_type": "NEWS_ATTENTION", "status": "DISCOVERY_SIGNAL"})
    return rows

def fetch_naver_trends() -> tuple[list[dict], str | None, int, list[str]]:
    client_id, client_secret = os.getenv("NAVER_CLIENT_ID", "").strip(), os.getenv("NAVER_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return [], "missing_credentials", 0, []
    today, start = datetime.now(timezone.utc).date(), datetime.now(timezone.utc).date() - timedelta(days=14)
    rows, groups_seen, groups_without_data = [], 0, []
    for query in QUERIES[:5]:
        body = {"startDate": start.isoformat(), "endDate": today.isoformat(), "timeUnit": "date", "keywordGroups": [{"groupName": query, "keywords": [query]}]}
        request = urllib.request.Request(NAVER_URL, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers={"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret, "Content-Type": "application/json", "User-Agent": USER_AGENT}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                result = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            return rows, f"{query}:{type(exc).__name__}", groups_seen, groups_without_data
        groups = result.get("results", [])
        if not groups:
            groups_without_data.append(query)
            continue
        for group in groups:
            groups_seen += 1
            title, data = group.get("title", query), group.get("data", [])
            if not data:
                groups_without_data.append(title)
            for point in data:
                rows.append({"query": title, "period": point.get("period"), "relative_ratio": point.get("ratio"), "signal_type": "NAVER_SEARCH_TREND", "status": "DISCOVERY_SIGNAL"})
    return rows, None, groups_seen, groups_without_data

def diversify_news(rows: list[dict], limit: int = 120) -> list[dict]:
    """Interleave query groups so one search term cannot fill the whole snapshot."""
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row.get("query", "기타"), []).append(row)
    output = []
    while grouped and len(output) < limit:
        for query in list(grouped):
            output.append(grouped[query].pop(0))
            if not grouped[query]:
                del grouped[query]
            if len(output) >= limit:
                break
    return output


def main() -> int:
    raw_news, errors = [], []
    for query in QUERIES:
        try:
            raw_news.extend(fetch_news(query))
        except Exception as exc:
            errors.append({"channel": "google_news_rss", "query": query, "error": type(exc).__name__})
    relevant_news = [row for row in raw_news if row["seoul_relevant"]]
    unique = {}
    for row in relevant_news:
        key = title_key(row["title"])
        if key and key not in unique:
            unique[key] = row
    news = list(unique.values())
    trends, trend_error, trend_groups, trend_groups_without_data = fetch_naver_trends()
    if trend_error:
        errors.append({"channel": "naver_datalab", "error": trend_error})
    trend_summary, by_query = [], {}
    for row in trends:
        by_query.setdefault(row["query"], []).append(row)
    for query, rows in by_query.items():
        rows = [r for r in rows if isinstance(r.get("relative_ratio"), (int, float))]
        if not rows:
            continue
        peak, latest = max(rows, key=lambda r: r["relative_ratio"]), max(rows, key=lambda r: r.get("period") or "")
        trend_summary.append({"query": query, "peak_period": peak.get("period"), "peak_ratio": peak.get("relative_ratio"), "latest_period": latest.get("period"), "latest_ratio": latest.get("relative_ratio"), "data_points": len(rows)})
    payload = {
        "schema": 5, "generated_at_utc": datetime.now(timezone.utc).isoformat(), "source_id": "search_news_interest", "source_name": "검색 관심도·뉴스 확산",
        "collection_mode": ["google_news_rss_keyword_probe", "naver_datalab_search_trend"], "queries": QUERIES,
        "quality_gate": {"raw_news_count": len(raw_news), "seoul_relevant_count": len(relevant_news), "unique_news_count": len(news), "duplicate_or_irrelevant_count": len(raw_news) - len(news), "trend_groups": trend_groups, "trend_groups_without_data": trend_groups_without_data, "trend_data_points": len(trends), "candidate_ready": False, "reason": "관심 신호는 탐색용이며, 후보 승격 전 원문·시민 영향·책임 주체 확인 필요"},
        "news_count": len(news), "trend_count": len(trends), "news_signals": diversify_news(news), "trend_signals": trends[:500], "trend_summary": trend_summary, "errors": errors,
        "limitations": ["네이버 데이터랩 ratio는 절대 검색량이 아닌 상대 지수임", "검색·뉴스 반복은 시민 전체 의견이나 사실 확정이 아님", "동일·유사 제목은 묶었지만 기사 내용의 사실성은 검증하지 않음", "지역성은 기사 제목 기준의 1차 분류이며 최종 사실 확인이 아님", "후보 승격 전 서울시의회·구의회·감사·통계·현장 확인 필요"],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"raw_news={len(raw_news)} relevant={len(relevant_news)} unique={len(news)} trends={len(trends)} errors={len(errors)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
