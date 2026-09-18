#!/usr/bin/env python3
"""Read-only L0 scan of official municipal homepages for social account links."""
from __future__ import annotations

import argparse
import json
import socket
import ssl
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from verify_registry import REGISTRY, canonical, safe_https

MAX_BYTES = 1_000_000
MAX_CANDIDATES = 12
TIMEOUT = 12


def host_without_www(host: str | None) -> str:
    host = (host or "").lower()
    return host[4:] if host.startswith("www.") else host


class SameSiteRedirect(HTTPRedirectHandler):
    def __init__(self, original_url: str):
        super().__init__()
        self.host = host_without_www(urlparse(original_url).hostname)

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        absolute = urljoin(req.full_url, newurl)
        target = urlparse(absolute)
        if target.scheme != "https" or host_without_www(target.hostname) != self.host:
            raise ValueError("redirect_outside_listed_host")
        return super().redirect_request(req, fp, code, msg, headers, absolute)


def social_platform(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    host = host_without_www(parsed.hostname)
    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        return None
    first = parts[0].lower()
    if host == "youtube.com" and (first.startswith("@") or first in {"user", "channel", "c"}):
        return "youtube"
    if host == "instagram.com" and len(parts) == 1 and first not in {
        "p", "reel", "stories", "explore", "accounts", "share"
    }:
        return "instagram"
    if host == "facebook.com" and len(parts) == 1 and first not in {
        "share", "sharer", "posts", "events", "watch", "login", "pages"
    }:
        return "facebook"
    if host == "blog.naver.com" and len(parts) == 1:
        return "blog"
    return None


class SocialLinkParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.candidates: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if not href:
            return
        absolute = urljoin(self.base_url, href)
        if not safe_https(absolute):
            return
        platform = social_platform(absolute)
        if platform:
            self.candidates[canonical(absolute)] = platform


def scan_one(entity: dict) -> dict:
    url = entity["official_site"]
    row = {
        "entity_id": entity["id"],
        "official_site": url,
        "site_evidence": entity.get("official_site_source"),
        "status": "NOT_ATTEMPTED",
        "reason": None,
        "candidate_links": [],
    }
    if not url or not safe_https(url):
        row.update(status="NOT_ATTEMPTED", reason="OFFICIAL_SITE_MISSING")
        return row
    request = Request(url, headers={
        "User-Agent": "news-item-radar-social-l0/1.0",
        "Accept": "text/html,application/xhtml+xml",
    })
    try:
        with build_opener(SameSiteRedirect(url)).open(request, timeout=TIMEOUT) as response:
            final_url = response.geturl()
            initial = urlparse(url)
            final = urlparse(final_url)
            if final.scheme != "https" or host_without_www(final.hostname) != host_without_www(initial.hostname):
                row.update(status="FAILED", reason="REDIRECT_OUTSIDE_LISTED_HOST")
                return row
            if response.headers.get_content_type() not in {"text/html", "application/xhtml+xml"}:
                row.update(status="PARTIAL", reason="NON_HTML_RESPONSE")
                return row
            raw = response.read(MAX_BYTES + 1)
            truncated = len(raw) > MAX_BYTES
            charset = response.headers.get_content_charset() or "utf-8"
            parser = SocialLinkParser(final_url)
            parser.feed(raw[:MAX_BYTES].decode(charset, errors="replace"))
            row["candidate_links"] = [
                {"platform": platform, "url": link, "evidence_page": final_url,
                 "status": "CANDIDATE_OFFICIAL_PAGE_LINK"}
                for link, platform in sorted(parser.candidates.items())[:MAX_CANDIDATES]
            ]
            row["status"] = "PARTIAL" if truncated else "SUCCESS"
            row["reason"] = "RESPONSE_TRUNCATED" if truncated else None
            return row
    except HTTPError as exc:
        row.update(status="FAILED", reason=f"HTTP_{exc.code}")
    except (TimeoutError, socket.timeout):
        row.update(status="FAILED", reason="TIMEOUT")
    except URLError as exc:
        if isinstance(exc.reason, socket.gaierror):
            reason = "DNS_ERROR"
        elif isinstance(exc.reason, ssl.SSLError):
            reason = "TLS_ERROR"
        elif isinstance(exc.reason, (TimeoutError, socket.timeout)):
            reason = "TIMEOUT"
        else:
            reason = "NETWORK_ERROR"
        row.update(status="FAILED", reason=reason)
    except ValueError:
        row.update(status="FAILED", reason="REDIRECT_OR_URL_ERROR")
    except (OSError, UnicodeError):
        row.update(status="FAILED", reason="ACCESS_ERROR")
    return row


def run(entities: list[dict], workers: int = 4) -> dict:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(scan_one, entities))
    return {
        "schema": 1,
        "scope": "L0_HOMEPAGE_LINK_CANDIDATES_ONLY",
        "sites": rows,
        "posts_collected": 0,
        "accounts_auto_approved": 0,
        "briefing_connected": False,
    }


def render(result: dict) -> str:
    lines = [
        "# 26개 시·구청 공식 홈페이지 SNS 연결 후보",
        "",
        "정부24에 등재된 공식 누리집 첫 화면의 링크만 얇게 검사했습니다. 계정의 주체·활동 상태는 아직 승인하지 않았습니다.",
        "",
        "| 기관 | 접속 | 계정 링크 후보 | 제한·오류 |",
        "|---|---|---:|---|",
    ]
    for row in result["sites"]:
        lines.append(
            f"| {row['entity_id']} | {row['status']} | {len(row['candidate_links'])} | {row['reason'] or '-'} |"
        )
    lines += [
        "",
        "후보 0건은 계정 부재가 아닙니다. 첫 화면에 링크가 없거나 동적 구성일 수 있습니다.",
        "접속 실패는 계정·게시물 0건과 구분하며, 공식 홈페이지가 연결한 계정도 사람 확인 전에는 등록부에 자동 승인하지 않습니다.",
        "게시물·질문·브리핑·장부는 수집하거나 변경하지 않습니다.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument("--output-dir", type=Path, default=Path("official-social-pilot/output/site-links"))
    args = cli.parse_args()
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    result = run(data["entities"])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary = render(result)
    (args.output_dir / "SUMMARY.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
