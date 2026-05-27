import unittest

from app.utils import link_or_copy, parse_release_name, safe_path_component


class ReleaseParsingTests(unittest.TestCase):
    def test_series_pattern_keeps_book_title(self):
        parsed = parse_release_name("Ursula K Le Guin - Earthsea 01 - A Wizard of Earthsea")

        self.assertEqual(parsed.author, "Ursula K Le Guin")
        self.assertEqual(parsed.series, "Earthsea 01")
        self.assertEqual(parsed.title, "A Wizard of Earthsea")
        self.assertGreaterEqual(parsed.confidence, 80)

    def test_series_can_be_included_in_folder_title(self):
        parsed = parse_release_name(
            "Ursula K Le Guin - Earthsea 01 - A Wizard of Earthsea",
            include_series_in_title=True,
        )

        self.assertEqual(parsed.title, "Earthsea 01 - A Wizard of Earthsea")

    def test_author_title_pattern(self):
        parsed = parse_release_name("Terry Pratchett - Guards Guards")

        self.assertEqual(parsed.author, "Terry Pratchett")
        self.assertEqual(parsed.title, "Guards Guards")

    def test_by_author_pattern_ignores_narrator_noise(self):
        parsed = parse_release_name(
            "The Way of Kings by Brandon Sanderson (Narrated by Michael Kramer) [M4B]"
        )

        self.assertEqual(parsed.author, "Brandon Sanderson")
        self.assertEqual(parsed.title, "The Way of Kings")

    def test_quality_tokens_are_removed_before_parsing(self):
        parsed = parse_release_name(
            "Brandon Sanderson - Stormlight Archive 01 - The Way of Kings (Unabridged) [64 kbps]"
        )

        self.assertEqual(parsed.author, "Brandon Sanderson")
        self.assertEqual(parsed.series, "Stormlight Archive 01")
        self.assertEqual(parsed.title, "The Way of Kings")

    def test_safe_path_component_removes_forbidden_characters(self):
        self.assertEqual(safe_path_component('A:B/C*D?"'), "A B C D")

    def test_link_or_copy_copies_when_hardlink_fails(self):
        class NoHardlink:
            def __init__(self, test_case):
                self.test_case = test_case

            def __enter__(self):
                import app.utils

                self.original = app.utils.os.link
                app.utils.os.link = self.fail

            def __exit__(self, exc_type, exc, tb):
                import app.utils

                app.utils.os.link = self.original

            @staticmethod
            def fail(src, dst):
                raise OSError("hardlinks unavailable")

        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp, NoHardlink(self):
            root = Path(tmp)
            src = root / "source.mp3"
            dst = root / "library" / "source.mp3"
            src.write_bytes(b"audio")

            mode, imported = link_or_copy(src, dst)

        self.assertEqual(mode, "copy")
        self.assertEqual(imported.name, "source.mp3")


if __name__ == "__main__":
    unittest.main()
