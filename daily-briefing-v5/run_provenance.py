#!/usr/bin/env python3
"""Attach and verify provenance for the exact briefing artifact being published."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BRIEFING = ROOT / "daily-briefing-v5" / "output" / "briefing_latest.md"
DEFAULT_FEED = ROOT / "source-scout-v1" / "output" / "daily_feed_latest.json"
DEFAULT_CONFIG = ROOT / "interest-radar-v2" / "config" / "editorial_lenses.json"
DEFAULT_MANIFEST = ROOT / "daily-briefing-v5" / "output" / "run_manifest_latest.json"
START = "<!-- RUN-METADATA:START -->"
END = "<!-- RUN-METADATA:END -->"
BLOCK_RE = re.compile(re.escape(START) + r".*?" + re.escape(END) + r"\n*", re.S)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def body_without_metadata(text: str) -> str:
    return BLOCK_RE.sub("", text, count=1)


def read_policy_version(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    value = str(payload.get("system_version", "")).strip()
    if not value:
        raise RuntimeError("editorial_lenses.json system_version missing")
    return value


def render_block(manifest: dict) -> str:
    mode = manifest["publication_mode"]
    if manifest["stale"]:
        status = "구판 사용 금지"
    elif mode == "main" and manifest["persisted"]:
        status = "MAIN 게시본"
    elif mode == "replay":
        status = "과거 날짜 재실행 — 미리보기만"
    else:
        status = "PR·브랜치 미리보기 — main 최신본 아님"
    rows = [
        START,
        f"> **상태: {status}**",
        "",
        "| 실행 ID | 검사 코드 | 생성 시각(KST) | 정책 | 공개 모드 | 저장 여부 | 유효 시한 |",
        "|---|---|---|---|---|---|---|",
        (
            f"| [{manifest['run_id']}]({manifest['run_url']}) | "
            f"`{manifest['code_sha'][:12]}` | {manifest['generated_at_kst']} | "
            f"v{manifest['policy_version']} | {mode} | "
            f"{'예' if manifest['persisted'] else '아니오'} | {manifest['stale_after_kst']} |"
        ),
        "",
        f"- 원본 지문: `{manifest['feed_sha256'][:16]}`",
        f"- 본문 지문: `{manifest['briefing_body_sha256'][:16]}`",
        f"- 구판 판정: {'예' if manifest['stale'] else '아니오'}"
        + (f" ({', '.join(manifest['stale_reasons'])})" if manifest["stale_reasons"] else ""),
        END,
        "",
    ]
    return "\n".join(rows)


def create_manifest(args: argparse.Namespace) -> dict:
    briefing_text = args.briefing.read_text(encoding="utf-8")
    feed_bytes = args.feed.read_bytes()
    feed = json.loads(feed_bytes.decode("utf-8"))
    generated_raw = str(feed.get("generated_at_kst", ""))
    generated = datetime.fromisoformat(generated_raw)
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=ZoneInfo("Asia/Seoul"))
    stale_after = generated + timedelta(hours=26)
    policy_version = read_policy_version(args.config)
    persisted = args.mode == "main"
    stale_reasons: list[str] = []
    if args.mode == "main" and not persisted:
        stale_reasons.append("main_not_persisted")
    manifest = {
        "schema_version": "1.0",
        "run_id": args.run_id,
        "run_url": args.run_url,
        "code_sha": args.code_sha,
        "source_sha": args.source_sha,
        "generated_at_kst": generated.isoformat(timespec="seconds"),
        "policy_version": policy_version,
        "publication_mode": args.mode,
        "publishable": args.mode == "main",
        "persisted": persisted,
        "stale": bool(stale_reasons),
        "stale_reasons": stale_reasons,
        "stale_after_kst": stale_after.isoformat(timespec="seconds"),
        "feed_sha256": sha256_bytes(feed_bytes),
        "briefing_body_sha256": sha256_bytes(
            body_without_metadata(briefing_text).encode("utf-8")
        ),
    }
    return manifest


def write(args: argparse.Namespace) -> int:
    manifest = create_manifest(args)
    original = args.briefing.read_text(encoding="utf-8")
    body = body_without_metadata(original)
    args.briefing.write_text(render_block(manifest) + body, encoding="utf-8")
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    history = args.briefing.parent / "history"
    history.mkdir(parents=True, exist_ok=True)
    day = manifest["generated_at_kst"][:10]
    (history / f"briefing_{day}_{manifest['run_id']}.md").write_text(
        args.briefing.read_text(encoding="utf-8"), encoding="utf-8"
    )
    print(f"provenance={args.manifest}")
    return verify(args)


def verify(args: argparse.Namespace) -> int:
    if not args.manifest.is_file():
        raise RuntimeError("run manifest missing")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    briefing_text = args.briefing.read_text(encoding="utf-8")
    errors: list[str] = []
    if START not in briefing_text or END not in briefing_text:
        errors.append("briefing metadata block missing")
    if manifest.get("feed_sha256") != sha256_bytes(args.feed.read_bytes()):
        errors.append("feed hash mismatch")
    body_hash = sha256_bytes(body_without_metadata(briefing_text).encode("utf-8"))
    if manifest.get("briefing_body_sha256") != body_hash:
        errors.append("briefing body hash mismatch")
    current_policy = read_policy_version(args.config)
    if manifest.get("policy_version") != current_policy:
        errors.append("policy version mismatch")
    mode = manifest.get("publication_mode")
    if mode == "main" and manifest.get("persisted") is not True:
        errors.append("main briefing not marked persisted")
    if mode in {"preview", "replay"} and manifest.get("publishable") is True:
        errors.append("preview/replay cannot be publishable")
    if errors:
        raise RuntimeError("; ".join(errors))
    print(
        "verified exact artifact "
        f"run={manifest['run_id']} feed={manifest['feed_sha256'][:12]} "
        f"body={manifest['briefing_body_sha256'][:12]}"
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--briefing", type=Path, default=DEFAULT_BRIEFING)
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--mode", choices=("main", "preview", "replay"), default="preview")
    parser.add_argument("--run-id", default="local")
    parser.add_argument("--run-url", default="")
    parser.add_argument("--code-sha", default="local")
    parser.add_argument("--source-sha", default="")
    parser.add_argument("--verify", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return verify(args) if args.verify else write(args)


if __name__ == "__main__":
    raise SystemExit(main())
