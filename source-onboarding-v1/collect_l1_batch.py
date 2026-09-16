#!/usr/bin/env python3
"""Bounded L1 listing inventory for the first two technically reachable sources."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import socket
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import Request, build_opener

from probe_l0_batch import MAX_RESPONSE_BYTES, SafeRedirectHandler
from thin_source_contract import load_registry, validate_thin_observation

TARGET_IDS = ("environment_assessment", "seoul_audit_results")
MAX_RECORDS = 20
DATE_RE = re.compile(r"(?<!\d)(20\d{2})[-./]\s*(\d{1,2})[-./]\s*(\d{1,2})(?!\d)")
AUDIT_ID_RE = re.compile(r"^/gov/archives/(\d+)(?:$|[/?#])")
PATH_IN_SCRIPT_RE = re.compile(r"((?:https://[^\s'\"]+|/eims/[^\s'\"]+?\.do(?:\?[^\s'\"]*)?))")
LONG_ID_RE = re.compile(r"(?<!\d)(\d{10,})(?!\d)")
FUNCTION_RE = re.compile(r"([A-Za-z_$][\w$]*)\s*\(")


def now_kst() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def clean_text(value: str) -> str:
    return " ".join(html.unescape(value).split()).strip()


class ListingParser(HTMLParser):
    """Collect anchor metadata and visible-token positions, not raw page bodies."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tokens: list[str] = []
        self.anchors: list[dict] = []
        self._ignored_depth = 0
        self._anchor: dict | None = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "template"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag == "a":
            attr_map = {str(k).lower(): str(v or "") for k, v in attrs}
            self._anchor = {
                "href": attr_map.get("href", ""),
                "onclick": attr_map.get("onclick", ""),
                "title_parts": [],
                "token_index": len(self.tokens),
            }

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "template"}:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return
        if not self._ignored_depth and tag == "a" and self._anchor is not None:
            self._anchor["title"] = clean_text(" ".join(self._anchor.pop("title_parts")))
            self._anchor["after_token_index"] = len(self.tokens)
            self.anchors.append(self._anchor)
            self._anchor = None

    def handle_data(self, data):
        if self._ignored_depth:
            return
        normalized = clean_text(data)
        if not normalized:
            return
        self.tokens.append(normalized)
        if self._anchor is not None:
            self._anchor["title_parts"].append(normalized)


def fetch_html(url: str, timeout: int = 20) -> tuple[str, str | None, dict]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return "FAILED", None, {"error_code": "UNSAFE_SOURCE_URL", "http_status": None}
    redirects = SafeRedirectHandler(parsed.hostname)
    opener = build_opener(redirects)
    request = Request(
        url,
        headers={
            "User-Agent": "news-item-radar-l1-inventory/1.0 (+read-only; contact via repository)",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
        },
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            final = urlparse(response.geturl())
            if final.scheme != "https" or (final.hostname or "").lower() != parsed.hostname.lower():
                return "FAILED", None, {"error_code": "FINAL_URL_OUTSIDE_OFFICIAL_HOST", "http_status": response.getcode()}
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                return "PARTIAL", None, {"error_code": "RESPONSE_TRUNCATED", "http_status": response.getcode()}
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                return "PARTIAL", None, {"error_code": "NON_HTML_RESPONSE", "http_status": response.getcode()}
            charset = response.headers.get_content_charset() or "utf-8"
            return "SUCCESS", raw.decode(charset, errors="replace"), {
                "error_code": None,
                "http_status": response.getcode(),
                "response_bytes": len(raw),
                "content_sha256": hashlib.sha256(raw).hexdigest(),
                "redirect_count": redirects.redirect_count,
            }
    except HTTPError as exc:
        return "FAILED", None, {"error_code": f"HTTP_{exc.code}", "http_status": exc.code}
    except (TimeoutError, socket.timeout):
        return "FAILED", None, {"error_code": "TIMEOUT", "http_status": None}
    except URLError:
        return "FAILED", None, {"error_code": "NETWORK_ERROR", "http_status": None}
    except (ValueError, UnicodeError):
        return "FAILED", None, {"error_code": "SECURITY_OR_DECODE_ERROR", "http_status": None}


def nearby_text(parser: ListingParser, anchor: dict, before: int = 2, after: int = 12) -> str:
    start = max(0, anchor["token_index"] - before)
    end = min(len(parser.tokens), anchor["after_token_index"] + after)
    return " ".join(parser.tokens[start:end])


def iso_date(text: str) -> str | None:
    match = DATE_RE.search(text)
    if not match:
        return None
    year, month, day = map(int, match.groups())
    try:
        return f"{year:04d}-{month:02d}-{day:02d}"
    except ValueError:
        return None


def fingerprint(record_id: str, title: str, url: str, published_at: str | None) -> str:
    raw = "\x1f".join((record_id, title, url, published_at or ""))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def record(record_id: str, title: str, url: str, published_at: str | None, date_status: str, observed_at: str) -> dict:
    return {
        "source_record_id": record_id,
        "title": title[:300],
        "detail_url": url,
        "published_at": published_at,
        "published_at_status": date_status,
        "observed_at_kst": observed_at,
        "access_status": "SUCCESS",
        "body_status": "NOT_FETCHED",
        "content_fingerprint": fingerprint(record_id, title, url, published_at),
    }


def parse_audit(html_text: str, source_url: str, observed_at: str) -> tuple[list[dict], dict]:
    parser = ListingParser()
    parser.feed(html_text)
    records = []
    seen = set()
    date_missing = 0
    for anchor in parser.anchors:
        absolute = urljoin(source_url, anchor["href"])
        parsed = urlparse(absolute)
        match = AUDIT_ID_RE.match(parsed.path)
        title = anchor["title"]
        if not match or len(title) < 4:
            continue
        record_id = match.group(1)
        if record_id in seen:
            continue
        context = nearby_text(parser, anchor, before=0, after=16)
        date_value = iso_date(context)
        if not date_value or "등록일" not in context:
            date_missing += 1
            continue
        seen.add(record_id)
        records.append(record(record_id, title, absolute, date_value, "VERIFIED", observed_at))
        if len(records) >= MAX_RECORDS:
            break
    return records, {
        "candidate_count": len(seen) + date_missing,
        "date_missing_count": date_missing,
        "unresolved_detail_url_count": 0,
        "unresolved_link_shapes": [],
    }


def section_bounds(tokens: list[str], start_label: str, end_label: str) -> tuple[int, int] | None:
    starts = [i for i, token in enumerate(tokens) if start_label in token]
    if not starts:
        return None
    start = starts[-1]
    ends = [i for i, token in enumerate(tokens[start + 1 :], start + 1) if end_label in token]
    return start, (ends[0] if ends else len(tokens))


def safe_direct_url(source_url: str, href: str) -> str | None:
    if not href or href.lower().startswith("javascript:") or href == "#":
        return None
    absolute = urljoin(source_url, href)
    src = urlparse(source_url)
    parsed = urlparse(absolute)
    if parsed.scheme != "https" or parsed.hostname != src.hostname:
        return None
    if parsed.path == src.path and parsed.query == src.query:
        return None
    return absolute


def scripted_url_shape(anchor: dict, source_url: str) -> tuple[str | None, str]:
    script = " ".join((anchor.get("href", ""), anchor.get("onclick", "")))
    path_match = PATH_IN_SCRIPT_RE.search(script)
    if path_match:
        candidate = urljoin(source_url, html.unescape(path_match.group(1)))
        parsed = urlparse(candidate)
        source = urlparse(source_url)
        if parsed.scheme == "https" and parsed.hostname == source.hostname:
            return candidate, "SCRIPT_PATH"
    function = FUNCTION_RE.search(script)
    ids = LONG_ID_RE.findall(script)
    shape = (function.group(1) if function else "NO_FUNCTION") + ":" + ",".join(str(len(x)) for x in ids[:3])
    return None, shape


def id_from_url(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("esbID", "seq", "sn", "id", "idx", "no"):
        values = query.get(key)
        if values and values[0]:
            return values[0]
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]


def public_function_route_hints(html_text: str, function_name: str) -> list[str]:
    """Return only route-shaped literals from a public function definition."""
    match = re.search(
        rf"function\\s+{re.escape(function_name)}\\s*\\([^)]*\\)\\s*\\{{(.{{0,2500}}?)\\}}",
        html_text,
        flags=re.DOTALL,
    )
    hints: list[str] = []
    if match:
        body = match.group(1)
        for quoted in re.findall(r"['\"]([^'\"]{1,300})['\"]", body):
            token = html.unescape(quoted).strip()
            if ".do" in token or ".frg" in token:
                token = re.sub(r"[^A-Za-z0-9_./?=&{}-]", "", token)
                if token and token not in hints:
                    hints.append(token[:200])
    if not hints:
        for src in re.findall(r"<script[^>]+src=['\"]([^'\"]+)['\"]", html_text, flags=re.I):
            if src.startswith("/") and src not in hints:
                hints.append("SCRIPT:" + src[:180])
            if len(hints) >= 20:
                break
    return hints[:20]


def parse_environment(html_text: str, source_url: str, observed_at: str) -> tuple[list[dict], dict]:
    parser = ListingParser()
    parser.feed(html_text)
    function_hints = public_function_route_hints(html_text, "goNews")
    bounds = section_bounds(parser.tokens, "공고/공람", "자료실")
    if not bounds:
        return [], {
            "candidate_count": 0,
            "date_missing_count": 0,
            "unresolved_detail_url_count": 0,
            "unresolved_link_shapes": ["SECTION_NOT_FOUND"],
            "public_function_route_hints": function_hints,
        }
    start, end = bounds
    records = []
    seen_urls = set()
    unresolved = 0
    date_missing = 0
    shapes: list[str] = []
    candidates = 0
    for anchor in parser.anchors:
        if not (start <= anchor["token_index"] < end):
            continue
        title = anchor["title"]
        if len(title) < 4 or title.startswith("+"):
            continue
        context = nearby_text(parser, anchor, before=0, after=5)
        date_value = iso_date(context)
        if not date_value:
            continue
        candidates += 1
        detail_url = safe_direct_url(source_url, anchor["href"])
        shape = "DIRECT"
        if not detail_url:
            detail_url, shape = scripted_url_shape(anchor, source_url)
        if not detail_url:
            unresolved += 1
            if shape not in shapes and len(shapes) < 5:
                shapes.append(shape)
            continue
        if detail_url in seen_urls:
            continue
        seen_urls.add(detail_url)
        record_id = id_from_url(detail_url)
        records.append(record(record_id, title, detail_url, date_value, "CANDIDATE", observed_at))
        if len(records) >= MAX_RECORDS:
            break
    return records, {
        "candidate_count": candidates,
        "date_missing_count": date_missing,
        "unresolved_detail_url_count": unresolved,
        "unresolved_link_shapes": shapes,
        "public_function_route_hints": function_hints,
    }


def collect_one(source: dict, observed_at: str, fetcher=fetch_html) -> dict:
    source_url = source["official_url"]
    fetch_status, html_text, fetch_diagnostics = fetcher(source_url)
    records: list[dict] = []
    parse_diagnostics = {
        "candidate_count": 0,
        "date_missing_count": 0,
        "unresolved_detail_url_count": 0,
        "unresolved_link_shapes": [],
        "public_function_route_hints": [],
    }
    access_status = fetch_status
    if html_text is not None:
        if source["source_id"] == "seoul_audit_results":
            records, parse_diagnostics = parse_audit(html_text, source_url, observed_at)
        elif source["source_id"] == "environment_assessment":
            records, parse_diagnostics = parse_environment(html_text, source_url, observed_at)
        if not records or parse_diagnostics["unresolved_detail_url_count"]:
            access_status = "PARTIAL"
    diagnostics = dict(fetch_diagnostics)
    diagnostics.update(parse_diagnostics)
    return {
        "schema": 1,
        "source_id": source["source_id"],
        "maturity": source["maturity"],
        "collected_at_kst": observed_at,
        "source_url": source_url,
        "access_status": access_status,
        "coverage": "FIRST_OFFICIAL_LIST_PAGE_MAX_20",
        "records": records,
        "interpretation_status": "NOT_EVALUATED",
        "diagnostics": diagnostics,
    }


def render_summary(observations: list[dict]) -> str:
    lines = [
        "# L1 목록 표본 시험",
        "",
        "게시물 본문과 편집 질문은 수집하지 않았습니다.",
        "",
        "| 소스 | 접근 | 표본 | 후보 | 상세주소 미해결 | 날짜 누락 | 오류 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in observations:
        d = row["diagnostics"]
        lines.append(
            f"| {row['source_id']} | {row['access_status']} | {len(row['records'])} | "
            f"{d.get('candidate_count', 0)} | {d.get('unresolved_detail_url_count', 0)} | "
            f"{d.get('date_missing_count', 0)} | {d.get('error_code') or '-'} |"
        )
        shapes = d.get("unresolved_link_shapes") or []
        if shapes:
            lines.append(f"| ↳ 미해결 링크 형태 |  |  |  |  |  | {', '.join(shapes)} |")
        hints = d.get("public_function_route_hints") or []
        if hints:
            lines.append(f"| ↳ 공개 함수 경로 단서 |  |  |  |  |  | {', '.join(hints)} |")
    lines.extend(["", "## 수집된 목록 표본", ""])
    for row in observations:
        lines.append(f"### {row['source_id']}")
        if not row["records"]:
            lines.append("- 안전한 상세주소까지 확인된 표본 없음")
            continue
        for item in row["records"]:
            lines.append(f"- {item['published_at'] or '날짜 미확인'} · [{item['title']}]({item['detail_url']})")
    lines.extend(
        [
            "",
            "- PARTIAL·FAILED는 게시물 0건을 뜻하지 않습니다.",
            "- 표본은 질문·브리핑·장부에 연결되지 않습니다.",
            "",
        ]
    )
    return "\n".join(lines)


def run(output_dir: Path) -> list[dict]:
    registry = load_registry()
    sources = {row["source_id"]: row for row in registry["sources"]}
    observed_at = now_kst()
    observations = []
    for source_id in TARGET_IDS:
        observation = collect_one(sources[source_id], observed_at)
        errors = validate_thin_observation(observation, registry)
        if errors:
            raise RuntimeError(f"{source_id}: " + "; ".join(errors))
        observations.append(observation)
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle = {"schema": 1, "probe": "L1_LISTING_ONLY", "collected_at_kst": observed_at, "observations": observations}
    (output_dir / "l1_batch.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "SUMMARY.md").write_text(render_summary(observations), encoding="utf-8")
    return observations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("source-onboarding-v1/output/l1-batch"))
    args = parser.parse_args()
    print(render_summary(run(args.output_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
