from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_identity", ROOT / "scripts" / "check_identity.py"
)
assert SPEC and SPEC.loader
identity_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(identity_check)


class IdentityPolicyTests(unittest.TestCase):
    def test_history_accepts_canonical_and_legacy_names(self):
        history = "\n".join(
            (
                "a" * 40 + "\x1fyeonwoo\x1fppupy1209@naver.com\x1fyeonwoo\x1fppupy1209@naver.com",
                "b" * 40 + "\x1fYeonwoo Kim\x1fppupy1209@naver.com\x1fYeonwoo Kim\x1fppupy1209@naver.com",
            )
        )

        with mock.patch.object(identity_check, "git", side_effect=(history, "")):
            self.assertEqual(identity_check.history_errors(), [])

    def test_history_rejects_another_name(self):
        history = (
            "a" * 40
            + "\x1fAnother User\x1fppupy1209@naver.com"
            + "\x1fyeonwoo\x1fppupy1209@naver.com"
        )

        with mock.patch.object(identity_check, "git", side_effect=(history, "")):
            errors = identity_check.history_errors()

        self.assertEqual(len(errors), 1)
        self.assertIn("Another User", errors[0])

    def test_current_identity_requires_canonical_local_name(self):
        values = (
            "yeonwoo <ppupy1209@naver.com> 0 +0000",
            "yeonwoo <ppupy1209@naver.com> 0 +0000",
            "Yeonwoo Kim",
            "ppupy1209@naver.com",
        )

        with mock.patch.object(identity_check, "git", side_effect=values):
            errors = identity_check.current_errors()

        self.assertEqual(errors, ["repository user.name: Yeonwoo Kim"])


if __name__ == "__main__":
    unittest.main()
