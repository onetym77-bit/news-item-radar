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
DEFAULT_BUNDLE_STATIC = (
    DEFAULT_BRIEFING,
    DEFAULT_FEED,
    ROOT / "agent-system-v1" / "VERIFICATION_QUEUE.csv",
    ROOT / "source-scout-v1" / "HUMAN_REVIEW_QUEUE.csv",
    ROOT / "source-scout-v1" / "output" / "daily_feed_latest.md",
    ROOT / "source-scout-v1" / "output" / "review_summary_latest.json",
    ROOT / "source-scout-v1" / "output" / "review_summary_latest.md",
    ROOT / "source-scout-v1" / "output" / "editorial_review_cards_latest.json",
    ROOT / "source-scout-v1" / "output" / "editorial_review_cards_latest.md",
    ROOT / "source-scout-v1" / "output" / "legacy_anchor_rereview_latest.md",
    ROOT / "source-scout-v1" / "output" / "grounding_comparison_latest.md",
)
START = "<!-- RUN-METADATA:START -->"
END = "<!-- RUN-METADATA:END -->"
BLOCK_RE = re.compile(re.escape(START) + r".*?" + re.escape(END) + r"\n*", re.S)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bundle_index_sha(entries: dict[str, str]) -> str:
    payload = json.dumps(
        entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(payload)


def history_paths(args: argparse.Namespace, manifest: dict) -> tuple[Path, Path]:
    day = str(manifest["generated_at_kst"])[:10]
    run_id = str(manifest["run_id"])
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise RuntimeError("invalid generated day for history path")
    if not re.fullmatch(r"[0-9A-Za-z_.-]+", run_id):
        raise RuntimeError("invalid run id for history path")
    return (
        args.briefing.parent / "history" / f"briefing_{day}_{run_id}.md",
        args.feed.parent / "history" / f"daily_feed_{day}_{run_id}.json",
    )


def expected_bundle_paths(args: argparse.Namespace, manifest: dict) -> list[Path]:
    explicit = list(getattr(args, "bundle_files", []) or [])
    if explicit:
        return explicit
    briefing_history, feed_history = history_paths(args, manifest)
    return [*DEFAULT_BUNDLE_STATIC, briefing_history, feed_history]


def bundle_key(args: argparse.Namespace, path: Path) -> str:
    root = Path(getattr(args, "bundle_root", ROOT)).resolve()
    resolved = path.resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise RuntimeError(f"bundle file outside root: {path}") from exc


def seal_bundle(args: argparse.Namespace, manifest: dict) -> None:
    entries: dict[str, str] = {}
    for path in expected_bundle_paths(args, manifest):
        if not path.is_file():
            raise RuntimeError(f"bundle file missing: {path}")
        key = bundle_key(args, path)
        if key in entries:
            raise RuntimeError(f"duplicate bundle path: {key}")
        entries[key] = sha256_bytes(path.read_bytes())
    entries = dict(sorted(entries.items()))
    manifest["bundle_files"] = entries
    manifest["bundle_sha256"] = bundle_index_sha(entries)


def verify_bundle(args: argparse.Namespace, manifest: dict) -> list[str]:
    errors: list[str] = []
    recorded = manifest.get("bundle_files")
    if not isinstance(recorded, dict) or not recorded:
        return ["bundle manifest missing"]
    if manifest.get("bundle_sha256") != bundle_index_sha(recorded):
        errors.append("bundle index hash mismatch")
    expected = {
        bundle_key(args, path): path
        for path in expected_bundle_paths(args, manifest)
    }
    if set(recorded) != set(expected):
        missing = sorted(set(expected) - set(recorded))
        extra = sorted(set(recorded) - set(expected))
        errors.append(f"bundle membership mismatch missing={missing} extra={extra}")
    for key, path in expected.items():
        if not path.is_file():
            errors.append(f"bundle file missing: {key}")
        elif recorded.get(key) != sha256_bytes(path.read_bytes()):
            errors.append(f"bundle file hash mismatch: {key}")
    return errors


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
    if manifest["stale_at_generation"]:
        status = "구판 사용 금지"
    elif mode == "main" and manifest["persisted"]:
        status = "MAIN 게시본 — 유효 시한 이후에는 구판"
    elif mode == "replay":
        status = "현재 장부를 지정일 기준으로 재계산 + 현재 소스 — 미리보기만"
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
        f"- 생성 시 구판 판정: {'예' if manifest['stale_at_generation'] else '아니오'}"
        + (f" ({', '.join(manifest['stale_reasons'])})" if manifest["stale_reasons"] else ""),
    ]
    if mode == "replay":
        rows.extend([
            f"- 적용 기준일: {manifest.get('requested_as_of') or '미지정'}",
            "- 재현 한계: 과거 장부 스냅샷이 아니며, 현재 장부와 실행 시점의 현재 소스를 함께 사용함",
        ])
    rows.extend([END, ""])
    return "\n".join(rows)

def create_manifest(args: argparse.Namespace) -> dict:
    requested_as_of = str(getattr(args, "as_of", "") or "").strip()
    if args.mode == "replay" and not requested_as_of:
        raise RuntimeError("replay mode requires --as-of")
    if args.mode != "replay" and requested_as_of:
        raise RuntimeError("--as-of is valid only in replay mode")
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
        "schema_version": "1.1",
        "requested_as_of": requested_as_of,
        "source_snapshot_semantics": (
            "current_ledger_recalculated_as_of_plus_current_sources"
            if args.mode == "replay"
            else "current_at_execution"
        ),
        "run_id": args.run_id,
        "run_url": args.run_url,
        "code_sha": args.code_sha,
        "source_sha": args.source_sha,
        "generated_at_kst": generated.isoformat(timespec="seconds"),
        "policy_version": policy_version,
        "publication_mode": args.mode,
        "publishable": args.mode == "main",
        "persisted": persisted,
        "stale_at_generation": bool(stale_reasons),
        "stale_reasons": stale_reasons,
        "stale_after_kst": stale_after.isoformat(timespec="seconds"),
        "stale_evaluation": "verify_at_read_time",
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

    briefing_history, feed_history = history_paths(args, manifest)
    briefing_history.parent.mkdir(parents=True, exist_ok=True)
    feed_history.parent.mkdir(parents=True, exist_ok=True)
    briefing_history.write_text(
        args.briefing.read_text(encoding="utf-8"), encoding="utf-8"
    )
    feed_history.write_bytes(args.feed.read_bytes())

    seal_bundle(args, manifest)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
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
    expected_source_sha = str(getattr(args, "source_sha", "") or "").strip()
    if expected_source_sha and manifest.get("source_sha") != expected_source_sha:
        errors.append("source sha mismatch")
    at_time_raw = getattr(args, "at_time", "") or ""
    at_time = (
        datetime.fromisoformat(at_time_raw)
        if at_time_raw
        else datetime.now(ZoneInfo("Asia/Seoul"))
    )
    if at_time.tzinfo is None:
        at_time = at_time.replace(tzinfo=ZoneInfo("Asia/Seoul"))
    stale_after = datetime.fromisoformat(manifest["stale_after_kst"])
    if at_time > stale_after:
        errors.append(
            f"artifact expired at {manifest['stale_after_kst']}; regenerate before use"
        )
    if mode == "main" and manifest.get("persisted") is not True:
        errors.append("main briefing not marked persisted")
    if mode in {"preview", "replay"} and manifest.get("publishable") is True:
        errors.append("preview/replay cannot be publishable")
    errors.extend(verify_bundle(args, manifest))
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
    parser.add_argument("--as-of", default="")
    parser.add_argument("--bundle-root", type=Path, default=ROOT)
    parser.add_argument(
        "--bundle-file", dest="bundle_files", action="append", type=Path, default=[]
    )
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--at-time", default="", help="ISO time override for deterministic validation")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return verify(args) if args.verify else write(args)


if __name__ == "__main__":
    raise SystemExit(main())
