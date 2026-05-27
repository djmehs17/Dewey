import time
import unittest

from app.auth import (
    generate_session_secret,
    hash_password,
    issue_session,
    prepare_auth_settings_payload,
    verify_password,
    verify_session,
)
from app.settings import DeweySettings


class AuthTests(unittest.TestCase):
    def test_password_hash_verifies_without_storing_plaintext(self):
        encoded = hash_password("correct horse battery staple")

        self.assertNotIn("correct horse", encoded)
        self.assertTrue(verify_password("correct horse battery staple", encoded))
        self.assertFalse(verify_password("wrong password", encoded))

    def test_session_requires_expected_user_and_secret(self):
        secret = generate_session_secret()
        token = issue_session("admin", secret, ttl_hours=1)

        self.assertTrue(verify_session(token, username="admin", secret=secret))
        self.assertFalse(verify_session(token, username="other", secret=secret))
        self.assertFalse(verify_session(token, username="admin", secret="wrong"))

    def test_expired_session_is_rejected(self):
        secret = generate_session_secret()
        expired = f"admin|{int(time.time()) - 1}|bad-signature"

        self.assertFalse(verify_session(expired, username="admin", secret=secret))

    def test_auth_enable_requires_password(self):
        with self.assertRaisesRegex(ValueError, "password"):
            prepare_auth_settings_payload({"auth_enabled": True}, DeweySettings())

    def test_auth_password_update_hashes_and_generates_secret(self):
        updates = prepare_auth_settings_payload(
            {
                "auth_enabled": True,
                "auth_password": "long enough password",
            },
            DeweySettings(),
        )

        self.assertTrue(updates["auth_password_hash"])
        self.assertTrue(updates["auth_session_secret"])
        self.assertNotIn("auth_password", updates)


if __name__ == "__main__":
    unittest.main()
