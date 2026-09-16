#!/usr/bin/env python3
"""Bounded Eungdapso statistics watch.

This pilot observes aggregate complaint counts. Counts are submissions, not
people or verified harm. Separate one-dimensional tables are never joined into
an invented district-by-topic cross table.
"""
import argparse
import json
import re
import statistics
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.request import Request, build_opener
from zoneinfo import ZoneInfo

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "off-session-pilot"))
from probe_sources import OfficialRedirect, Page, sanitize

URL = "https://eungdapso.seoul.go.kr/gud/chart/chart_progress.do"
BASE = Path(__file__).resolve().parent
OUT = BASE / "output"
SCHEMA = 1
MAX_SNAPSHOTS = 40
DISTRICTS = (
    "강남구", "강동구", "강북구", "강서구", "관악구", "광진구", "구로구", "금천구",
    "노원구", "도봉구", "동대문구", "동작구", "마포구", "서대문구", "서초구", "성동구",
    "성북구", "송파구", "양천구", "영등포구", "용산구", "은평구", "종로구", "중구", "중랑구",
)
CHANNELS = ("홈페이지", "전화", "문자", "모바일앱", "국민신문고", "기타")
TOPICS = ("교통", "환경/안전", "복지/문화/경제", "주택/건설", "기타")
AGENCIES = ("서울시", "자치구", "투자출연기관", "기타")
COUNT = r"([\d,]+)\s*건"

def now_kst():
    return datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")

def fetch_html():
    request = Request(URL, headers={
        "User-Agent": "NewsItemRadarReadOnlyPilot/1.0",
        "Accept-Language": "ko",
    })
    with build_opener(OfficialRedirect()).open(request, timeout=18) as response:
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("response exceeds 2 MB watch limit")
        for encoding in (response.headers.get_content_charset(), "utf-8", "cp949"):
            if encoding:
                try:
                    return raw.decode(encoding)
                except (UnicodeDecodeError, LookupError):
                    pass
    raise ValueError("unknown text encoding")

def visible_text(html):
    return sanitize(re.sub(r"\s+", " ", " ".join(Page(html).chunks))).strip()

def count_after(text, label):
    match = re.search(re.escape(label) + r"\s*(?:[:|]|\()?\s*" + COUNT, text)
    if not match:
        raise ValueError(f"missing count for {label}")
    return int(match.group(1).replace(",", ""))

def section(text, start, end=None):
    at = text.find(start)
    if at < 0:
        raise ValueError(f"missing section {start}")
    stop = text.find(end, at + len(start)) if end else len(text)
    if stop < 0:
        raise ValueError(f"missing section boundary {end}")
    return text[at:stop]

def axis(section_text, labels):
    return {label: count_after(section_text, label) for label in labels}

def full_day(month_day, as_of):
    month, day = map(int, month_day.split("."))
    year = as_of.year
    candidate = date(year, month, day)
    if candidate >= as_of:
        candidate = date(year - 1, month, day)
    return candidate.isoformat()

def parse_snapshot(html):
    text = visible_text(html)
    as_of_match = re.search(r"(20\d{2})[.]\s*(\d{1,2})[.]\s*(\d{1,2})\s*현재", text)
    if not as_of_match:
        raise ValueError("reference date missing")
    as_of = date(*map(int, as_of_match.groups()))
    total = count_after(text, "기간 내 민원 건 수")
    today = count_after(text, "오늘")
    previous_day = count_after(text, "전일")

    trend_text = section(text, "민원현황 추이 " + as_of.strftime("%Y.%m.%d") + " 현재", "자치구별")
    daily = [
        {"date": full_day(md, as_of), "count": int(raw.replace(",", ""))}
        for md, raw in re.findall(r"(\d{2}[.]\d{2})\((" + r"[\d,]+" + r")건\)", trend_text)
    ]
    if len(daily) < 20:
        raise ValueError("daily trend parse degraded")

    district_text = section(text, "자치구별 " + as_of.strftime("%Y.%m.%d") + " 현재",
                            "자치구별 대체 텍스트")
    channel_text = section(text, "분야별 민원현황 홈페이지", "분야별 민원현황 교통")
    topic_text = section(text, "분야별 민원현황 교통", "처리기관별 민원현황 서울시")
    agency_text = section(text, "처리기관별 민원현황 서울시", "자동 로그아웃 안내")

    districts = axis(district_text, DISTRICTS)
    channels = axis(channel_text, CHANNELS)
    topics = axis(topic_text, TOPICS)
    agencies = axis(agency_text, AGENCIES)

    checks = {
        "daily_equals_total": sum(x["count"] for x in daily) == total,
        "channels_equal_total": sum(channels.values()) == total,
        "topics_equal_total": sum(topics.values()) == total,
        "agencies_equal_total": sum(agencies.values()) == total,
        "districts_equal_district_agency": sum(districts.values()) == agencies["자치구"],
        "last_daily_precedes_reference": daily[-1]["date"] == (as_of - timedelta(days=1)).isoformat(),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError("integrity check failed: " + ", ".join(failed))
    return {
        "reference_date": as_of.isoformat(),
        "period_start": daily[0]["date"],
        "period_end": daily[-1]["date"],
        "rolling_total": total,
        "headline_today": today,
        "headline_previous_day": previous_day,
        "daily": daily,
        "districts": districts,
        "channels": channels,
        "topics": topics,
        "agencies": agencies,
        "integrity": checks,
        "source_url": URL,
        "units": {
            "count": "complaint_submissions_not_people",
            "districts": "handling_districts_not_complainant_residence",
            "tables": "independent_one_dimensional_aggregates",
        },
    }

def empty_state():
    return {"schema": SCHEMA, "last_checked_kst": None, "snapshots": [], "last_run": {}}

def validate_state(state):
    if state.get("schema") != SCHEMA or not isinstance(state.get("snapshots"), list):
        raise ValueError("invalid state")
    return state

def shares(values):
    total = sum(values.values())
    return {key: (value / total * 100 if total else 0.0) for key, value in values.items()}

def signal(kind, observation, question):
    return {
        "kind": kind,
        "observation": observation,
        "verification_question": question,
        "question_status": "PRE_EDITORIAL_VERIFY",
        "article_gate": "NOT_EVALUATED",
        "source_url": URL,
    }

def compare(prior, snapshot, checked_at):
    prior = validate_state(prior)
    snapshots = list(prior["snapshots"])
    previous = snapshots[-1] if snapshots else None
    first_baseline = previous is None
    reference_status = "FIRST_BASELINE" if first_baseline else "ADVANCED"
    signals = []

    if previous and snapshot["reference_date"] == previous["reference_date"]:
        reference_status = "UNCHANGED"
        snapshots[-1] = snapshot
    elif previous and snapshot["reference_date"] < previous["reference_date"]:
        raise ValueError("reference date moved backwards")
    else:
        snapshots.append(snapshot)

    if previous and reference_status == "ADVANCED":
        latest = snapshot["daily"][-1]
        latest_date = date.fromisoformat(latest["date"])
        peers = [x["count"] for x in snapshot["daily"][:-1]
                 if date.fromisoformat(x["date"]).weekday() == latest_date.weekday()]
        if len(peers) >= 3:
            median = statistics.median(peers)
            difference = latest["count"] - median
            relative = difference / median if median else 0.0
            if abs(difference) >= 1000 and abs(relative) >= 0.30:
                direction = "높음" if difference > 0 else "낮음"
                signals.append(signal(
                    "SAME_WEEKDAY_VOLUME_OUTLIER",
                    f"{latest['date']} 접수 {latest['count']:,}건은 앞선 같은 요일 중앙값 "
                    f"{median:,.0f}건보다 {abs(relative) * 100:.1f}% {direction}.",
                    "접수 경로의 장애·캠페인·중복 접수나 특정 사건으로 설명되는가? "
                    "민원 원문 표본과 업무 시스템 변경을 확인하기 전 시민 피해 증가로 해석하지 않는다.",
                ))

        for field, label, denominator in (
            ("channels", "접수경로", "전체 접수"),
            ("topics", "분야", "전체 접수"),
            ("agencies", "처리기관", "전체 접수"),
            ("districts", "자치구 처리기관", "자치구 처리 접수"),
        ):
            before = shares(previous[field])
            after = shares(snapshot[field])
            moved = []
            for key in after:
                delta = after[key] - before.get(key, 0.0)
                if abs(delta) >= 1.0:
                    moved.append((abs(delta), key, delta, before.get(key, 0.0), after[key]))
            for _, key, delta, old, new in sorted(moved, reverse=True)[:2]:
                signals.append(signal(
                    "SHARE_SHIFT_" + field.upper(),
                    f"{label} 중 {key} 비중이 {old:.1f}%→{new:.1f}%({delta:+.1f}%p). "
                    f"분모는 {denominator}.",
                    "실제 불편 구성의 변화인가, 분류·배정·신고 경로 변화인가? "
                    "같은 기간의 세부 원문과 집계 정의를 확인하며 서로 다른 표를 교차표처럼 결합하지 않는다.",
                ))
    snapshots = snapshots[-MAX_SNAPSHOTS:]
    return {
        "schema": SCHEMA,
        "last_checked_kst": checked_at,
        "snapshots": snapshots,
        "last_run": {
            "first_baseline": first_baseline,
            "reference_date_status": reference_status,
            "reference_date": snapshot["reference_date"],
            "signals": signals[:5],
            "coverage": "OFFICIAL_ROLLING_AGGREGATES_ONLY",
            "article_gate": "NOT_EVALUATED",
        },
    }

def render(state):
    run = state["last_run"]
    latest = state["snapshots"][-1]
    lines = [
        "# 응답소 민원통계 변화 관측 — 시험", "",
        f"확인 시각: {state['last_checked_kst']}",
        f"공식 기준일: {latest['reference_date']} / 집계기간: "
        f"{latest['period_start']}~{latest['period_end']}",
        f"30일 접수 합계: {latest['rolling_total']:,}건", "",
        "민원 건수는 사람 수·피해자 수가 아니며, 자치구 표는 민원인 거주지가 아니라 처리기관 기준입니다.",
        "접수경로·분야·처리기관·자치구 표는 서로 독립된 1차원 집계로 교차 결합하지 않습니다.",
        "이 문서는 취재 질문 원석이며 확정 기사 아이템이 아닙니다.", "",
    ]
    if run["reference_date_status"] == "FIRST_BASELINE":
        lines += ["첫 기준 관측입니다. 이전 값이 없어 변화 질문을 만들지 않습니다.", ""]
    elif run["reference_date_status"] == "UNCHANGED":
        lines += ["공식 기준일이 이전 관측과 같습니다. 새 통계로 중복 계상하지 않습니다.", ""]
    lines += [f"저장된 기준과 비교해 생긴 질문: {len(run['signals'])}건", ""]
    for item in run["signals"]:
        lines += [f"## {item['kind']}", item["observation"],
                  "확인할 질문: " + item["verification_question"],
                  "판정: 검증 전 / 기사 게이트 미평가", ""]
    if not run["signals"]:
        lines += ["이번 관측에서 설정한 변화 기준을 넘은 질문은 0건입니다. "
                  "민원이나 불편이 없다는 뜻은 아닙니다.", ""]
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=OUT)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    state_path = args.output_dir / "state_latest.json"
    prior = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else empty_state()
    try:
        snapshot = parse_snapshot(fetch_html())
        state = compare(prior, snapshot, now_kst())
    except Exception as exc:
        (args.output_dir / "access_failure_latest.json").write_text(
            json.dumps({"status": "FAILED_NO_STATE_WRITE",
                        "error": sanitize(str(exc))[:600]}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print("WATCH_FAILED " + sanitize(str(exc))[:600])
        return 1
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / "questions_latest.md").write_text(render(state), encoding="utf-8")
    print("WATCH " + json.dumps(state["last_run"], ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
