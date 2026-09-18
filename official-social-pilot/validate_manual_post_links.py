#!/usr/bin/env python3
"""Validate editor-submitted Facebook post links without opening Facebook."""
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
REGISTRY = HERE / "accounts.json"
INTAKE = HERE / "manual_post_links.json"
POST_ID = re.compile(r"[A-Za-z0-9._-]{2,160}\Z")


def account_identity(url: str) -> tuple[str, str] | None:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in {"facebook.com", "www.facebook.com", "m.facebook.com"}:
        return None
    if parsed.path.rstrip("/").lower() == "/profile.php":
        values = parse_qs(parsed.query).get("id", [])
        return ("numeric", values[0]) if len(values) == 1 and values[0].isdigit() else None
    parts = [part for part in parsed.path.split("/") if part]
    return ("handle", parts[0].lower()) if len(parts) == 1 and re.fullmatch(r"[A-Za-z0-9._-]{2,80}", parts[0]) else None


def post_owner(url: str) -> tuple[str, str] | None:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in {"facebook.com", "www.facebook.com", "m.facebook.com"}:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) == 3 and parts[1].lower() == "posts" and POST_ID.fullmatch(parts[2]):
        return ("handle", parts[0].lower())
    if parsed.path.rstrip("/").lower() == "/permalink.php":
        values = parse_qs(parsed.query)
        story = values.get("story_fbid", [])
        owner = values.get("id", [])
        if len(story) == len(owner) == 1 and owner[0].isdigit() and POST_ID.fullmatch(story[0]):
            return ("numeric", owner[0])
    return None


def validate(data: dict, registry: dict) -> list[str]:
    if data.get("schema") != 1 or not isinstance(data.get("entries"), list):
        return ["invalid intake schema"]
    registered = {}
    for entity in registry.get("entities", []):
        for account in entity.get("officeholder_accounts", []):
            identity = account_identity(account.get("url", ""))
            if identity:
                registered[identity] = (entity["id"], account["officeholder_name"])
    errors = []
    seen = set()
    for index, row in enumerate(data["entries"]):
        prefix = f"entry {index}"
        url = row.get("post_url", "")
        owner = post_owner(url)
        if owner is None:
            errors.append(f"{prefix}: unsupported Facebook post URL")
            continue
        if owner not in registered:
            errors.append(f"{prefix}: post owner is not one of the 26 registered accounts")
        if url in seen:
            errors.append(f"{prefix}: duplicate post URL")
        seen.add(url)
        try:
            date.fromisoformat(row.get("observed_on", ""))
        except ValueError:
            errors.append(f"{prefix}: observed_on must be YYYY-MM-DD")
        if not row.get("entity_id") or not row.get("officeholder_name"):
            errors.append(f"{prefix}: entity and officeholder name are required")
        elif owner in registered and (row["entity_id"], row["officeholder_name"]) != registered[owner]:
            errors.append(f"{prefix}: entity/name does not match registered owner")
        if row.get("review_status") not in {"EDITOR_SUBMITTED_UNREVIEWED", "EDITOR_CONFIRMED_PUBLIC_LINK"}:
            errors.append(f"{prefix}: invalid review status")
        if len(row.get("editor_note", "")) > 500:
            errors.append(f"{prefix}: editor_note exceeds 500 characters")
    return errors


def render(data: dict, errors: list[str]) -> str:
    lines = [
        "# 편집자 제출 페이스북 게시물 링크",
        "",
        f"- 제출 링크: {len(data.get('entries', []))}건",
        f"- 형식·계정 대조 오류: {len(errors)}건",
        "- 페이스북 프로필·게시물 자동 접근: 0건",
        "- 게시물 본문·댓글 저장: 0건",
        "- 브리핑·장부 연결: 없음",
        "",
    ]
    if errors:
        lines += ["## 수정 필요", ""] + [f"- {error}" for error in errors] + [""]
    else:
        lines += [
            "링크 형식과 등록 계정 대조만 통과했습니다. 이 결과는 게시물의 진위·게시일·내용을 독립 검증한 것이 아닙니다.",
            "다음 편집 단계에서 링크를 직접 열어 사실관계와 기사 가치, 독립 근거를 확인해야 합니다.",
            "",
        ]
    return "\n".join(lines)


def main() -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument("--intake", type=Path, default=INTAKE)
    cli.add_argument("--output", type=Path, default=HERE / "output" / "manual-post-links" / "SUMMARY.md")
    args = cli.parse_args()
    data = json.loads(args.intake.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    errors = validate(data, registry)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(data, errors), encoding="utf-8")
    print(render(data, errors))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
