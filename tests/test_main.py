import unittest

from app.main import (
    _is_supported_audio_result,
    _is_supported_ebook_result,
    _is_vip_result,
    _mam_account_refresh_interval_seconds,
)
from app.settings import DeweySettings


class MainHelperTests(unittest.TestCase):
    def test_import_guard_allows_audio_results(self):
        self.assertTrue(_is_supported_audio_result({"title": "The Way of Kings", "format": "m4b"}))

    def test_import_guard_rejects_ebook_results(self):
        self.assertFalse(_is_supported_audio_result({"title": "The Way of Kings", "format": "epub"}))

    def test_import_guard_prefers_explicit_format_over_category(self):
        self.assertFalse(
            _is_supported_audio_result(
                {"title": "The Way of Kings", "category": "Audiobook", "format": "epub"}
            )
        )

    def test_ebook_guard_allows_ebook_results(self):
        self.assertTrue(_is_supported_ebook_result({"title": "The Way of Kings", "format": "epub"}))

    def test_ebook_guard_rejects_audio_results(self):
        self.assertFalse(_is_supported_ebook_result({"title": "The Way of Kings", "format": "m4b"}))

    def test_ebook_guard_prefers_explicit_format_over_category(self):
        self.assertTrue(
            _is_supported_ebook_result(
                {"title": "The Way of Kings", "category": "Audiobooks", "format": "epub"}
            )
        )

    def test_vip_result_detects_explicit_field(self):
        self.assertTrue(_is_vip_result({"title": "The Way of Kings", "vip_only": True}))

    def test_vip_result_detects_flag(self):
        self.assertTrue(_is_vip_result({"title": "The Way of Kings", "flags": ["VIP"]}))

    def test_vip_result_ignores_non_vip_audio(self):
        self.assertFalse(_is_vip_result({"title": "The Way of Kings", "format": "m4b"}))

    def test_account_refresh_interval_defaults_to_eight_hours(self):
        self.assertEqual(_mam_account_refresh_interval_seconds(DeweySettings()), 8 * 60 * 60)

    def test_account_refresh_interval_has_one_hour_floor(self):
        self.assertEqual(
            _mam_account_refresh_interval_seconds(DeweySettings(mam_account_refresh_interval_hours=0)),
            60 * 60,
        )


if __name__ == "__main__":
    unittest.main()
