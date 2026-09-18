#!/usr/bin/env python3
"""Read-only L0 check of official links; never fetches social posts or profiles."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
REGISTRY = HERE / "accounts.json"
DIRECTORY = "https://mediahub.seoul.go.kr/staticpage/sns.do"
EXPECTED_DISTRICTS = {
    "gangnam", "gwanak", "nowon", "mapo", "seongdong", "jongno",
    "junggu", "yongsan", "seongbuk", "gangbuk", "dobong", "eunpyeong",
    "seodaemun", "yangcheon", "gangseo", "gwangjin", "dongdaemun",
    "jungnang", "guro", "geumcheon", "yeongdeungpo", "dongjak",
    "seocho", "songpa", "gangdong",
}
PLATFORMS = {"youtube", "instagram", "facebook", "blog"}
MAX_BYTES = 1_000_000
KST = timezone(timedelta(hours=9))


def safe_https(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password


def canonical(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme.lower()}://{(parsed.hostname or '').lower()}{parsed.path.rstrip('/')}"


class LinkParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: set[str] = set()

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            absolute = urljoin(self.base_url, href)
            if safe_https(absolute):
                self.links.add(canonical(absolute))


def validate_registry(data: dict) -> list[str]:
    errors = []
    if data.get("schema") != 1:
        errors.append("schema must be 1")
    entities = data.get("entities")
    if not isinstance(entities, list):
        return errors + ["entities must be a list"]
    ids = [item.get("id") for item in entities]
    if len(ids) != 26 or set(ids) != EXPECTED_DISTRICTS | {"seoul"}:
        errors.append("exactly Seoul and the 25 district IDs are required")
    if len(ids) != len(set(ids)):
        errors.append("duplicate entity ID")
    account_urls = set()
    for entity in entities:
        entity_id = entity.get("id", "?")
        if not entity.get("name"):
            errors.append(f"{entity_id}: name missing")
        site = entity.get("official_site")
        if site is not None and not safe_https(site):
            errors.append(f"{entity_id}: official_site must be safe HTTPS or null")
        if site is not None and (
            not safe_https(entity.get("official_site_source", ""))
            or entity.get("official_site_verification") != "GOV24_LISTED"
            or not entity.get("official_site_checked_on")
        ):
            errors.append(f"{entity_id}: official_site lacks government-directory evidence")
        for field in ("institution_accounts", "officeholder_accounts"):
            accounts = entity.get(field)
            if not isinstance(accounts, list):
                errors.append(f"{entity_id}: {field} must be a list")
                continue
            for account in accounts:
                url = account.get("url", "")
                evidence = account.get("verification_source", "")
                if account.get("platform") not in PLATFORMS:
                    errors.append(f"{entity_id}: unsupported platform")
                if not safe_https(url) or not safe_https(evidence):
                    errors.append(f"{entity_id}: account and evidence need safe HTTPS")
                if account.get("verification_kind") != "OFFICIAL_DIRECTORY_LINK":
                    errors.append(f"{entity_id}: account lacks official-link evidence")
                if not account.get("checked_on"):
                    errors.append(f"{entity_id}: checked_on missing")
                if canonical(url) in account_urls:
                    errors.append(f"{entity_id}: duplicate account URL")
                account_urls.add(canonical(url))
    return errors


def fetch_directory(url: str = DIRECTORY) -> tuple[str, str | None]:
    request = Request(url, headers={"User-Agent": "news-item-radar-l0/1.0", "Accept": "text/html"})
    try:
        with urlopen(request, timeout=15) as response:
            final = urlparse(response.geturl())
            expected = urlparse(url)
            if final.scheme != "https" or final.hostname != expected.hostname:
                return "SOURCE_UNAVAILABLE", None
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                return "SOURCE_UNAVAILABLE", None
            if response.headers.get_content_type() not in {"text/html", "application/xhtml+xml"}:
                return "SOURCE_UNAVAILABLE", None
            charset = response.headers.get_content_charset() or "utf-8"
            return "SUCCESS", raw.decode(charset, errors="replace")
    except (HTTPError, URLError, OSError, TimeoutError, ValueError):
        return "SOURCE_UNAVAILABLE", None


def evaluate(data: dict, source_status: str, html: str | None) -> dict:
    parser = LinkParser(DIRECTORY)
    if source_status == "SUCCESS" and html is not None:
        parser.feed(html)
    rows = []
    for entity in data["entities"]:
        accounts = entity["institution_accounts"] + entity["officeholder_accounts"]
        for account in accounts:
            listed = source_status == "SUCCESS" and canonical(account["url"]) in parser.links
            if account["verification_source"] != DIRECTORY:
                status = "OTHER_OFFICIAL_SOURCE_NOT_PROBED"
            elif source_status != "SUCCESS":
                status = "SOURCE_UNAVAILABLE"
            else:
                status = "CONFIRMED_LISTED" if listed else "NOT_LISTED_NEEDS_REVIEW"
            rows.append({
                "entity_id": entity["id"], "account_type": (
                    "institution" if account in entity["institution_accounts"] else "officeholder"
                ),
                "platform": account["platform"], "url": account["url"],
                "verification_source": account["verification_source"], "status": status,
            })
    return {
        "schema": 1,
        "scope": "L0_ACCOUNT_LINKS_ONLY",
        "checked_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "official_directory_status": source_status,
        "entity_count": len(data["entities"]),
        "entities_without_registered_accounts": [
            entity["id"] for entity in data["entities"]
            if not entity["institution_accounts"] and not entity["officeholder_accounts"]
        ],
        "accounts": rows,
        "posts_collected": 0,
        "briefing_connected": False,
    }


def render(result: dict) -> str:
    counts = {}
    for row in result["accounts"]:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return "\n".join([
        "# 공식 SNS 계정 L0 연결 점검",
        "",
        f"- 대상: {result['entity_count']}개 행정 단위(서울시 + 25개 구)",
        f"- 계정 등록: {len(result['accounts'])}개; 미등록 행정 단위: {len(result['entities_without_registered_accounts'])}개",
        f"- 서울시 공식 목록 접근: {result['official_directory_status']}",
        f"- 목록 재확인: {counts.get('CONFIRMED_LISTED', 0)}개; 재검토 필요: {counts.get('NOT_LISTED_NEEDS_REVIEW', 0)}개",
        f"- 공식 목록 접속 불가로 확인 보류: {counts.get('SOURCE_UNAVAILABLE', 0)}개",
        "",
        "미등록은 계정이 없다는 뜻이 아니며, 접속 실패도 계정 삭제나 게시물 0건을 뜻하지 않습니다.",
        "기관 계정과 단체장 개인 계정은 별도로 기록합니다. 이 단계는 게시물·질문·브리핑을 수집하거나 생성하지 않습니다.",
        "",
    ])


def main() -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument("--output-dir", type=Path, default=HERE / "output" / "l0")
    cli.add_argument("--offline", action="store_true", help="validate registry only")
    args = cli.parse_args()
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    errors = validate_registry(data)
    if errors:
        print("\n".join(f"ERROR: {item}" for item in errors))
        return 1
    status, html = ("NOT_ATTEMPTED", None) if args.offline else fetch_directory()
    result = evaluate(data, status, html)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = render(result)
    (args.output_dir / "SUMMARY.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
