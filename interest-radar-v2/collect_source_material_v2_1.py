"""유튜브 시민 언어를 LEAD와 반복 확인 군집으로 나눠 수집한다.

검색 API 비용을 통제하면서 하루 세 회차가 생활 의제를 순환한다. 댓글은
사실 근거가 아니라 반복 경험의 언어와 후속 검색어를 찾는 용도로만 쓴다.
파일명은 예약 작업 호환성을 위해 v2_1을 유지하지만 출력 규칙은 v2.3이다.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import urllib.error
import urllib.parse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config" / "editorial_lenses.json"
OUTPUT = ROOT / "output"
STATE_FILE = OUTPUT / "youtube_quota_state.json"
SIGNAL_LEDGER = OUTPUT / "youtube_signal_ledger_v2_1.json"
QUERY_HEALTH = OUTPUT / "youtube_query_health_v2_3.json"
API_USAGE = OUTPUT / "youtube_api_usage_v2_3.json"


def load_base():
    spec = importlib.util.spec_from_file_location("source_v1", ROOT / "collect_source_material_v1.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def iso_duration_seconds(value: str) -> int:
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value or "")
    if not match:
        return 0
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def text_matches(text: str, terms: list[str]) -> list[str]:
    lowered = text.lower()
    return [term for term in terms if term.lower() in lowered]


def classify_source(channel: str, title: str, description: str, settings: dict) -> str:
    visible = f"{channel} {title}"
    full_text = f"{visible} {description}"
    if text_matches(visible, settings.get("fiction_markers", [])):
        return "사연·재연"
    if text_matches(full_text, settings["advice_markers"]):
        return "생활정보·설명"
    if text_matches(visible, settings["media_channel_markers"]):
        return "언론·방송"
    if any(term in visible for term in ("노무사", "변호사", "상담", "센터", "협회", "지원단체")):
        return "상담·지원"
    if any(term in channel for term in ("사장", "중개", "요양", "라이더", "대리기사", "상인", "현장")):
        return "현장·운영자"
    if any(term in title for term in ("사장 브이로그", "자영업자 일상", "배달기사 일상", "라이더 일상", "현장 인터뷰")):
        return "현장·운영자"
    return "분류 대기"


def promote_direct_experience(
    source_archetype: str, channel: str, title: str, description: str, settings: dict,
    query_labels: list[dict] | None = None,
) -> str:
    if source_archetype != "분류 대기":
        return source_archetype
    visible = f"{channel} {title}"
    first_person_visible = text_matches(visible, settings["first_person_markers"])
    experience_cues = ("브이로그", "일상", "후기", "직접", "겪은", "경험담")
    first_person_full = text_matches(f"{visible} {description}", settings["first_person_markers"])
    source_lane = any(label.get("lane") == "SOURCE" for label in (query_labels or []))
    if first_person_visible or (first_person_full and any(cue in visible for cue in experience_cues)):
        return "당사자 가능성"
    if source_lane and any(cue in visible for cue in experience_cues):
        return "당사자 가능성"
    return source_archetype


def normalize_record(record: dict, config: dict) -> dict | None:
    """현재 앵커·분류 규칙으로 누적 장부의 과거 행도 다시 판정한다."""
    settings = config["youtube_discovery"]
    haystack = f"{record.get('title', '')} {record.get('description', '')}"
    anchors = {
        (row["agenda"], row["cluster"]): row.get("anchor_terms", [])
        for row in config["youtube_cluster_queries"]
    }
    labels = [
        label for label in record.get("query_labels", [])
        if text_matches(haystack, anchors.get((label.get("agenda"), label.get("cluster")), []))
    ]
    if not labels:
        return None
    signal_markers = text_matches(haystack, settings["signal_markers"])
    first_person = text_matches(haystack, settings["first_person_markers"])
    verification_markers = text_matches(haystack, settings["verification_markers"])
    seoul_place_terms = text_matches(haystack, config.get("youtube_seoul_place_terms", []))
    source_archetype = classify_source(
        record.get("channel", ""), record.get("title", ""), record.get("description", ""), settings
    )
    source_archetype = promote_direct_experience(
        source_archetype, record.get("channel", ""), record.get("title", ""), record.get("description", ""), settings, labels
    )
    record.update({
        "query_labels": labels,
        "source_archetype": source_archetype,
        "signal_markers": signal_markers,
        "first_person_markers": first_person,
        "verification_markers": verification_markers,
        "seoul_place_terms": seoul_place_terms,
        "advice_markers": text_matches(haystack, settings["advice_markers"]),
    })
    return record


def load_api_usage() -> dict:
    try:
        usage = json.loads(API_USAGE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        usage = {}
    if not isinstance(usage, dict):
        usage = {}
    usage.setdefault("version", "2.3")
    usage.setdefault("quota_timezone", "America/Los_Angeles")
    usage.setdefault("days", {})
    return usage


def save_api_usage(usage: dict) -> None:
    days = usage.setdefault("days", {})
    for old_day in sorted(days)[:-35]:
        days.pop(old_day, None)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    API_USAGE.write_text(json.dumps(usage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def quota_day_key(now, settings: dict) -> str:
    # Windows 예약 실행 환경에는 IANA tzdata가 없을 수 있다. 미국 서부의
    # 2007년 이후 DST 규칙(3월 둘째 일요일~11월 첫째 일요일)을 직접 적용한다.
    utc_now = now.astimezone(timezone.utc)
    year = utc_now.year

    def sunday_on_or_after(month: int, day: int) -> int:
        candidate = datetime(year, month, day, tzinfo=timezone.utc)
        return day + (6 - candidate.weekday()) % 7

    dst_start = datetime(
        year, 3, sunday_on_or_after(3, 8), 10, tzinfo=timezone.utc
    )
    dst_end = datetime(
        year, 11, sunday_on_or_after(11, 1), 9, tzinfo=timezone.utc
    )
    offset_hours = -7 if dst_start <= utc_now < dst_end else -8
    pacific = timezone(timedelta(hours=offset_hours))
    return utc_now.astimezone(pacific).date().isoformat()


def youtube_endpoint(url: str) -> str:
    path = urllib.parse.urlparse(url).path.rstrip("/").split("/")[-1]
    return {
        "search": "search.list", "videos": "videos.list", "comments": "comments.list",
        "commentThreads": "commentThreads.list", "channels": "channels.list",
        "playlistItems": "playlistItems.list",
    }.get(path, path or "unknown")


def api_error_detail(body: str) -> tuple[str, str]:
    try:
        payload = json.loads(body)
        error = payload.get("error", {})
        reasons = error.get("errors", [])
        reason = reasons[0].get("reason", "") if reasons else error.get("status", "")
        return reason, error.get("message", "")
    except (json.JSONDecodeError, AttributeError, IndexError):
        return "", re.sub(r"\s+", " ", body).strip()[:500]


def usage_summary(usage: dict, now, settings: dict, run_mode: str) -> dict:
    quota_day = quota_day_key(now, settings)
    events = usage.get("days", {}).get(quota_day, {}).get("events", [])
    search_events = [row for row in events if row.get("endpoint") == "search.list"]
    regular = sum(row.get("mode") == "regular" for row in search_events)
    exploration = sum(row.get("mode") in {"manual", "audit"} for row in search_events)
    total = len(search_events)
    regular_limit = int(settings.get("regular_search_daily_budget", 40))
    exploration_limit = int(settings.get("exploration_search_daily_budget", 20))
    managed_limit = int(settings.get("managed_search_daily_cap", 60))
    return {
        "quota_day": quota_day,
        "quota_timezone": settings.get("quota_timezone", "America/Los_Angeles"),
        "mode": run_mode,
        "search_attempts": total,
        "regular_search_attempts": regular,
        "exploration_search_attempts": exploration,
        "regular_remaining": max(0, regular_limit - regular),
        "exploration_remaining": max(0, exploration_limit - exploration),
        "managed_remaining": max(0, managed_limit - total),
        "provider_daily_limit": int(settings.get("search_provider_daily_limit", 100)),
        "reserved_calls": int(settings.get("search_reserved_calls", 40)),
    }


def guarded_get_json(base, now, config: dict, run_mode: str):
    settings = config["youtube_discovery"]
    usage = load_api_usage()
    quota_day = quota_day_key(now, settings)
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}
    if (
        state.get("blocked_quota_day") == quota_day
        or state.get("blocked_on") == quota_day
    ) and state.get("reason") == "daily quotaExceeded":
        raise RuntimeError("YouTube 할당량 제한이 오늘 이미 확인됨")
    cooldown_until = state.get("cooldown_until")
    if cooldown_until:
        try:
            if now < base_datetime(cooldown_until):
                raise RuntimeError(f"YouTube 일시 요청 제한 대기 중: {cooldown_until}")
        except ValueError:
            pass

    def request(url: str, query_row: dict | None = None):
        endpoint = youtube_endpoint(url)
        summary = usage_summary(usage, now, settings, run_mode)
        if endpoint == "search.list":
            if summary["managed_remaining"] <= 0:
                raise RuntimeError("YouTube 관리 검색 예산 60회가 소진되어 40회를 예비분으로 보존함")
            if run_mode == "regular" and summary["regular_remaining"] <= 0:
                raise RuntimeError("YouTube 정규 검색 예산 40회가 소진됨")
            if run_mode in {"manual", "audit"} and summary["exploration_remaining"] <= 0:
                raise RuntimeError("YouTube 수동·감사 검색 예산 20회가 소진됨")

        day = usage.setdefault("days", {}).setdefault(quota_day, {"events": []})
        event = {
            "at": base.datetime.now(base.KST).isoformat(),
            "mode": run_mode,
            "endpoint": endpoint,
            "status": "ATTEMPTED",
        }
        if query_row:
            event.update({
                "query_key": query_identity(query_row),
                "query": query_row.get("query", ""),
                "selection_tier": query_row.get("selection_tier", ""),
                "run_slot": query_row.get("run_slot"),
            })
        day["events"].append(event)
        save_api_usage(usage)
        try:
            payload = base.get_json(url)
            event["status"] = "OK"
            save_api_usage(usage)
            return payload
        except urllib.error.HTTPError as exc:
            if "googleapis.com/youtube/" not in url:
                raise
            body = exc.read().decode("utf-8", errors="ignore")
            reason, message = api_error_detail(body)
            retry_after = exc.headers.get("Retry-After", "")
            event.update({
                "status": f"HTTP_{exc.code}", "http_status": exc.code,
                "api_reason": reason, "message": message,
                "retry_after": retry_after,
            })
            save_api_usage(usage)
            if exc.code == 429:
                wait_seconds = int(retry_after) if retry_after.isdigit() else 15 * 60
                cooldown = base.datetime.now(base.KST) + timedelta(seconds=max(60, wait_seconds))
                STATE_FILE.write_text(json.dumps({
                    "reason": "temporary HTTP 429",
                    "http_status": 429,
                    "api_reason": reason or "unknown",
                    "message": message,
                    "retry_after_header": retry_after,
                    "cooldown_until": cooldown.isoformat(),
                    "quota_day": quota_day,
                }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                detail = f", reason={reason}" if reason else ""
                raise RuntimeError(
                    f"YouTube 일시 요청 제한(HTTP 429{detail}), {cooldown.isoformat()}까지 대기"
                ) from exc
            if exc.code == 403 and (reason == "quotaExceeded" or "quotaExceeded" in body):
                STATE_FILE.write_text(json.dumps({
                    "blocked_quota_day": quota_day,
                    "reason": "daily quotaExceeded",
                    "http_status": 403,
                    "api_reason": reason or "quotaExceeded",
                    "message": message,
                    "retry_after": "다음 태평양 시간 일일 할당량 주기",
                }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                raise RuntimeError("YouTube 일일 할당량 제한(quotaExceeded)") from exc
            raise
        except Exception as exc:
            event.update({"status": "ERROR", "message": str(exc)[:500]})
            save_api_usage(usage)
            raise

    request.usage_state = usage
    request.usage_summary = lambda: usage_summary(usage, now, settings, run_mode)
    return request


def query_identity(row: dict) -> str:
    return "|".join((row.get("agenda", ""), row.get("cluster", ""), row.get("lane", ""), row.get("query", "")))


def load_query_health() -> list[dict]:
    try:
        rows = json.loads(QUERY_HEALTH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    return rows if isinstance(rows, list) else []


def run_slot(now) -> int:
    return 0 if now.hour < 10 else 1 if now.hour < 15 else 2


def query_expressions(config: dict, paused_keys: set[str] | None = None) -> list[dict]:
    rows = [
        {
            "agenda": cluster_row["agenda"],
            "cluster": cluster_row["cluster"],
            "anchor_terms": cluster_row["anchor_terms"],
            "lane": lane_row["lane"],
            "query": lane_row["query"],
        }
        for cluster_row in config["youtube_cluster_queries"]
        for lane_row in cluster_row["search_lanes"]
    ]
    if paused_keys is not None:
        rows = [row for row in rows if query_identity(row) not in paused_keys]
    return rows


def balanced_overdue(
    rows: list[dict], count: int, agendas: list[str], health_index: dict,
    seed: int,
) -> list[dict]:
    queues: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        queues[row["agenda"]].append(row)
    for agenda_rows in queues.values():
        agenda_rows.sort(key=lambda row: (
            health_index.get(query_identity(row), {}).get("last_run", ""),
            query_identity(row),
        ))
    agenda_order = agendas[seed % len(agendas):] + agendas[:seed % len(agendas)]
    output = []
    while len(output) < count:
        progressed = False
        for agenda in agenda_order:
            if queues.get(agenda):
                output.append(queues[agenda].pop(0))
                progressed = True
                if len(output) >= count:
                    break
        if not progressed:
            break
    return output


def selected_queries(
    config: dict, now, run_mode: str = "regular",
    paused_keys: set[str] | None = None, query_health: list[dict] | None = None,
    request=None,
) -> list[dict]:
    settings = config["youtube_discovery"]
    agendas = [entry["code"] for entry in config["agenda_domains"]]
    slot = run_slot(now)
    all_rows = query_expressions(config, paused_keys)
    health_index = {query_identity(row): row for row in (query_health or [])}
    usage = getattr(request, "usage_state", load_api_usage())
    summary = request.usage_summary() if request else usage_summary(usage, now, settings, run_mode)
    quota_day = summary["quota_day"]
    events = usage.get("days", {}).get(quota_day, {}).get("events", [])
    executed_keys = {
        row.get("query_key") for row in events
        if row.get("endpoint") == "search.list" and row.get("status") == "OK"
    }
    available = [row for row in all_rows if query_identity(row) not in executed_keys]

    if run_mode == "regular":
        slot_calls = settings.get("regular_slot_search_calls", [14, 13, 13])
        sentinel_calls = settings.get("sentinel_queries_per_slot", [4, 3, 3])
        slot_used = sum(
            row.get("endpoint") == "search.list"
            and row.get("mode") == "regular"
            and row.get("run_slot") == slot
            for row in events
        )
        target = min(
            max(0, int(slot_calls[slot]) - slot_used),
            summary["regular_remaining"],
            summary["managed_remaining"],
        )
        if target <= 0:
            return []

        core_agendas = {entry["code"] for entry in config["agenda_domains"] if entry.get("core_daily")}
        core_clusters = []
        for cluster_row in config["youtube_cluster_queries"]:
            key = (cluster_row["agenda"], cluster_row["cluster"])
            if cluster_row["agenda"] in core_agendas and key not in core_clusters:
                core_clusters.append(key)
        sentinel_start = sum(int(value) for value in sentinel_calls[:slot])
        sentinel_cluster_keys = core_clusters[
            sentinel_start:sentinel_start + int(sentinel_calls[slot])
        ]
        output = []
        for agenda, cluster in sentinel_cluster_keys:
            candidates = [
                row for row in available
                if row["agenda"] == agenda and row["cluster"] == cluster
            ]
            candidates.sort(key=lambda row: (
                health_index.get(query_identity(row), {}).get("last_run", ""),
                query_identity(row),
            ))
            if candidates:
                chosen = candidates[0]
                output.append({**chosen, "selection_tier": "SENTINEL"})

        chosen_keys = {query_identity(row) for row in output}
        rotation_pool = [
            row for row in available if query_identity(row) not in chosen_keys
        ]
        rotation = balanced_overdue(
            rotation_pool, target - len(output), agendas, health_index,
            now.toordinal() * 3 + slot,
        )
        output.extend({**row, "selection_tier": "ROTATION"} for row in rotation)
    elif run_mode == "audit":
        target = min(
            len(agendas) * int(settings.get("expressions_per_agenda_per_run", 2)),
            summary["exploration_remaining"],
            summary["managed_remaining"],
        )
        output = []
        per_agenda = int(settings.get("expressions_per_agenda_per_run", 2))
        for agenda_index, agenda in enumerate(agendas):
            candidates = [row for row in available if row["agenda"] == agenda]
            candidates.sort(key=lambda row: (
                health_index.get(query_identity(row), {}).get("last_run", ""),
                query_identity(row),
            ))
            start = (now.toordinal() + agenda_index) % max(len(candidates), 1)
            ordered = candidates[start:] + candidates[:start]
            output.extend(
                {**row, "selection_tier": "AUDIT"}
                for row in ordered[:per_agenda]
            )
        output = output[:target]
    else:
        target = min(
            int(settings.get("manual_queries_per_run", 8)),
            summary["exploration_remaining"],
            summary["managed_remaining"],
        )
        output = [
            {**row, "selection_tier": "MANUAL"}
            for row in balanced_overdue(
                available, target, agendas, health_index, now.toordinal() + slot,
            )
        ]

    for index, row in enumerate(output):
        row["run_slot"] = slot
        row["search_order"] = (
            "date" if row["selection_tier"] == "SENTINEL" or index % 2 == 0
            else "relevance"
        )
    return output


def collect_search_records(
    base, request, key: str, config: dict, now, run_mode: str = "regular",
    paused_keys: set[str] | None = None, query_health: list[dict] | None = None,
):
    settings = config["youtube_discovery"]
    after = (now - timedelta(days=settings["lookback_days"])).astimezone(base.timezone.utc).isoformat().replace("+00:00", "Z")
    selected = selected_queries(config, now, run_mode, paused_keys, query_health, request)
    per_query = {
        query_identity(row): {
            "agenda": row["agenda"], "cluster": row["cluster"], "lane": row["lane"],
            "query": row["query"], "search_order": row["search_order"],
            "api_hits": 0, "anchor_match": 0, "anchor_mismatch": 0,
            "hard_excluded": 0, "qualified": 0, "scene": 0, "seoul": 0,
            "pending": 0, "advice": 0, "media": 0, "fiction": 0,
        }
        for row in selected
    }
    metrics = {
        "query_count": len(selected),
        "queries": [
            {key: row[key] for key in (
                "agenda", "cluster", "lane", "query", "search_order",
                "selection_tier", "run_slot",
            )}
            for row in selected
        ],
        "search_hits": 0,
        "unique_video_ids": 0,
        "detail_records": 0,
        "hard_excluded": 0,
        "query_mismatch": 0,
        "accepted_records": 0,
        "per_query": [],
    }
    labels: dict[str, list[dict]] = defaultdict(list)
    for query_row in selected:
        query = urllib.parse.urlencode({
            "part": "snippet", "type": "video", "order": query_row["search_order"],
            "regionCode": "KR", "relevanceLanguage": "ko",
            "publishedAfter": after, "maxResults": settings["results_per_query"],
            "q": query_row["query"], "key": key,
        })
        items = request(
            "https://www.googleapis.com/youtube/v3/search?" + query, query_row
        ).get("items", [])
        metrics["search_hits"] += len(items)
        per_query[query_identity(query_row)]["api_hits"] += len(items)
        for item in items:
            video_id = item.get("id", {}).get("videoId")
            if video_id:
                labels[video_id].append(query_row)

    records = []
    ids = list(labels)
    metrics["unique_video_ids"] = len(ids)
    for start in range(0, len(ids), 50):
        detail_query = urllib.parse.urlencode({
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(ids[start:start + 50]), "key": key,
        })
        for item in request("https://www.googleapis.com/youtube/v3/videos?" + detail_query).get("items", []):
            metrics["detail_records"] += 1
            snippet = item.get("snippet", {})
            title = snippet.get("title", "")
            channel = snippet.get("channelTitle", "")
            description = snippet.get("description", "")
            haystack = f"{title} {description}"
            if channel.endswith(" - Topic") or text_matches(f"{title} {channel}", settings["hard_exclusions"]):
                metrics["hard_excluded"] += 1
                for label in labels[item.get("id")]:
                    per_query[query_identity(label)]["hard_excluded"] += 1
                continue
            matched_labels = []
            for label in labels[item.get("id")]:
                query_metric = per_query[query_identity(label)]
                if text_matches(haystack, label.get("anchor_terms", [])):
                    matched_labels.append(label)
                    query_metric["anchor_match"] += 1
                else:
                    query_metric["anchor_mismatch"] += 1
            if not matched_labels:
                metrics["query_mismatch"] += 1
                continue
            base_record = base.video_record(item, set(), now)
            duration = iso_duration_seconds(item.get("contentDetails", {}).get("duration", ""))
            signal_markers = text_matches(haystack, settings["signal_markers"])
            first_person = text_matches(haystack, settings["first_person_markers"])
            verification_markers = text_matches(haystack, settings["verification_markers"])
            seoul_place_terms = text_matches(haystack, config.get("youtube_seoul_place_terms", []))
            source_archetype = classify_source(channel, title, description, settings)
            source_archetype = promote_direct_experience(source_archetype, channel, title, description, settings, matched_labels)
            qualified_type = source_archetype in {"당사자 가능성", "상담·지원", "현장·운영자"}
            for label in matched_labels:
                query_metric = per_query[query_identity(label)]
                if qualified_type:
                    query_metric["qualified"] += 1
                    if signal_markers:
                        query_metric["scene"] += 1
                if seoul_place_terms:
                    query_metric["seoul"] += 1
                type_key = {
                    "분류 대기": "pending", "생활정보·설명": "advice",
                    "언론·방송": "media", "사연·재연": "fiction",
                }.get(source_archetype)
                if type_key:
                    query_metric[type_key] += 1
            base_record.update({
                "duration_seconds": duration,
                "source_archetype": source_archetype,
                "seoul_place_terms": seoul_place_terms,
                "signal_markers": signal_markers,
                "first_person_markers": first_person,
                "verification_markers": verification_markers,
                "advice_markers": text_matches(haystack, settings["advice_markers"]),
                "is_short": 0 < duration <= settings["short_video_seconds"],
                "query_labels": matched_labels,
            })
            records.append(base_record)
    metrics["accepted_records"] = len(records)
    metrics["per_query"] = list(per_query.values())
    return records, metrics


def update_query_health(metrics: dict, config: dict, now) -> list[dict]:
    settings = config["youtube_discovery"]
    stored = {query_identity(row): row for row in load_query_health()}
    for current in metrics.get("per_query", []):
        identity = query_identity(current)
        previous = stored.get(identity, {})
        row = {
            "agenda": current["agenda"], "cluster": current["cluster"], "lane": current["lane"],
            "query": current["query"], "runs": int(previous.get("runs", 0)) + 1,
            "api_hits": int(previous.get("api_hits", 0)) + current["api_hits"],
            "anchor_match": int(previous.get("anchor_match", 0)) + current["anchor_match"],
            "anchor_mismatch": int(previous.get("anchor_mismatch", 0)) + current["anchor_mismatch"],
            "qualified": int(previous.get("qualified", 0)) + current["qualified"],
            "scene": int(previous.get("scene", 0)) + current["scene"],
            "seoul": int(previous.get("seoul", 0)) + current["seoul"],
            "noise": int(previous.get("noise", 0)) + current["advice"] + current["media"] + current["fiction"],
            "last_run": now.isoformat(), "status": "ACTIVE", "reason": "표본 축적 중",
        }
        if row["runs"] >= settings["query_health_min_runs"]:
            total_classified = max(row["anchor_match"], 1)
            mismatch_base = max(row["anchor_match"] + row["anchor_mismatch"], 1)
            if row["anchor_match"] == 0:
                row["status"], row["reason"] = "PAUSED", "3회 이상 수집 통과 0건"
            elif row["anchor_match"] >= settings["query_health_min_accepted_for_review"] and row["scene"] == 0:
                row["status"], row["reason"] = "REVIEW", "수집 10건 이상이나 시민 손실 장면 0건"
            elif row["anchor_mismatch"] / mismatch_base > settings["query_health_mismatch_rate_review"]:
                row["status"], row["reason"] = "REVIEW", "주제 불일치율 50% 초과"
            elif row["noise"] / total_classified > settings["query_health_noise_rate_review"]:
                row["status"], row["reason"] = "REVIEW", "생활정보·언론·재연 비중 50% 초과"
        stored[identity] = row
    rows = sorted(stored.values(), key=lambda row: (row.get("status", ""), row.get("agenda", ""), row.get("query", "")))
    QUERY_HEALTH.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rows


def update_signal_ledger(records: list[dict], config: dict, now) -> tuple[list[dict], int]:
    try:
        stored_rows = json.loads(SIGNAL_LEDGER.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        stored_rows = []
    normalized_stored = [normalize_record(row, config) for row in stored_rows if row.get("id")]
    stored = {row["id"]: row for row in normalized_stored if row}
    existing_ids = set(stored)
    observed_at = now.isoformat()
    for record in records:
        previous = stored.get(record["id"], {})
        labels = {
            (row.get("agenda"), row.get("cluster"), row.get("query")): row
            for row in previous.get("query_labels", []) + record.get("query_labels", [])
        }
        record["query_labels"] = list(labels.values())
        record["observed_first"] = previous.get("observed_first", observed_at)
        record["observed_last"] = observed_at
        stored[record["id"]] = record
    cutoff = now - timedelta(days=config["youtube_discovery"]["persistence_days"])
    kept = []
    for row in stored.values():
        try:
            published = base_datetime(row.get("published_at", ""))
        except ValueError:
            continue
        if published >= cutoff:
            kept.append(row)
    SIGNAL_LEDGER.write_text(json.dumps(kept, ensure_ascii=False), encoding="utf-8")
    new_unique = len({row.get("id") for row in records if row.get("id")} - existing_ids)
    return kept, new_unique


def base_datetime(value: str):
    from datetime import datetime
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def build_clusters(records: list[dict], config: dict) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for record in records:
        for label in record["query_labels"]:
            grouped[(label["agenda"], label["cluster"])].append(record)
    clusters = []
    for (agenda, name), rows in grouped.items():
        unique = {row["id"]: row for row in rows}.values()
        rows = list(unique)
        channels = {row["channel"] for row in rows}
        qualified_types = {"당사자 가능성", "상담·지원", "현장·운영자"}
        qualified = [row for row in rows if row["source_archetype"] in qualified_types]
        direct_rows = [row for row in qualified if row["source_archetype"] in {"당사자 가능성", "현장·운영자"}]
        direct_scene_rows = [
            row for row in direct_rows
            if any(label.get("lane") in {"SCENE", "SOURCE"} for label in row.get("query_labels", []))
        ]
        non_media = {row["channel"] for row in qualified}
        scene_rows = [row for row in qualified if row["signal_markers"]]
        concrete_rows = [row for row in qualified if row["verification_markers"] or row["seoul_place_terms"]]
        first_person_rows = [row for row in qualified if row["first_person_markers"]]
        advice_rows = [row for row in rows if row["source_archetype"] == "생활정보·설명"]
        corroborated = len(non_media) >= 2 and len(scene_rows) >= 2 and bool(direct_rows)
        lead = bool(scene_rows or direct_scene_rows)
        score = min(len(non_media), 3) * 3 + min(len(scene_rows), 3) * 2 + min(len(concrete_rows), 2)
        score += min(len(first_person_rows), 2) * 2
        score -= len(advice_rows) * 3 + sum(1 for row in qualified if row["is_short"])
        clusters.append({
            "agenda": agenda, "cluster": name, "records": rows,
            "independent_channels": len(channels), "non_media_channels": len(non_media),
            "scene_records": len(scene_rows), "concrete_records": len(concrete_rows),
            "first_person_records": len(first_person_rows), "advice_records": len(advice_rows),
            "readiness": "CORROBORATED" if corroborated else "LEAD" if lead else "HOLD",
            "lead_basis": "독립 비언론 2개 이상" if corroborated else "단일 손실 표현 또는 직접 생활 장면" if lead else "유효 시민 단서 미달",
            "score": score,
            "comments": [], "comment_signal_count": 0,
        })
    level_order = {"HOLD": 0, "LEAD": 1, "CORROBORATED": 2}
    return sorted(clusters, key=lambda row: (level_order[row["readiness"]], row["score"], row["non_media_channels"]), reverse=True)


def enrich_comments(request, key: str, clusters: list[dict], config: dict):
    settings = config["youtube_discovery"]
    for cluster in clusters[:settings["comment_clusters_per_run"]]:
        samples = []
        signal_count = 0
        for record in sorted(cluster["records"], key=lambda row: row["views"], reverse=True)[:2]:
            query = urllib.parse.urlencode({
                "part": "snippet", "videoId": record["id"], "order": "relevance",
                "textFormat": "plainText", "maxResults": settings["comments_per_cluster"], "key": key,
            })
            try:
                items = request("https://www.googleapis.com/youtube/v3/commentThreads?" + query).get("items", [])
            except urllib.error.HTTPError as exc:
                if exc.code in {403, 404}:
                    continue
                raise
            for item in items:
                text = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {}).get("textDisplay", "")
                if text_matches(text, settings["signal_markers"]):
                    signal_count += 1
                    if len(samples) < 3:
                        samples.append(re.sub(r"\s+", " ", text).strip()[:180])
        cluster["comment_signal_count"] = signal_count
        cluster["comments"] = samples
        if cluster["readiness"] == "HOLD" and signal_count >= 2:
            cluster["readiness"] = "LEAD"
            cluster["lead_basis"] = "댓글의 반복 손실 표현"


def collect_background(base, request, key: str, config: dict, now) -> list[dict]:
    rows = []
    for channel in config.get("youtube_watch_channels", []):
        channel_query = urllib.parse.urlencode({"part": "contentDetails", "id": channel["id"], "key": key})
        items = request("https://www.googleapis.com/youtube/v3/channels?" + channel_query).get("items", [])
        if not items:
            continue
        uploads = items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
        playlist_query = urllib.parse.urlencode({"part": "contentDetails", "playlistId": uploads, "maxResults": 15, "key": key})
        ids = [item.get("contentDetails", {}).get("videoId") for item in request("https://www.googleapis.com/youtube/v3/playlistItems?" + playlist_query).get("items", [])]
        valid_ids = [video_id for video_id in ids if video_id]
        for start in range(0, len(valid_ids), 50):
            detail_query = urllib.parse.urlencode({
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(valid_ids[start:start + 50]), "key": key,
            })
            detail_items = request(
                "https://www.googleapis.com/youtube/v3/videos?" + detail_query
            ).get("items", [])
            for item in detail_items:
                record = base.video_record(item, {f"배경·{channel['name']}"}, now)
                if text_matches(
                    record["title"] + " " + record["description"],
                    config.get("youtube_editorial_keywords", []),
                ):
                    rows.append(record)
    return sorted(rows, key=lambda row: row["published_at"], reverse=True)


def collect_naver(base, config: dict, client_id: str, client_secret: str, today):
    rows = []
    for start in range(0, len(config["lenses"]), 5):
        rows.extend(base.collect_naver({**config, "lenses": config["lenses"][start:start + 5]}, client_id, client_secret, today))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="유튜브 행동·증거·장면·당사자 검색 수집기 v2.3")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--audit-all", action="store_true", help="감사 예산으로 9개 의제를 검색")
    mode.add_argument("--manual", action="store_true", help="수동 점검 예산으로 최대 8개 표현 검색")
    parser.add_argument("--preview-queries", action="store_true", help="API를 호출하지 않고 이번 회차 검색식과 예산만 표시")
    args = parser.parse_args()
    base = load_base()
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    now = base.datetime.now(base.KST)
    run_mode = "audit" if args.audit_all else "manual" if args.manual else "regular"
    OUTPUT.mkdir(parents=True, exist_ok=True)
    errors = []
    youtube_run_status = "OK"
    search_records, records, clusters, background, naver = [], [], [], [], []
    query_health = load_query_health()
    paused_keys = {query_identity(row) for row in query_health if row.get("status") == "PAUSED"}
    if args.preview_queries:
        preview_usage = load_api_usage()
        preview = {
            "run_mode": run_mode,
            "usage": usage_summary(
                preview_usage, now, config["youtube_discovery"], run_mode
            ),
            "queries": selected_queries(
                config, now, run_mode, paused_keys, query_health
            ),
        }
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return 0
    new_unique_count = 0
    search_metrics = {"query_count": 0, "queries": [], "search_hits": 0, "unique_video_ids": 0, "detail_records": 0, "hard_excluded": 0, "query_mismatch": 0, "accepted_records": 0, "per_query": []}
    key = os.environ.get("YOUTUBE_API_KEY")
    naver_id = os.environ.get("NAVER_CLIENT_ID")
    naver_secret = os.environ.get("NAVER_CLIENT_SECRET")
    request = None
    if key:
        try:
            request = guarded_get_json(base, now, config, run_mode)
            search_records, search_metrics = collect_search_records(
                base, request, key, config, now, run_mode, paused_keys, query_health
            )
            if search_metrics["query_count"] == 0:
                youtube_run_status = "BUDGET_SKIPPED"
                records, _ = update_signal_ledger([], config, now)
                clusters = build_clusters(records, config)
            else:
                query_health = update_query_health(search_metrics, config, now)
                records, new_unique_count = update_signal_ledger(search_records, config, now)
                clusters = build_clusters(records, config)
                enrich_comments(request, key, clusters, config)
                level_order = {"HOLD": 0, "LEAD": 1, "CORROBORATED": 2}
                clusters.sort(key=lambda row: (level_order[row["readiness"]], row["score"], row["non_media_channels"]), reverse=True)
                background = collect_background(base, request, key, config, now)
        except Exception as exc:
            errors.append("youtube: " + str(exc))
            youtube_run_status = "ERROR_CACHED"
            records, _ = update_signal_ledger([], config, now)
            clusters = build_clusters(records, config)
    else:
        errors.append("youtube: YOUTUBE_API_KEY 미설정")
    api_usage = (
        request.usage_summary() if request
        else usage_summary(
            load_api_usage(), now, config["youtube_discovery"], run_mode
        )
    )
    if naver_id and naver_secret:
        try:
            naver = collect_naver(base, config, naver_id, naver_secret, now.date())
        except Exception as exc:
            errors.append("naver: " + str(exc))
    else:
        errors.append("naver: NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET 미설정")

    review_queue = [
        row for row in records
        if row.get("source_archetype") == "분류 대기" and row.get("signal_markers") and not row.get("advice_markers")
    ]
    raw = {
        "collected_at": now.isoformat(),
        "collector_version": "2.3",
        "youtube_run_status": youtube_run_status,
        "youtube_api_usage": api_usage,
        "youtube_new_records": search_records,
        "youtube_new_unique_count": new_unique_count,
        "youtube_funnel": search_metrics,
        "youtube_query_health": query_health,
        "youtube_records": records,
        "youtube_clusters": clusters,
        "youtube_review_queue": review_queue,
        "youtube_background": background,
        "naver": naver,
        "errors": errors,
    }
    stamp = now.strftime("%Y-%m-%d-%H%M")
    (OUTPUT / f"source_material_{stamp}_v2.3.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    selected = search_metrics["queries"]
    lines = [
        "# 서울 기획기사 관심 레이더 v2.3 — 행동·증거·장면·당사자 검색", "",
        f"수집 시각: {now.isoformat()}",
        f"유튜브 실행 상태: {youtube_run_status}",
        f"API 예산일: {api_usage['quota_day']} ({api_usage['quota_timezone']}) / 정규 {api_usage['regular_search_attempts']}/40 / 수동·감사 {api_usage['exploration_search_attempts']}/20 / 예비 {api_usage['reserved_calls']}회 보존",
        f"검색 의제: {', '.join(dict.fromkeys(row['agenda'] for row in selected))}",
        f"실행 검색식: {search_metrics['query_count']}개 / API 검색 결과 {search_metrics['search_hits']}건 / 고유 영상 ID {search_metrics['unique_video_ids']}건",
        f"상세 조회 {search_metrics['detail_records']}건 / 강제 제외 {search_metrics['hard_excluded']}건 / 주제 불일치 {search_metrics['query_mismatch']}건 / 수집 통과 {search_metrics['accepted_records']}건 / 새 고유 영상 {new_unique_count}건",
        f"누적 관찰창: 최근 {config['youtube_discovery']['persistence_days']}일 / 누적 영상 {len(records)}건",
        "", "주의: 영상과 댓글은 시민 언어·현장·섭외 단서이며 사실 확인 근거가 아닙니다.",
        "", "## 유튜브 반복 현상 군집", "",
    ]
    for cluster in clusters:
        lines.append(f"### [{cluster['readiness']}] {cluster['cluster']} ({cluster['agenda']})")
        lines.append(f"- 판정 근거: {cluster['lead_basis']}")
        lines.append(f"- 점수 {cluster['score']} / 독립 채널 {cluster['independent_channels']} / 유효 비언론 채널 {cluster['non_media_channels']} / 손실 표현 {cluster['scene_records']} / 1인칭 경험 {cluster['first_person_records']} / 확인 단서 {cluster['concrete_records']} / 생활정보·설명 {cluster['advice_records']}")
        queries = sorted({label["query"] for row in cluster["records"] for label in row["query_labels"] if label["cluster"] == cluster["cluster"]})
        lines.append(f"- 사용한 시민 표현: {', '.join(queries)}")
        for record in sorted(cluster["records"], key=lambda row: (bool(row["signal_markers"]), row["views"]), reverse=True)[:3]:
            markers = ", ".join(record["signal_markers"][:3]) or "없음"
            lines.append(f"- 영상: [{record['source_archetype']}] {record['title']} / {record['channel']} / 손실표현 {markers} / {record['url']}")
        lines.append(f"- 댓글 반복표현 감지: {cluster['comment_signal_count']}건")
        for sample in cluster["comments"]:
            lines.append(f"  - 댓글 단서: {sample}")
        lines.append("- 다음 단계: 동일 현상의 서울 장소·집단·규모를 독립 자료로 확인")
        lines.append("")
    if not clusters:
        lines.append("- 없음. 이번 회차 검색어에서 군집 가능한 영상이 잡히지 않았습니다.\n")
    lines += ["## 검색 표현 건강도", ""]
    current_health = {query_identity(row): row for row in query_health}
    for query_row in search_metrics.get("per_query", []):
        health = current_health.get(query_identity(query_row), {})
        lines.append(
            f"- [{query_row.get('selection_tier', '-')}/{query_row['lane']}/{health.get('status', 'ACTIVE')}] {query_row['query']} / "
            f"API {query_row['api_hits']} / 일치 {query_row['anchor_match']} / 불일치 {query_row['anchor_mismatch']} / "
            f"현장·당사자·상담 {query_row['qualified']} / 손실 장면 {query_row['scene']} / 서울 {query_row['seoul']} / "
            f"{health.get('reason', '표본 축적 중')}"
        )
    paused_count = sum(row.get("status") == "PAUSED" for row in query_health)
    review_count = sum(row.get("status") == "REVIEW" for row in query_health)
    lines.append(f"- 누적 판정: REVIEW {review_count}개 / PAUSED {paused_count}개")
    lines += ["## 발굴 검토함", ""]
    for row in sorted(review_queue, key=lambda item: item.get("views", 0), reverse=True)[:10]:
        markers = ", ".join(row.get("signal_markers", [])[:3]) or "없음"
        lines.append(f"- [분류 대기] {row['title']} / {row['channel']} / 손실표현 {markers} / {row['url']}")
    if not review_queue:
        lines.append("- 없음. 손실 표현은 있으나 출처 유형이 불명확한 영상이 없습니다.")
    lines += ["## 편집 관찰 채널의 배경 자료", ""]
    for row in background[:5]:
        lines.append(f"- {row['title']} / {row['channel']} / {row['url']}")
    if not background:
        lines.append("- 없음")
    lines += ["", "## 네이버 검색 흐름", ""]
    for row in naver:
        ratio = f"{row['ratio']}배" if row["ratio"] is not None else "비교 불가"
        lines.append(f"- {row['lens']}: 최근 7일 {row['recent_7d']:.2f} / 이전 7일 {row['previous_7d']:.2f} / {ratio}")
    if errors:
        lines += ["", "## 수집 진단", ""] + [f"- {error}" for error in errors]
    lines += [
        "", "## 편집 사용 규칙", "",
        "- LEAD는 단일 시민·현장·댓글 단서이며 사실 확인 전에는 기사 근거로 쓰지 않습니다.",
        "- CORROBORATED는 독립 비언론 채널 두 곳 이상에서 반복된 현상 단서이며 기사 후보가 아닙니다.",
        "- 댓글은 사실·규모의 근거로 인용하지 않고 검색어와 섭외 단서로만 씁니다.",
        "- 서울시 발표는 유튜브 현상의 독립 발견 원천으로 역산하지 않습니다.",
        "- 검색 표현은 3회 이상 관찰한 뒤 수율·불일치·소음 기준으로 REVIEW 또는 PAUSED 처리합니다.",
    ]
    latest = OUTPUT / "source_material_latest.txt"
    latest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"완료: {latest}")
    print(
        f"검색 통과 {len(search_records)}건 / 새 고유 {new_unique_count}건 / 누적 {len(records)}건 / "
        f"군집 {len(clusters)}건 / LEAD {sum(row['readiness'] == 'LEAD' for row in clusters)}건 / "
        f"CORROBORATED {sum(row['readiness'] == 'CORROBORATED' for row in clusters)}건 / "
        f"검색식 REVIEW {sum(row.get('status') == 'REVIEW' for row in query_health)}개 / "
        f"PAUSED {sum(row.get('status') == 'PAUSED' for row in query_health)}개"
    )
    return 1 if errors and not (clusters or naver) else 0


if __name__ == "__main__":
    raise SystemExit(main())
