"""Managed release lifecycle tests without network access."""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from rondo import release  # noqa: E402


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class ReleaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "app"
        (self.root / "bin").mkdir(parents=True)
        (self.root / "bin" / "rondo").write_text("rondo")
        self.marker(self.root, "0.11.0")

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def marker(root: Path, version: str) -> None:
        root.mkdir(parents=True, exist_ok=True)
        (root / release.MARKER).write_text(json.dumps({
            "schema": 1, "version": version, "source": "release",
        }))

    def test_latest_release_and_versions_are_strict(self) -> None:
        opener = lambda *_args, **_kwargs: Response(b'{"tag_name":"v0.12.0"}')
        self.assertEqual(release.latest_version(opener), "0.12.0")
        self.assertGreater(release.version_tuple("0.12.0"), release.version_tuple("0.11.9"))
        with self.assertRaises(release.ReleaseError):
            release.normalize_version("main")

    def test_command_center_check_is_cached_and_throttled(self) -> None:
        cache = self.base / "release-check.json"
        opener = mock.Mock(return_value=Response(b'{"tag_name":"v0.12.1"}'))
        first = release.version_status(cache, "0.12.0", opener=opener, now=100)
        second = release.version_status(
            cache,
            "0.12.0",
            opener=mock.Mock(side_effect=AssertionError("cache was ignored")),
            now=101,
        )

        self.assertTrue(first["available"])
        self.assertEqual(first, second)
        opener.assert_called_once()

    def test_failed_check_stays_quiet_until_retry_window(self) -> None:
        cache = self.base / "release-check.json"
        offline = mock.Mock(side_effect=OSError("offline"))
        first = release.version_status(cache, "0.12.0", opener=offline, now=100)
        second = release.version_status(
            cache,
            "0.12.0",
            opener=mock.Mock(side_effect=AssertionError("retried too soon")),
            now=101,
        )

        self.assertEqual(first["latest"], "")
        self.assertEqual(first, second)
        offline.assert_called_once()

    def test_update_runs_the_trusted_installer_and_verifies_result(self) -> None:
        def runner(command, check, env):
            self.assertTrue(check)
            self.assertEqual(env["RONDO_VERSION"], "0.12.0")
            self.assertEqual(env["RONDO_FORCE_REMOTE"], "1")
            self.marker(self.root, "0.12.0")
            return mock.Mock(returncode=0)

        installed = release.update(self.root, "0.12.0", runner=runner)
        self.assertEqual(installed, "0.12.0")
        with self.assertRaisesRegex(release.ReleaseError, "use_rollback"):
            release.update(self.root, "0.11.0", runner=runner)

    def test_rollback_atomically_keeps_the_replaced_release(self) -> None:
        previous = self.base / "app.previous"
        (previous / "bin").mkdir(parents=True)
        (previous / "bin" / "rondo").write_text("old")
        self.marker(previous, "0.10.0")

        current, restored = release.rollback(self.root)
        self.assertEqual((current, restored), ("0.11.0", "0.10.0"))
        self.assertEqual(release.metadata(self.root)["version"], "0.10.0")
        self.assertEqual(release.metadata(previous)["version"], "0.11.0")

    @unittest.skipIf(os.name == "nt", "Unix launcher links are tested here")
    def test_uninstall_removes_owned_files_but_preserves_data_by_default(self) -> None:
        binary = self.base / "bin"
        binary.mkdir()
        owned = binary / "rondo"
        owned.symlink_to(self.root / "bin" / "rondo")
        unrelated = binary / "other"
        unrelated.write_text("keep")
        config = self.base / "config" / "rondo"
        cache = self.base / "cache" / "rondo"
        config.mkdir(parents=True)
        cache.mkdir(parents=True)
        (config / "language").write_text("ko")

        settings = self.base / "settings.json"
        settings.write_text(json.dumps({
            "hooks": {
                "SessionEnd": [{"hooks": [
                    {"type": "command", "command": "handoff Claude"},
                    {"type": "command", "command": "handoff Custom"},
                    {"type": "command", "command": "keep-me"},
                ]}],
                "UserPromptSubmit": [{"hooks": [
                    {"type": "command", "command": "rondo snap --auto"},
                ]}],
            },
            "statusLine": {"type": "command", "command": "rondo-claude-status"},
        }))

        result = release.uninstall(
            self.root, binary, [settings], config, cache, purge=False
        )
        self.assertEqual(result["version"], "0.11.0")
        self.assertFalse(self.root.exists())
        self.assertFalse(owned.exists())
        self.assertTrue(unrelated.exists())
        self.assertTrue(config.exists())
        self.assertTrue(cache.exists())
        value = json.loads(settings.read_text())
        kept = [item["command"] for item in value["hooks"]["SessionEnd"][0]["hooks"]]
        self.assertEqual(kept, ["handoff Custom", "keep-me"])
        self.assertNotIn("UserPromptSubmit", value["hooks"])
        self.assertNotIn("statusLine", value)

    def test_source_checkout_cannot_be_updated_or_deleted(self) -> None:
        (self.root / release.MARKER).unlink()
        with self.assertRaisesRegex(release.ReleaseError, "unmanaged"):
            release.metadata(self.root)

    def test_purge_symlink_is_rejected_before_any_removal(self) -> None:
        binary = self.base / "bin"
        binary.mkdir()
        config = self.base / "config"
        outside = self.base / "outside"
        outside.mkdir()
        config.symlink_to(outside, target_is_directory=True)

        with self.assertRaisesRegex(release.ReleaseError, "state_unsafe"):
            release.uninstall(
                self.root, binary, [], config, self.base / "cache", purge=True
            )
        self.assertTrue(self.root.exists())
        self.assertTrue((self.root / release.MARKER).exists())


if __name__ == "__main__":
    unittest.main()
