import unittest
from datetime import datetime, timezone
from unittest import mock

import keyword_discovery


class CommentWeightTests(unittest.TestCase):
    def test_comment_weight_increases_for_high_points(self):
        base = keyword_discovery._comment_weight(0)
        boosted = keyword_discovery._comment_weight(120)
        self.assertEqual(base, 1.0)
        self.assertGreater(boosted, base)
        self.assertLessEqual(boosted, 1.9)


class GlossaryTests(unittest.TestCase):
    def test_glossary_matches_detects_domains(self):
        text = "Highly scalable quantum computing and autonomous robotics in orbit"
        tokens, domains = keyword_discovery._glossary_matches(text)
        self.assertTrue(tokens)
        self.assertTrue(domains)
        status = keyword_discovery.get_glossary_status()
        self.assertGreaterEqual(status["token_count"], len(tokens))
        self.assertGreaterEqual(status["domain_count"], len(domains))


class NoveltyTests(unittest.TestCase):
    def test_apply_novelty_boosts_score_when_mentions_exceed_baseline(self):
        candidates = [
            {
                "term": "fusion battery",
                "score": 12.0,
                "novelty_multiplier": 1.0,
                "mentions": 6,
            }
        ]
        fake_db = mock.Mock()
        fake_db.get_keyword_baseline.return_value = {"avg_mentions": 2.0}
        with mock.patch.object(keyword_discovery, "database", fake_db):
            keyword_discovery._apply_novelty(
                candidates,
                run_timestamp=datetime.now(timezone.utc),
                lookback_days=90,
            )
        self.assertGreater(candidates[0]["score"], 12.0)
        self.assertGreater(candidates[0]["novelty_multiplier"], 1.0)


if __name__ == "__main__":
    unittest.main()
