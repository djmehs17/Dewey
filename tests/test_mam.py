import unittest
import asyncio

from app.integrations.mam import MamClient
from app.settings import DeweySettings


class MamClientTests(unittest.TestCase):
    def test_normalize_rich_result(self):
        client = MamClient(DeweySettings(mam_id="test-token"))

        result = client._normalize(
            {
                "id": 123,
                "title": "Brandon Sanderson - Stormlight Archive 01 - The Way of Kings",
                "author_info": '{"1":"Brandon Sanderson"}',
                "narrator_info": '{"2":"Michael Kramer","3":"Kate Reading"}',
                "series_info": '{"4":["Stormlight Archive","1",1.0]}',
                "size": "1.5 GiB",
                "seeders": "12",
                "leechers": "3",
                "snatched": "456",
                "comments": "7",
                "tags": '{"10":"fantasy","11":"epic"}',
                "lang_code": "en",
                "catname": "Audiobooks - Fantasy",
                "category": "101",
                "main_cat": "13",
                "filetype": "m4b",
                "dl": "download-token",
            }
        )

        self.assertEqual(result.provider, "mam")
        self.assertEqual(result.torrent_id, "123")
        self.assertEqual(result.author, "Brandon Sanderson")
        self.assertEqual(result.narrator, "Michael Kramer, Kate Reading")
        self.assertEqual(result.series, "Stormlight Archive #1")
        self.assertEqual(result.size, 1610612736)
        self.assertEqual(result.seeders, 12)
        self.assertEqual(result.leechers, 3)
        self.assertEqual(result.snatches, 456)
        self.assertEqual(result.comments, 7)
        self.assertEqual(result.tags, ["fantasy", "epic"])
        self.assertEqual(result.format, "m4b")
        self.assertEqual(result.category, "Audiobooks - Fantasy")
        self.assertEqual(result.category_id, 101)
        self.assertEqual(result.main_category_id, 13)
        self.assertEqual(result.download_url, "https://www.myanonamouse.net/tor/download.php/download-token")
        self.assertTrue(result.requires_dewey_download)

    def test_normalize_marks_vip_and_freeleech(self):
        client = MamClient(DeweySettings(mam_id="test-token"))

        result = client._normalize(
            {
                "id": 1,
                "title": "The Way of Kings",
                "vip": "1",
                "free": "1",
                "fl_vip": "1",
                "personal_freeleech": "1",
                "my_snatched": "1",
                "filetype": "m4b",
            }
        )

        self.assertTrue(result.vip_only)
        self.assertTrue(result.freeleech)
        self.assertTrue(result.fl_vip)
        self.assertTrue(result.personal_freeleech)
        self.assertTrue(result.my_snatched)
        self.assertIn("VIP", result.flags)
        self.assertIn("Freeleech", result.flags)
        self.assertIn("FL/VIP", result.flags)
        self.assertIn("Personal FL", result.flags)
        self.assertIn("Snatched", result.flags)

    def test_parse_account_status_detects_vip_class(self):
        client = MamClient(DeweySettings(mam_id="test-token"))

        status = client._parse_account_status(
            {
                "user": {
                    "class": "VIP",
                    "bonus_points": "12,345",
                    "freeleech_wedges": "617",
                }
            }
        )

        self.assertEqual(status.vip_status, "active")
        self.assertEqual(status.class_name, "VIP")
        self.assertEqual(status.bonus_points, 12345)
        self.assertEqual(status.freeleech_wedges, 617)

    def test_parse_account_status_marks_known_non_vip_inactive(self):
        client = MamClient(DeweySettings(mam_id="test-token"))

        status = client._parse_account_status({"user": {"class": "Power User"}})

        self.assertEqual(status.vip_status, "inactive")
        self.assertEqual(status.class_name, "Power User")

    def test_search_payload_drops_noisy_title_words(self):
        client = MamClient(DeweySettings(mam_id="test-token"))

        payload = client._search_payload(client._significant_query("The Way of Kings"), start=0, limit=100)

        self.assertEqual(payload["text"], "way kings")
        self.assertEqual(payload["tor"]["perpage"], 100)
        self.assertEqual(payload["tor"]["srchIn"], ["title", "author", "series", "narrator"])
        self.assertEqual(payload["tor"]["main_cat"], ["13"])
        self.assertEqual(payload["tor"]["searchType"], "all")
        self.assertIn("dlLink", payload)

    def test_search_payload_accepts_category_override(self):
        client = MamClient(DeweySettings(mam_id="test-token", mam_audiobook_category="13"))

        payload = client._search_payload("hobbit", start=0, limit=50, category_filter="14", search_type="fl")

        self.assertEqual(payload["tor"]["main_cat"], ["14"])
        self.assertEqual(payload["tor"]["searchType"], "fl")

    def test_normalize_uses_documented_times_completed(self):
        client = MamClient(DeweySettings(mam_id="test-token"))

        result = client._normalize({"id": 1, "title": "The Way of Kings", "times_completed": "321"})

        self.assertEqual(result.snatches, 321)

    def test_buy_vip_rejects_unsupported_duration_before_network(self):
        client = MamClient(DeweySettings(mam_id="test-token"))

        with self.assertRaisesRegex(RuntimeError, "VIP duration"):
            asyncio.run(client.buy_vip("3"))

    def test_relevance_rejects_common_word_matches(self):
        client = MamClient(DeweySettings(mam_id="test-token"))
        good = client._normalize({"id": 1, "title": "The Way of Kings", "filetype": "m4b"})
        bad = client._normalize({"id": 2, "title": "Written in the Stars", "filetype": "m4b"})

        self.assertGreaterEqual(client._relevance("The Way of Kings", good), 90)
        self.assertLess(client._relevance("The Way of Kings", bad), 45)

    def test_format_filter_matches_filetype(self):
        client = MamClient(DeweySettings(mam_id="test-token"))
        result = client._normalize({"id": 1, "title": "The Way of Kings", "filetype": "m4b"})

        self.assertTrue(client._format_matches(result, "m4b"))
        self.assertFalse(client._format_matches(result, "mp3"))

    def test_language_filter_accepts_english_aliases(self):
        client = MamClient(DeweySettings(mam_id="test-token"))
        result = client._normalize({"id": 1, "title": "The Way of Kings", "lang_code": "ENG"})

        self.assertTrue(client._language_matches(result, "english"))
        self.assertTrue(client._language_matches(result, "en"))
        self.assertFalse(client._language_matches(result, "fre"))

    def test_exact_title_sorts_above_related_title(self):
        client = MamClient(DeweySettings(mam_id="test-token"))
        exact = client._normalize({"id": 1, "title": "The Way of Kings", "seeders": 10})
        related = client._normalize(
            {
                "id": 2,
                "title": "The Stormlight Archive: A Pocket Companion to The Way of Kings",
                "seeders": 999,
            }
        )
        exact.relevance = client._relevance("The Way of Kings", exact)
        related.relevance = client._relevance("The Way of Kings", related)

        self.assertGreater(client._sort_key("The Way of Kings", exact), client._sort_key("The Way of Kings", related))


if __name__ == "__main__":
    unittest.main()
