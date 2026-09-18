import json
import unittest
from pathlib import Path

from collect_youtube_feed_trial import parse_feed, render, validate_config

HERE = Path(__file__).resolve().parent


class YoutubeFeedTrialTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((HERE / "youtube_feed_trial.json").read_text(encoding="utf-8"))
        self.registry = json.loads((HERE / "accounts.json").read_text(encoding="utf-8"))

    def test_eight_distinct_official_homepage_link_candidates(self):
        self.assertEqual(validate_config(self.config, self.registry), [])
        self.assertEqual(len(self.config["channels"]), 8)
        self.assertEqual(len({r["channel_id"] for r in self.config["channels"]}), 8)

    def test_offsite_evidence_and_repeated_channel_rejected(self):
        bad = json.loads(json.dumps(self.config))
        bad["channels"][0]["evidence_page"] = "https://example.com/fake"
        self.assertTrue(any("evidence" in e for e in validate_config(bad, self.registry)))
        bad = json.loads(json.dumps(self.config))
        bad["channels"][1]["channel_id"] = bad["channels"][0]["channel_id"]
        self.assertTrue(any("repeated channel ID" in e for e in validate_config(bad, self.registry)))

    def test_feed_keeps_only_matching_channel_with_valid_date(self):
        channel = self.config["channels"][0]["channel_id"]
        xml = f"""<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015">
          <link rel="self" href="https://www.youtube.com/feeds/videos.xml?channel_id={channel}"/>
          <entry><yt:videoId>AbCdEfGh123</yt:videoId><yt:channelId>{channel}</yt:channelId>
            <title>공식 영상</title><published>2026-09-18T01:00:00+00:00</published></entry>
          <entry><yt:videoId>AbCdEfGh124</yt:videoId><yt:channelId>UCwrongwrongwrongwrongwr</yt:channelId>
            <title>다른 채널</title><published>2026-09-18T01:00:00+00:00</published></entry>
        </feed>""".encode()
        status, items, invalid = parse_feed(xml, channel)
        self.assertEqual(status, "PARTIAL_INVALID_ENTRIES")
        self.assertEqual(len(items), 1)
        self.assertEqual(invalid, 1)
        self.assertEqual(items[0]["source_video_id"], "AbCdEfGh123")
        self.assertEqual(items[0]["date_status"], "VERIFIED_FEED_VALUE")
        self.assertNotIn("description", items[0])

    def test_feed_identity_mismatch_rejected(self):
        channel = self.config["channels"][0]["channel_id"]
        xml = b'<feed xmlns="http://www.w3.org/2005/Atom"><link rel="self" href="https://www.youtube.com/feeds/videos.xml?channel_id=UCdifferentdifferentdiff1"/></feed>'
        status, items, invalid = parse_feed(xml, channel)
        self.assertEqual((status, items, invalid), ("CHANNEL_MISMATCH", [], 0))

    def test_summary_does_not_imply_editorial_approval(self):
        row = {**self.config["channels"][0], "status": "SUCCESS_WITH_ITEMS", "invalid_entries": 0, "items": [{
            "title": "시험 영상", "url": "https://www.youtube.com/watch?v=AbCdEfGh123",
            "published_at": "2026-09-18T01:00:00+00:00",
        }]}
        summary = render({"channels": [row]})
        self.assertIn("소스 성숙도: L0 유지", summary)
        self.assertIn("제목만으로", summary)


if __name__ == "__main__":
    unittest.main()
