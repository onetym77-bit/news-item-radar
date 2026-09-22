"""Read-only, provenance-aware summaries of non-news source exploration.

These rows are observations for editorial review, never final article candidates.
"""
import json
from collections import Counter
from pathlib import Path


def _load(root: Path, relative_path: str):
    try:
        value = json.loads((root / relative_path).read_text(encoding="utf-8"))
        return value, True
    except (OSError, ValueError):
        return None, False


def _text(value, limit=220):
    value = " ".join(str(value or "").split())
    return value[:limit].rstrip() + ("…" if len(value) > limit else "")


def _row(source_id, source, stage, status, collected_at, observed, review_count, reason, url=""):
    return {
        "source_id": source_id,
        "source": source,
        "stage": stage,
        "status": status,
        "collected_at": collected_at or "저장된 실행 없음",
        "observed": observed,
        "review_count": review_count,
        "reason": reason,
        "url": url,
    }


def build_source_exploration(root: Path, interest_queue: dict):
    """Normalize persisted collection states without promoting any source to a story."""
    sources = []
    clues = []
    generated = interest_queue.get("generated_at_utc", "")
    news_items = interest_queue.get("items", [])
    sources.append(_row(
        "news_interest", "뉴스·검색 관심", "본문 탐색",
        "수집됨" if generated else "결과 없음", generated, len(news_items),
        sum(bool(item.get("content_assessment")) for item in news_items),
        "기사 본문 판정은 사실 검증이나 최종 편집 승인이 아닙니다."
        if generated else "최신 탐색 큐 파일이 없습니다.",
    ))

    feed, feed_ok = _load(root, "source-scout-v1/output/daily_feed_latest.json")
    if feed_ok and isinstance(feed, dict):
        collected_at = feed.get("generated_at_kst", "")
        for metric in feed.get("metrics", []):
            observed = int(metric.get("extracted") or 0)
            if not metric.get("http_ok"):
                status = "수집 실패"
                reason = "접속 또는 검증에 실패했습니다. 항목 0건으로 해석하지 않습니다."
            elif observed == 0:
                status = "수집됨 · 항목 없음"
                reason = "이번 저장 실행에서 읽은 항목이 없습니다."
            else:
                status = "수집됨"
                reason = (
                    f"읽은 항목 {observed}건, 원자료 적격 {int(metric.get('qualified') or 0)}건. "
                    "적격은 기사 후보 선정이나 독립 사실 검증이 아닙니다."
                )
            sources.append(_row(
                metric.get("id", "daily_unknown"), metric.get("name", "일일 피드"),
                "일일 원자료" if metric.get("role") != "VERIFICATION" else "후속 검증 자료",
                status, collected_at, observed if metric.get("http_ok") else None,
                int(metric.get("qualified") or 0) if metric.get("http_ok") else None,
                reason, metric.get("main_url", ""),
            ))
        for item in feed.get("editorial_triage", [])[:5]:
            if item.get("triage_status") != "EDITOR_REVIEW" or not item.get("url"):
                continue
            subject = _text(item.get("context_subject"), 75)
            title = subject if subject and len(subject) <= 65 else "시의회 발언 · 사안명 확인 필요"
            clues.append({
                "source_id": item.get("source_id", "council_minutes"),
                "source": item.get("source_name", "서울시의회 회의록"),
                "title": title,
                "date": item.get("source_date", ""),
                "url": item["url"],
                "status": "편집 검토 · 사실 미확인",
                "reason": _text(item.get("triage_reason"), 160) or "원문 맥락과 사안 가치를 확인해야 합니다.",
                "excerpt": _text(item.get("display_fact") or item.get("text"), 200),
                "next_step": "사안의 가치와 수치 기준기간을 원문에서 확인",
            })
    else:
        sources.append(_row(
            "daily_feed", "서울시의회·응답소 등 일일 피드", "일일 원자료",
            "결과 없음", "", None, None, "저장된 수집 결과를 읽지 못했습니다.",
        ))

    watch, watch_ok = _load(root, "district-council-pilot/output/watch/state_latest.json")
    last_watch = watch.get("last_run", {}) if watch_ok and isinstance(watch, dict) else {}
    if last_watch:
        results = last_watch.get("results", [])
        counts = Counter(row.get("status", "미확인") for row in results)
        new_count = sum(int(row.get("new_count") or 0) for row in results)
        sources.append(_row(
            "district_councils", "25개 자치구의회 회의록", "목록 감시 · 본문 미평가",
            "저장된 관측", last_watch.get("collected_at_kst", ""), len(results), 0,
            f"공식 목록 첫 화면만 비교했습니다. 새 주소 {new_count}건, 접속·수집 미확인 {counts.get('UNKNOWN_COLLECTION', 0)}곳. "
            "회의록 본문과 기획 질문은 만들지 않았습니다.",
        ))
    else:
        sources.append(_row(
            "district_councils", "25개 자치구의회 회의록", "목록 감시 · 본문 미평가",
            "결과 없음", "", None, None, "저장된 관측 결과가 없습니다.",
        ))

    audit, audit_ok = _load(root, "source-onboarding-v1/output/audit-l4/state_latest.json")
    runs = audit.get("runs", []) if audit_ok and isinstance(audit, dict) else []
    if runs:
        latest = runs[-1]
        diag = latest.get("diagnostics", {})
        selected_ids = set(latest.get("selected_ids", []))
        status = "그림자 검토" if latest.get("listing_status") == "SUCCESS" else "수집 실패"
        sources.append(_row(
            "seoul_audit_results", "서울시 감사 결과", "L4 그림자 평가 · 운영 미승인",
            status, latest.get("run_date_kst", ""), int(diag.get("pdf_extracted") or 0),
            int(diag.get("ready_questions") or 0),
            f"이번 표본의 질문 준비 {int(diag.get('ready_questions') or 0)}건, 보류 {int(diag.get('held_questions') or 0)}건. "
            "그림자 평가 결과는 최종 후보에 자동 편입하지 않습니다.",
        ))
        for record in audit.get("records", []):
            if record.get("source_record_id") not in selected_ids:
                continue
            card = record.get("card", {})
            if not card.get("detail_url"):
                continue
            ready = card.get("question_status") == "READY_FOR_HUMAN_REVIEW"
            clues.append({
                "source_id": "seoul_audit_results",
                "source": "서울시 감사 결과",
                "title": _text(card.get("selected_finding_title") or card.get("title"), 100),
                "date": card.get("published_at", ""),
                "url": card["detail_url"],
                "status": "그림자 질문 · 미승인" if ready else "본문 검토 보류",
                "reason": _text(
                    "감사 지적을 확인했지만 독립 검증과 운영 승인이 필요합니다."
                    if ready else card.get("hold_reason") or "대표 지적을 확인하지 못했습니다.", 160
                ),
                "excerpt": _text(card.get("verification_question"), 200) if ready else "",
                "next_step": "공식 감사문서의 지적·처분 대조" if ready else "PDF의 개별 지적 확인",
            })
    else:
        sources.append(_row(
            "seoul_audit_results", "서울시 감사 결과", "L4 그림자 평가 · 운영 미승인",
            "결과 없음", "", None, None, "저장된 그림자 평가 결과가 없습니다.",
        ))

    youtube, youtube_ok = _load(root, "interest-radar-v2/output/youtube_query_health_v2_3.json")
    if youtube_ok and isinstance(youtube, list):
        counts = Counter(row.get("status", "미확인") for row in youtube)
        dates = [row.get("last_run", "") for row in youtube if row.get("last_run")]
        sources.append(_row(
            "youtube_interest", "유튜브 시민 관심", "검색 전략 시험 · 개별 영상 미편입",
            "검색 시험", max(dates) if dates else "", len(youtube), 0,
            f"검색 전략 {len(youtube)}개 중 활성 {counts.get('ACTIVE', 0)}개, 재검토 {counts.get('REVIEW', 0)}개, "
            f"일시중지 {counts.get('PAUSED', 0)}개. 누적 검색 적격 수는 기사 후보 수가 아닙니다.",
        ))
    else:
        sources.append(_row(
            "youtube_interest", "유튜브 시민 관심", "검색 전략 시험 · 개별 영상 미편입",
            "결과 없음", "", None, None, "저장된 검색 전략 상태가 없습니다.",
        ))

    sources.append(_row(
        "community_social", "지역 SNS·커뮤니티", "게시물 소스 발굴",
        "연결 보류", "", None, None, "검증된 공개 지역 페이지의 게시물 자동 수집은 아직 없습니다.",
    ))
    return {"schema": 1, "sources": sources, "clues": clues}
