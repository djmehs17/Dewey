import tempfile
import unittest
from pathlib import Path

from app.library import find_library_matches, move_review_import, review_destination
from app.models import SearchResult
from app.settings import DeweySettings


class LibraryHelperTests(unittest.TestCase):
    def test_find_library_matches_spots_existing_author_title_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Audiobooks"
            existing = root / "Brandon Sanderson" / "The Way of Kings"
            existing.mkdir(parents=True)
            settings = DeweySettings(audiobooks_dir=root)
            result = SearchResult(
                id="1",
                title="Brandon Sanderson - The Stormlight Archive 01 - The Way of Kings",
                author="Brandon Sanderson",
            )

            matches = find_library_matches(result, settings)

        self.assertEqual(matches, [str(existing)])

    def test_find_library_matches_ignores_unsorted_review_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Audiobooks"
            (root / "_unsorted" / "The Way of Kings").mkdir(parents=True)
            settings = DeweySettings(audiobooks_dir=root)
            result = SearchResult(id="1", title="The Way of Kings", author="Brandon Sanderson")

            matches = find_library_matches(result, settings)

        self.assertEqual(matches, [])

    def test_move_review_import_moves_within_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Audiobooks"
            current = root / "_unsorted" / "Way of Kings"
            current.mkdir(parents=True)
            (current / "book.m4b").write_bytes(b"audio")
            settings = DeweySettings(audiobooks_dir=root)

            destination = review_destination(settings, "Brandon Sanderson", "The Way of Kings")
            moved = move_review_import(current, destination, settings)

            self.assertEqual(moved, destination)
            self.assertTrue((destination / "book.m4b").exists())
            self.assertFalse(current.exists())


if __name__ == "__main__":
    unittest.main()
