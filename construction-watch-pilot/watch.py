#!/usr/bin/env python3
"""Read-only construction change watch with bounded rolling state.

The output is a pre-editorial question queue, never an article candidate.
Only official list first pages are observed. Progress has no confirmed pjt_cd,
so its title key is used ONLY for within-progress temporal comparison.
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "off-session-pilot"))
from contract_route_probe import Scripts, read_text, route_evidence
from construction_change_probe import CHANGE_LISTS, inspect_list, inspect_progress
from probe_sources import norm, sanitize

BASE = Path(__file__).resolve().parent
OUT = BASE / "output"
SCHEMA = 1
MAX_RECORDS = 500
CATEGORY = ("EXTENSION", "DESIGN", "PENALTY")
PERCENT = re.compile(r"(계\s*획|실\s*적)\s*:\s*([\d.]+)\s*%")
DATE = re.compile(r"20\d{2}-\d{2}-\d{2}")

def now_kst():
    return datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")

def id_key(category, project_id, record_key):
    if not re.fullmatch(r"[A-Za-z0-9]{8,30}", project_id or ""):
        raise ValueError("unverified project code")
    if not re.fullmatch(r"[A-Za-z0-9|]{1,80}", record_key or ""):
        raise ValueError("unverified change record key")
    return f"{category}|{project_id}|{record_key}"

def parse_extension(context):
    days = re.search(r"연장일수\s*:\s*(\d{1,4})\s*일", context)
    before = re.search(r"변경전\s*준공예정\s*:\s*(20\d{2}-\d{2}-\d{2})", context)
    after = re.search(r"변경후\s*준공예정일\s*:\s*(20\d{2}-\d{2}-\d{2})", context)
    return {
        "extension_days": int(days.group(1)) if days else None,
        "before_completion": before.group(1) if before else None,
        "after_completion": after.group(1) if after else None,
    }

def change_record(category, item):
    link = item["link"]
    args = link.get("quoted_args", [])
    project_id = link.get("first_arg_project_candidate")
    if not args or args[0] != project_id:
        raise ValueError("popup first argument is not project code")
    record_key = args[-1]
    key = id_key(category, project_id, record_key)
    row = item.get("row_excerpt", "")
    record = {
        "key": key,
        "category": category,
        "pjt_cd": project_id,
        "record_key": record_key,
        "title": sanitize(item["title"])[:180],
        "registration_date": item.get("registration_date"),
        "source_url": CHANGE_LISTS[category],
    }
    if category == "EXTENSION":
        record.update(parse_extension(row))
    elif category == "DESIGN":
        record["change_reason_status"] = "LIST_VALUE_NOT_VERIFIED"
    elif category == "PENALTY":
        record["penalty_context"] = sanitize(row)[:300]
    return record

def progress_record(card):
    title = re.search(r"^■\s*(.*?)\s+사업기간", card)
    if not title:
        raise ValueError("progress card title missing")
    values = {re.sub(r"\s+", "", label): float(number)
              for label, number in PERCENT.findall(card)}
    if "계획" not in values or "실적" not in values:
        raise ValueError("progress plan/actual values missing")
    name = norm(title.group(1))
    key = hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
    return {
        "key": key,
        "title": sanitize(name)[:180],
        "identity_scope": "WITHIN_PROGRESS_TITLE_ONLY",
        "plan_percent": values["계획"],
        "actual_percent": values["실적"],
        "gap_pp": round(values["실적"] - values["계획"], 2),
        "source_url": CHANGE_LISTS["PROGRESS"],
        "pjt_cd": None,
    }

def collect(fetch=read_text):
    pages = {}
    errors = {}
    for category, url in CHANGE_LISTS.items():
        try:
            pages[category] = fetch(url)
        except Exception as exc:
            errors[category] = sanitize(str(exc))[:160]
    if errors:
        raise RuntimeError("SOURCE_ACCESS_FAILED " + json.dumps(errors, ensure_ascii=False))
    events = {}
    counts = {}
    for category in CATEGORY:
        html = pages[category]
        route = route_evidence(Scripts(html).inline)
        if (route.get("function_status") != "FOUND" or
                'pjt_cd="+pjt_cd' not in route.get("popup_expression", "")):
            raise ValueError(f"{category} popup project route not confirmed")
        report = inspect_list(html, category)
        if not report["items"] or report["visible_characters"] < 200:
            raise ValueError(f"{category} row parse degraded")
        counts[category] = len(report["items"])
        for item in report["items"]:
            record = change_record(category, item)
            if record["registration_date"] is None:
                raise ValueError(f"{category} row date missing")
            events[record["key"]] = record
    progress = {}
    report = inspect_progress(pages["PROGRESS"])
    if not report["first_five_card_excerpts"]:
        raise ValueError("PROGRESS card parse degraded")
    for card in report["first_five_card_excerpts"]:
        record = progress_record(card)
        progress[record["key"]] = record
    counts["PROGRESS"] = len(progress)
    return {"events": events, "progress": progress, "sample_counts": counts}

def empty_state():
    return {"schema": SCHEMA, "last_collected_kst": None,
            "events": {}, "progress": {}, "last_run": {}}

def validate_state(state):
    if state.get("schema") != SCHEMA:
        raise ValueError("unknown state schema")
    if not isinstance(state.get("events"), dict) or not isinstance(state.get("progress"), dict):
        raise ValueError("invalid state collections")
    return state

def question_signal(kind, project_id, title, detail, source_urls):
    return {
        "kind": kind,
        "pjt_cd": project_id,
        "title": title,
        "observation": detail,
        "question_status": "PRE_EDITORIAL_VERIFY",
        "article_gate": "NOT_EVALUATED",
        "signal_basis": "NEW_RECORD_COMPARED_WITH_SAVED_STATE",
        "source_urls": list(dict.fromkeys(source_urls)),
    }

def verification_question(signal):
    questions = {
        "REPEAT_EXTENSION": (
            "서로 다른 공기연장인가 동일 변경의 재게시인가? 각 공식 사유와 "
            "최종 준공일을 확인하고, 주민 이용 중단 기간이나 사업비에 실제 변화가 있었나?"
        ),
        "REPEAT_DESIGN": (
            "각 설계변경의 사유·증감액·일정 영향은 무엇인가? 최초 계획에서 빠진 조건인지, "
            "이용자에게 확인 가능한 불편이나 추가 부담이 생겼는지 확인할 수 있나?"
        ),
        "PENALTY_WITH_CHANGE": (
            "벌점 대상 행위와 설계·공기 변경의 날짜가 실제로 이어지는가? 시정조치가 끝났는지, "
            "품질·안전·준공 시점·사업비에 확인 가능한 영향이 있었는가?"
        ),
        "MULTIPLE_PENALTIES": (
            "각 벌점은 어느 업체의 어떤 별개 위반인가? 시정조치가 끝났는지, "
            "품질·안전·공기·사업비에 확인 가능한 영향이 발생했는가?"
        ),
        "PROGRESS_GAP_WIDENED": (
            "계획 기준이 바뀐 것인가 실제 공정이 늦어진 것인가? 원인과 회복 계획을 확인하고, "
            "완공·개통 또는 시민 이용 시점에 영향이 생겼는가?"
        ),
    }
    return questions.get(
        signal["kind"],
        "원자료의 값이 실제 변화인지 먼저 확인하고 시민에게 관찰 가능한 영향이 있는지 검증한다.",
    )

def compare(prior, observed, collected_at):
    prior = validate_state(prior)
    first_baseline = prior["last_collected_kst"] is None
    old_events = prior["events"]
    events = dict(old_events)
    new = []
    signals = []
    for key, record in observed["events"].items():
        if key in events:
            # Refresh current derived fields so parser corrections and official
            # row edits do not leave stale context in the rolling state. A row
            # with the same stable key is not promoted as a new event.
            first_seen = events[key].get("first_seen_kst", collected_at)
            events[key] = dict(record, first_seen_kst=first_seen,
                               last_seen_kst=collected_at)
            continue
        record = dict(record, first_seen_kst=collected_at,
                      last_seen_kst=collected_at)
        siblings = [x for x in events.values() if x["pjt_cd"] == record["pjt_cd"]]
        if record["category"] == "EXTENSION":
            same = [x for x in siblings if x["category"] == "EXTENSION"]
            if same:
                signals.append(question_signal(
                    "REPEAT_EXTENSION", record["pjt_cd"], record["title"],
                    f"같은 사업 코드에서 공기연장 기록이 {len(same) + 1}건 관측됨. "
                    "연장일수는 합산하지 않음.",
                    [x["source_url"] for x in same] + [record["source_url"]]))
        elif record["category"] == "DESIGN":
            same = [x for x in siblings if x["category"] == "DESIGN"]
            if same:
                signals.append(question_signal(
                    "REPEAT_DESIGN", record["pjt_cd"], record["title"],
                    f"같은 사업 코드에서 설계변경 기록이 {len(same) + 1}건 관측됨. "
                    "변경 사유와 비용 영향은 아직 미확인.",
                    [record["source_url"]]))
        elif record["category"] == "PENALTY":
            changes = [x for x in siblings if x["category"] in ("EXTENSION", "DESIGN")]
            if changes:
                signals.append(question_signal(
                    "PENALTY_WITH_CHANGE", record["pjt_cd"], record["title"],
                    "같은 사업 코드에 벌점과 변경 기록이 함께 있음. "
                    "인과관계와 시민 영향은 미확인.",
                    [x["source_url"] for x in changes] + [record["source_url"]]))
        events[key] = record
        new.append(key)
    new_penalty_projects = {
        observed["events"][key]["pjt_cd"] for key in new
        if observed["events"][key]["category"] == "PENALTY"
    }
    for project_id in sorted(new_penalty_projects):
        penalties = [x for x in events.values()
                     if x["pjt_cd"] == project_id and x["category"] == "PENALTY"]
        if len(penalties) >= 2:
            signals.append(question_signal(
                "MULTIPLE_PENALTIES", project_id, penalties[0]["title"],
                f"같은 사업 코드의 서로 다른 벌점 기록이 {len(penalties)}건 관측됨. "
                "업체·점검·부과일을 구분하고 동일 사실의 중복 게시인지 확인.",
                [x["source_url"] for x in penalties]))
    if len(events) > MAX_RECORDS:
        # Keep the most recently observed derived records, not raw pages.
        newest = sorted(events.values(), key=lambda x: x["last_seen_kst"],
                        reverse=True)[:MAX_RECORDS]
        events = {x["key"]: x for x in newest}
    old_progress = prior["progress"]
    progress = {}
    for key, record in observed["progress"].items():
        prior_record = old_progress.get(key)
        record = dict(record, observed_at_kst=collected_at)
        if prior_record:
            delta = round(record["gap_pp"] - prior_record["gap_pp"], 2)
            if delta <= -1.0:
                signals.append(question_signal(
                    "PROGRESS_GAP_WIDENED", None, record["title"],
                    f"같은 공정 카드의 계획 대비 실적 격차가 "
                    f"{prior_record['gap_pp']:+.2f}→{record['gap_pp']:+.2f}%p. "
                    "계획 변경·집계 수정 여부를 먼저 확인.",
                    [record["source_url"]]))
        progress[key] = record
    # A first snapshot establishes inventory only. It cannot support a claim
    # that a record is new or that a condition changed since the prior run.
    if first_baseline:
        signals = []
    state = {
        "schema": SCHEMA,
        "last_collected_kst": collected_at,
        "events": events,
        "progress": progress,
        "last_run": {
            "first_baseline": first_baseline,
            "new_record_keys": new,
            "signals": signals,
            "sample_counts": observed["sample_counts"],
            "coverage": "FIRST_PAGE_ONLY",
            "article_gate": "NOT_EVALUATED",
        },
    }
    return state

def render(state):
    run = state["last_run"]
    lines = ["# 건설알림이 변화 관측 — 시험", "",
             f"관측 시각: {state['last_collected_kst']}",
             "범위: 네 화면의 첫 페이지·상위 소량 항목. 전체 공사 전수 분석이 아닙니다.",
             "동일 사업 코드는 공기연장·설계변경·벌점 안에서만 연결합니다. "
             "공정률은 사업 코드가 미확인되어 제목 기준의 동일 화면 전후 비교만 합니다.",
             "이 문서는 취재 질문 원석이며 확정 기사 아이템이 아닙니다.", ""]
    if run["first_baseline"]:
        lines += ["첫 기준 관측입니다. 이전 값이 없어 변화 여부는 아직 판단하지 않습니다.", ""]
    lines += [f"이번 관측에서 처음 본 기록: {len(run['new_record_keys'])}건",
              f"저장된 기준과 비교해 생긴 질문: {len(run['signals'])}건", ""]
    for signal in run["signals"]:
        lines += [f"## {signal['title']}", signal["observation"],
                  f"확인할 질문: {verification_question(signal)}",
                  "판정: 검증 전 / 기사 게이트 미평가", ""]
    if not run["signals"]:
        lines += ["이번 제한된 관측 범위에서 반복·결합·격차 확대 질문은 0건입니다. "
                  "원자료 전체에 현상이 없다는 뜻은 아닙니다.", ""]
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=OUT)
    args = parser.parse_args()
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    state_path = output / "state_latest.json"
    prior = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else empty_state()
    try:
        observed = collect()
        state = compare(prior, observed, now_kst())
    except Exception as exc:
        (output / "access_failure_latest.json").write_text(
            json.dumps({"status": "FAILED_NO_STATE_WRITE",
                        "error": sanitize(str(exc))[:600]}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print("WATCH_FAILED " + sanitize(str(exc))[:600])
        return 1
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "questions_latest.md").write_text(render(state), encoding="utf-8")
    print("WATCH " + json.dumps(state["last_run"], ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
