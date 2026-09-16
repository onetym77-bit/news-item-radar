#!/usr/bin/env python3
"""Read-only L0 access probe for sources still held at access testing.

This probe records only page-level technical diagnostics. It never emits
source records, titles from listing rows, body text, questions, or briefing
content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import socket
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from thin_source_contract import load_registry, validate_thin_observation

KST_OFFSET = "+09:00"
TARGET_IDS = ("opengov_approvals",)
MAX_RESPONSE_BYTES = 1_500_000
TIMEOUT_SECONDS = 20
MIN_VISIBLE_TEXT_CHARS = 100
MIN_INTERNAL_LINKS_FOR_REVIEW = 3
DATE_TOKEN_RE = re.compile(
    r"(?:20\d{2}[-./년]\s*\d{1,2}(?:[-./월]\s*\d{1,2})?|\d{1,2}[-./월]\s*\d{1,2}일?)"
)


class SafeRedirectHandler(HTTPRedirectHandler):
    """Allow redirects only within the original HTTPS host."""

    def __init__(self, allowed_host: str):
        super().__init__()
        self.allowed_host = allowed_host.lower()
        self.redirect_count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        absolute = urljoin(req.full_url, newurl)
        parsed = urlparse(absolute)
        if parsed.scheme != "https" or (parsed.hostname or "").lower() != self.allowed_host:
            raise ValueError("redirect_target_outside_official_host")
        self.redirect_count += 1
        return super().redirect_request(req, fp, code, msg, headers, absolute)


class PageSignalParser(HTMLParser):
    """Count page-level structure without retaining source body text."""

    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.base_host = (urlparse(base_url).hostname or "").lower()
        self._ignored_depth = 0
        self._in_title = False
        self._title_parts: list[str] = []
        self._visible_parts: list[str] = []
        self.internal_link_count = 0
        self.article_like_node_count = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "template"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag == "title":
            self._in_title = True
        if tag in {"li", "article", "tr"}:
            self.article_like_node_count += 1
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                parsed = urlparse(urljoin(self.base_url, href))
                if parsed.scheme == "https" and (parsed.hostname or "").lower() == self.base_host:
                    self.internal_link_count += 1

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "template"}:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return
        if not self._ignored_depth and tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._ignored_depth:
            return
        normalized = " ".join(data.split())
        if not normalized:
            return
        self._visible_parts.append(normalized)
        if self._in_title:
            self._title_parts.append(normalized)

    @property
    def title(self) -> str:
        return " ".join(self._title_parts)[:160]

    @property
    def visible_text(self) -> str:
        return " ".join(self._visible_parts)


def now_kst() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _failure_diagnostics(code: str, http_status: int | None = None) -> dict:
    result = {
        "http_status": http_status,
        "error_code": code,
        "response_bytes": 0,
        "response_truncated": False,
        "content_type": None,
        "content_sha256": None,
        "page_title": None,
        "visible_text_chars": 0,
        "internal_link_count": 0,
        "article_like_node_count": 0,
        "date_like_token_count": 0,
        "redirect_count": 0,
    }
    return result


def fetch_url(
    url: str,
    *,
    timeout: int = TIMEOUT_SECONDS,
    max_bytes: int = MAX_RESPONSE_BYTES,
    opener=None,
) -> tuple[str, dict]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return "FAILED", _failure_diagnostics("UNSAFE_SOURCE_URL")

    redirect_handler = SafeRedirectHandler(parsed.hostname)
    active_opener = opener or build_opener(redirect_handler)
    request = Request(
        url,
        headers={
            "User-Agent": "news-item-radar-l0-probe/1.0 (+read-only; contact via repository)",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
        },
    )
    try:
        with active_opener.open(request, timeout=timeout) as response:
            status_code = response.getcode()
            final_url = response.geturl()
            final = urlparse(final_url)
            if final.scheme != "https" or (final.hostname or "").lower() != parsed.hostname.lower():
                return "FAILED", _failure_diagnostics("FINAL_URL_OUTSIDE_OFFICIAL_HOST", status_code)
            raw = response.read(max_bytes + 1)
            truncated = len(raw) > max_bytes
            bounded = raw[:max_bytes]
            content_type = response.headers.get_content_type()
            charset = response.headers.get_content_charset() or "utf-8"
            diagnostics = {
                "http_status": status_code,
                "error_code": None,
                "response_bytes": len(bounded),
                "response_truncated": truncated,
                "content_type": content_type,
                "content_sha256": hashlib.sha256(bounded).hexdigest(),
                "page_title": None,
                "visible_text_chars": 0,
                "internal_link_count": 0,
                "article_like_node_count": 0,
                "date_like_token_count": 0,
                "redirect_count": getattr(redirect_handler, "redirect_count", 0),
            }
            is_html = content_type in {"text/html", "application/xhtml+xml"}
            if not is_html:
                diagnostics["error_code"] = "NON_HTML_RESPONSE"
                return "PARTIAL", diagnostics
            text = bounded.decode(charset, errors="replace")
            parser = PageSignalParser(final_url)
            parser.feed(text)
            visible = parser.visible_text
            diagnostics.update(
                {
                    "page_title": parser.title or None,
                    "visible_text_chars": len(visible),
                    "internal_link_count": parser.internal_link_count,
                    "article_like_node_count": parser.article_like_node_count,
                    "date_like_token_count": len(DATE_TOKEN_RE.findall(visible)),
                }
            )
            partial = truncated or len(visible) < MIN_VISIBLE_TEXT_CHARS
            if truncated:
                diagnostics["error_code"] = "RESPONSE_TRUNCATED"
            elif len(visible) < MIN_VISIBLE_TEXT_CHARS:
                diagnostics["error_code"] = "LOW_VISIBLE_TEXT"
            return ("PARTIAL" if partial else "SUCCESS"), diagnostics
    except HTTPError as exc:
        return "FAILED", _failure_diagnostics(f"HTTP_{exc.code}", exc.code)
    except (TimeoutError, socket.timeout):
        return "FAILED", _failure_diagnostics("TIMEOUT")
    except URLError:
        return "FAILED", _failure_diagnostics("NETWORK_ERROR")
    except (ValueError, UnicodeError):
        return "FAILED", _failure_diagnostics("SECURITY_OR_DECODE_ERROR")


def technical_readiness(access_status: str, diagnostics: dict) -> str:
    if (
        access_status == "SUCCESS"
        and diagnostics.get("visible_text_chars", 0) >= MIN_VISIBLE_TEXT_CHARS
        and diagnostics.get("internal_link_count", 0) >= MIN_INTERNAL_LINKS_FOR_REVIEW
    ):
        return "READY_FOR_L1_REVIEW"
    return "KEEP_L0"


def build_observation(source: dict, collected_at: str | None = None, fetcher=fetch_url) -> dict:
    observed_at = collected_at or now_kst()
    source_url = source.get("official_url")
    if not source_url:
        access_status = "NOT_ATTEMPTED"
        diagnostics = _failure_diagnostics("OFFICIAL_URL_MISSING")
    else:
        access_status, diagnostics = fetcher(source_url)
    return {
        "schema": 1,
        "source_id": source["source_id"],
        "maturity": source["maturity"],
        "collected_at_kst": observed_at,
        "source_url": source_url,
        "access_status": access_status,
        "coverage": "ACCESS_ONLY_NO_RECORDS",
        "records": [],
        "interpretation_status": "NOT_EVALUATED",
        "technical_readiness": technical_readiness(access_status, diagnostics),
        "diagnostics": diagnostics,
    }


def render_summary(observations: list[dict]) -> str:
    lines = [
        "# L0 신규 소스 일괄 접속 시험",
        "",
        "이 결과는 접속·목록형 구조의 기술 진단일 뿐, 게시물 수집이나 편집 가치 판정이 아닙니다.",
        "",
        "| 소스 | 접속 | HTTP | 실패·제한 코드 | 본문 글자 | 내부 링크 | 목록형 노드 | 날짜형 토큰 | 다음 기술 검토 |",
        "|---|---:|---:|---|---:|---:|---:|---:|---|",
    ]
    for row in observations:
        d = row["diagnostics"]
        lines.append(
            f"| {row['source_id']} | {row['access_status']} | "
            f"{d.get('http_status') or '-'} | {d.get('error_code') or '-'} | "
            f"{d.get('visible_text_chars', 0)} | "
            f"{d.get('internal_link_count', 0)} | {d.get('article_like_node_count', 0)} | "
            f"{d.get('date_like_token_count', 0)} | {row['technical_readiness']} |"
        )
    lines.extend(
        [
            "",
            "- READY_FOR_L1_REVIEW는 목록 표본 수집을 검토할 기술 조건일 뿐 자동 승격이 아닙니다.",
            "- FAILED·PARTIAL은 게시물 0건을 뜻하지 않습니다.",
            "- 이 실행은 질문·브리핑·장부·원문을 생성하거나 저장하지 않습니다.",
            "",
        ]
    )
    return "\n".join(lines)


def run(output_dir: Path) -> list[dict]:
    registry = load_registry()
    sources = {row["source_id"]: row for row in registry["sources"]}
    collected_at = now_kst()
    observations = []
    for source_id in TARGET_IDS:
        source = sources[source_id]
        observation = build_observation(source, collected_at=collected_at)
        errors = validate_thin_observation(observation, registry)
        if errors:
            raise RuntimeError(f"{source_id}: " + "; ".join(errors))
        observations.append(observation)

    output_dir.mkdir(parents=True, exist_ok=True)
    bundle = {
        "schema": 1,
        "probe": "L0_ACCESS_ONLY",
        "collected_at_kst": collected_at,
        "observations": observations,
    }
    (output_dir / "l0_batch.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for observation in observations:
        (output_dir / f"{observation['source_id']}.json").write_text(
            json.dumps(observation, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    (output_dir / "SUMMARY.md").write_text(render_summary(observations), encoding="utf-8")
    return observations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("source-onboarding-v1/output/l0-batch"),
    )
    args = parser.parse_args()
    observations = run(args.output_dir)
    print(render_summary(observations))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
