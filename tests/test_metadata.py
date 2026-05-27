import unittest

from app.importer import _apply_series_to_title, _title_candidate
from app.integrations.metadata import MetadataClient


class MetadataResolutionTests(unittest.TestCase):
    def test_title_candidate_handles_trailing_author(self):
        title, series, confidence = _title_candidate(
            "The Way of Kings - Brandon Sanderson",
            "Brandon Sanderson",
            include_series_in_title=False,
        )

        self.assertEqual(title, "The Way of Kings")
        self.assertIsNone(series)
        self.assertGreaterEqual(confidence, 76)

    def test_title_candidate_keeps_series_when_configured(self):
        title, series, _ = _title_candidate(
            "Brandon Sanderson - Stormlight Archive 01 - The Way of Kings",
            "Brandon Sanderson",
            include_series_in_title=True,
        )

        self.assertEqual(series, "Stormlight Archive 01")
        self.assertEqual(title, "Stormlight Archive 01 - The Way of Kings")

    def test_apply_series_to_title_is_idempotent(self):
        title = _apply_series_to_title("Stormlight Archive 01 - The Way of Kings", "Stormlight Archive 01", True)

        self.assertEqual(title, "Stormlight Archive 01 - The Way of Kings")

    def test_openlibrary_scoring_uses_author_hint(self):
        brandon = MetadataClient._score_candidate(
            "the way of kings",
            "brandon sanderson",
            "The Way of Kings",
            ["Brandon Sanderson"],
        )
        wrong_author = MetadataClient._score_candidate(
            "the way of kings",
            "brandon sanderson",
            "The Way of Kings",
            ["Someone Else"],
        )

        self.assertGreater(brandon, wrong_author)


if __name__ == "__main__":
    unittest.main()
