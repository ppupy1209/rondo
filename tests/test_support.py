"""Support bundles expose only allowlisted diagnostics."""
from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from rondo import support


class SupportTest(unittest.TestCase):
    def test_bundle_excludes_repository_paths_and_raw_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "private-project-name"
            root.mkdir()
            value = support.report(
                version="0.12.0",
                root=root,
                branch="PRIVATE_BRANCH_MARKER",
                config={
                    "language": "PRIVATE_CONFIG_MARKER", "audience": "guided", "approval": "ask",
                    "panels": "claude codex", "relay": "ready",
                    "raw_prompt": "PRIVATE_PROMPT_MARKER",
                },
                agents={"claude": True, "codex": False},
                state={
                    "changed": 2, "knowledge_pending": 1, "jobs_pending": 0,
                    "jobs_active": 1, "test": {"complete": 1, "total": 2},
                    "race": {"agents": 0}, "proof": {"verdict": "review"},
                    "next": "knowledge", "goal": "PRIVATE_TASK_MARKER",
                },
                installation={"managed": True, "version": "0.12.0"},
            )
            target = support.create(base / "support", value)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            with zipfile.ZipFile(target) as archive:
                self.assertEqual(sorted(archive.namelist()), ["README.txt", "report.json"])
                raw = archive.read("report.json").decode()
                report = json.loads(raw)
            self.assertNotIn(str(root), raw)
            self.assertNotIn("private-project-name", raw)
            self.assertNotIn("PRIVATE_PROMPT_MARKER", raw)
            self.assertNotIn("PRIVATE_TASK_MARKER", raw)
            self.assertNotIn("PRIVATE_BRANCH_MARKER", raw)
            self.assertNotIn("PRIVATE_CONFIG_MARKER", raw)
            self.assertEqual(report["repository"]["changed"], 2)
            self.assertEqual(report["repository"]["branch_kind"], "other")
            self.assertEqual(report["configuration"]["language"], "invalid")

    def test_existing_or_linked_destination_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "support.zip"
            target.write_text("keep")
            with self.assertRaisesRegex(support.SupportError, "destination_unsafe"):
                support.create(target, {})
            self.assertEqual(target.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
