import tempfile
import unittest
from pathlib import Path

from app.database import Database


class DatabaseImportHistoryTests(unittest.TestCase):
    def test_delete_job_removes_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "dewey.sqlite3")
            db.init()
            job_id = db.create_job(
                query="The Way of Kings",
                result={"title": "The Way of Kings", "download_url": "https://example.test/torrent"},
                category="dewey",
            )
            db.add_event(job_id, "error", "example failure")

            self.assertTrue(db.delete_job(job_id))
            self.assertIsNone(db.get_job_row(job_id))
            self.assertEqual(db.event_rows(job_id), [])

    def test_delete_jobs_by_status_keeps_active_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "dewey.sqlite3")
            db.init()
            error_id = db.create_job(
                query="Error",
                result={"title": "Error", "download_url": "https://example.test/error"},
                category="dewey",
            )
            queued_id = db.create_job(
                query="Queued",
                result={"title": "Queued", "download_url": "https://example.test/queued"},
                category="dewey",
            )
            db.update_job(error_id, status="error")

            deleted = db.delete_jobs_by_status({"error", "completed", "review"})

            self.assertEqual(deleted, 1)
            self.assertIsNone(db.get_job_row(error_id))
            self.assertIsNotNone(db.get_job_row(queued_id))


if __name__ == "__main__":
    unittest.main()
