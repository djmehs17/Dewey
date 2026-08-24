import tempfile
import unittest
from pathlib import Path

from app.importer import ImportManager
from app.settings import DeweySettings
from app.utils import collect_ebook_files


class _FakeDb:
    def add_event(self, *args, **kwargs):
        pass

    def update_job(self, *args, **kwargs):
        pass


class EbookImportTests(unittest.TestCase):
    def _manager(self):
        return ImportManager(_FakeDb(), None)

    def test_collect_ebook_files_finds_supported_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "book.epub").write_bytes(b"epub")
            (root / "book.pdf").write_bytes(b"pdf")
            (root / "cover.jpg").write_bytes(b"junk")
            found = {path.name for path in collect_ebook_files(root)}
        self.assertEqual(found, {"book.epub", "book.pdf"})

    def test_ebook_author_title_parses_release_name(self):
        author, title = self._manager()._ebook_author_title(
            {"title": "Terry Pratchett - Guards Guards"}, {}
        )
        self.assertEqual(author, "Terry Pratchett")
        self.assertEqual(title, "Guards Guards")

    def test_ebook_folder_uses_author_and_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = DeweySettings(ebooks_dir=Path(tmp))
            folder = self._manager()._ebook_folder(settings, "Terry Pratchett", "Guards Guards")
        self.assertEqual(folder, Path(tmp) / "Terry Pratchett" / "Guards Guards")

    def test_ebook_folder_without_author_is_flat_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = DeweySettings(ebooks_dir=Path(tmp))
            folder = self._manager()._ebook_folder(settings, None, "Guards Guards")
        self.assertEqual(folder, Path(tmp) / "Guards Guards")

    def test_publish_subfolder_copies_files_into_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "download"
            source.mkdir()
            (source / "book.epub").write_bytes(b"epub-bytes")
            settings = DeweySettings(ebooks_dir=root / "ebooks")

            published = self._manager()._publish_ebook_subfolder(
                job_id=1,
                files=[source / "book.epub"],
                source_root=source,
                author="Terry Pratchett",
                title="Guards Guards",
                settings=settings,
            )

            self.assertEqual(published, settings.ebooks_dir / "Terry Pratchett" / "Guards Guards")
            self.assertTrue((published / "book.epub").exists())
            self.assertEqual((published / "book.epub").read_bytes(), b"epub-bytes")

    def test_publish_flat_drops_files_into_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "download"
            source.mkdir()
            (source / "book.epub").write_bytes(b"epub-bytes")
            settings = DeweySettings(ebooks_dir=root / "ebooks")

            published = self._manager()._publish_ebook_flat(
                job_id=1,
                files=[source / "book.epub"],
                settings=settings,
            )

            self.assertEqual(published, settings.ebooks_dir)
            self.assertTrue((settings.ebooks_dir / "book.epub").exists())


if __name__ == "__main__":
    unittest.main()
