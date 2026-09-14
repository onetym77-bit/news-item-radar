import importlib.util
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


provenance = load_module("run_provenance_test", "run_provenance.py")


class ProvenanceTests(unittest.TestCase):
    def make_args(self, root: Path, mode="preview"):
        briefing = root / "briefing.md"
        feed = root / "feed.json"
        config = root / "config.json"
        manifest = root / "manifest.json"
        briefing.write_text("# 브리핑\n\n본문\n", encoding="utf-8")
        feed.write_text(
            json.dumps(
                {"generated_at_kst": "2026-09-14T10:00:00+09:00"},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        config.write_text(
            json.dumps({"system_version": "1.6"}, ensure_ascii=False),
            encoding="utf-8",
        )
        return Namespace(
            briefing=briefing,
            feed=feed,
            config=config,
            manifest=manifest,
            mode=mode,
            run_id="12345",
            run_url="https://github.com/example/actions/runs/12345",
            code_sha="abcdef1234567890",
            source_sha="abcdef1234567890",
            verify=False,
            at_time="2026-09-14T10:05:00+09:00",
        )

    def test_preview_is_visibly_not_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.make_args(Path(tmp), "preview")
            provenance.write(args)
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            rendered = args.briefing.read_text(encoding="utf-8")
            self.assertFalse(manifest["persisted"])
            self.assertFalse(manifest["publishable"])
            self.assertIn("main 최신본 아님", rendered)
            self.assertEqual(provenance.verify(args), 0)

    def test_main_marks_exact_artifact_as_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.make_args(Path(tmp), "main")
            provenance.write(args)
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            self.assertTrue(manifest["persisted"])
            self.assertTrue(manifest["publishable"])
            self.assertIn("MAIN 게시본", args.briefing.read_text(encoding="utf-8"))

    def test_replay_cannot_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.make_args(Path(tmp), "replay")
            provenance.write(args)
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            self.assertFalse(manifest["publishable"])
            self.assertIn("과거 날짜 재실행", args.briefing.read_text(encoding="utf-8"))

    def test_expired_artifact_fails_at_read_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.make_args(Path(tmp), "preview")
            provenance.write(args)
            args.at_time = "2026-09-15T12:00:01+09:00"
            with self.assertRaisesRegex(RuntimeError, "artifact expired"):
                provenance.verify(args)

    def test_feed_tamper_fails_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.make_args(Path(tmp), "preview")
            provenance.write(args)
            args.feed.write_text('{"changed": true}', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "feed hash mismatch"):
                provenance.verify(args)

    def test_workflow_collects_once_and_separates_read_from_write(self):
        workflow = (ROOT / ".github" / "workflows" / "daily-briefing.yml").read_text(
            encoding="utf-8"
        )
        command = "python -X utf8 source-scout-v1/collect_daily_feed.py"
        self.assertEqual(workflow.count(command), 1)
        self.assertNotIn("Recollect", workflow)
        self.assertIn("run_provenance.py --verify", workflow)
        self.assertIn("actions/upload-artifact@v7", workflow)
        self.assertIn("actions/download-artifact@v8", workflow)
        self.assertIn("interest-radar-v2/config/editorial_lenses.json", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("build-and-validate:", workflow)
        self.assertIn("persist-main:", workflow)
        self.assertIn("needs: build-and-validate", workflow)
        self.assertIn("Confirm protected ledgers were not changed", workflow)
        self.assertIn("Persist only the explicit generated-file allowlist", workflow)
        self.assertLess(
            workflow.index("Upload the validated build package"),
            workflow.index("persist-main:"),
        )
        self.assertLess(
            workflow.index('git push origin "HEAD:'),
            workflow.index("Upload the exact persisted result"),
        )


if __name__ == "__main__":
    unittest.main()
