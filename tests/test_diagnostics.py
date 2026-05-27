import tempfile
import unittest
from pathlib import Path

from app.database import Database
from app.diagnostics import OK, SKIPPED, _database_check, _path_check, run_diagnostics
from app.settings import DeweySettings


class DiagnosticsTests(unittest.TestCase):
    def test_path_check_reports_writable_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            check = _path_check("tmp", "Temp", Path(tmp))

        self.assertEqual(check.status, OK)

    def test_database_check_opens_sqlite_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "dewey.sqlite3")
            db.init()

            check = _database_check(db)

        self.assertEqual(check.status, OK)

    def test_run_diagnostics_skips_disabled_audiobookshelf(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = DeweySettings(
                mam_id="",
                qbittorrent_url="",
                audiobooks_dir=root / "Audiobooks",
                torrents_dir=root / "Torrents",
                audiobookshelf_scan_enabled=False,
            )
            settings.audiobooks_dir.mkdir()
            settings.torrents_dir.mkdir()
            db = Database(root / "dewey.sqlite3")
            db.init()

            response = self.run_async(run_diagnostics(settings, db))

        abs_check = next(check for check in response.checks if check.id == "audiobookshelf")
        self.assertEqual(abs_check.status, SKIPPED)
        self.assertIn(response.overall_status, {"warn", "error"})

    @staticmethod
    def run_async(awaitable):
        import asyncio

        return asyncio.run(awaitable)


if __name__ == "__main__":
    unittest.main()
