import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from app.settings import DEFAULT_SEARCH_PROFILES, DeweySettings, SettingsManager


class SettingsTests(unittest.TestCase):
    def test_default_search_profiles_are_public_settings(self):
        settings = DeweySettings()

        self.assertEqual(settings.search_profiles, DEFAULT_SEARCH_PROFILES)
        self.assertIn("search_profiles", settings.public_dict())

    def test_public_settings_mask_secrets_but_report_configured_status(self):
        settings = DeweySettings(mam_id="secret", qbittorrent_password="password")

        public = settings.public_dict()

        self.assertEqual(public["mam_id"], "")
        self.assertTrue(public["mam_id_configured"])
        self.assertEqual(public["qbittorrent_password"], "")
        self.assertTrue(public["qbittorrent_password_configured"])
        self.assertFalse(public["audiobookshelf_api_key_configured"])

    def test_search_profiles_round_trip_through_saved_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"DEWEY_CONFIG_DIR": tmp}):
                manager = SettingsManager()
                manager._settings = DeweySettings(config_dir=Path(tmp))

                saved = manager.save(
                    {
                        "search_profiles": [
                            {
                                "id": "custom",
                                "name": "Custom M4B",
                                "format": "m4b",
                                "language": "ENG",
                                "min_seeders": 2,
                                "min_relevance": 60,
                                "search_type": "active",
                                "category": "13",
                            }
                        ]
                    }
                )

                self.assertEqual(saved.search_profiles[0]["name"], "Custom M4B")
                loaded = manager.load()
                self.assertEqual(loaded.search_profiles, saved.search_profiles)


if __name__ == "__main__":
    unittest.main()
