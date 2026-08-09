"""Rondo Proof 계약 테스트."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from rondo import proof as proof_mod  # noqa: E402
from rondo.gitcmd import git  # noqa: E402


class ProofTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.cache = base / "cache"
        mock.patch.object(proof_mod, "CACHE", self.cache).start()
        self.repo = base / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "t@t")
        git(self.repo, "config", "user.name", "t")
        (self.repo / "README.md").write_text("hello\n", encoding="utf-8")
        tests = self.repo / "tests"
        tests.mkdir()
        (tests / "test_smoke.py").write_text(
            "import unittest\n\nclass Smoke(unittest.TestCase):\n"
            "    def test_ok(self): self.assertTrue(True)\n",
            encoding="utf-8",
        )
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "first")

    def tearDown(self) -> None:
        mock.patch.stopall()
        self.tmp.cleanup()

    def task(self, **values) -> dict:
        return proof_mod.record_task(
            self.repo,
            values.get("goal", "문서 정리"),
            acceptance=values.get("acceptance", ["문서가 읽기 쉽다"]),
            must_not=values.get("must_not", []),
            scope=values.get("scope", []),
            checks=values.get("checks", []),
        )

    def test_task_round_trips_privately(self) -> None:
        self.task(must_not=["API 변경 금지"])
        loaded = proof_mod.load_task(self.repo)
        self.assertEqual(loaded["goal"], "문서 정리")
        self.assertEqual(loaded["must_not"], ["API 변경 금지"])
        if os.name != "nt":
            self.assertEqual(proof_mod.task_path(self.repo).stat().st_mode & 0o777, 0o600)

    def test_risk_uses_scope_and_sensitive_paths(self) -> None:
        self.assertEqual(proof_mod.risk_for("docs/guide.md")["level"], "low")
        self.assertEqual(proof_mod.risk_for("src/auth/session.py")["level"], "high")
        self.assertEqual(proof_mod.risk_for("src/oauth/token.py")["level"], "high")
        self.assertEqual(proof_mod.risk_for("Web/page.tsx", ["web"])["level"], "medium")
        drift = proof_mod.risk_for("backend/app.py", ["web"])
        self.assertEqual((drift["level"], drift["reason"]), ("high", "scope_drift"))
        sensitive_drift = proof_mod.risk_for("migrations/001.sql", ["web"], 12)
        self.assertEqual(
            sensitive_drift["reasons"], ["scope_drift", "sensitive_path"]
        )
        self.assertEqual(sensitive_drift["lines"], 12)

    def test_generated_artifacts_are_never_review_targets(self) -> None:
        (self.repo / "src" / "__pycache__").mkdir(parents=True)
        (self.repo / "src" / "__pycache__" / "app.pyc").write_bytes(b"binary")
        (self.repo / "dist").mkdir()
        (self.repo / "dist" / "bundle.js").write_text("generated\n")
        (self.repo / "src" / "app.py").write_text("print('real')\n")

        self.assertEqual(proof_mod.changed_files(self.repo), ["src/app.py"])

    def test_no_changes_is_not_an_approval_candidate(self) -> None:
        self.task()
        proof = proof_mod.build(self.repo)
        self.assertEqual(proof["summary"]["verdict"], "empty")
        self.assertEqual(proof["summary"]["passed"], 0)
        self.assertEqual(proof["human"], [])

    def test_low_risk_change_with_passing_check_is_ready(self) -> None:
        self.task()
        (self.repo / "README.md").write_text("clearer\n", encoding="utf-8")
        proof = proof_mod.build(self.repo)
        self.assertEqual(proof["summary"]["verdict"], "ready")
        self.assertEqual(proof["summary"]["passed"], 1)
        self.assertTrue(Path(proof["packet"]).is_file())

    def test_sensitive_change_requires_human_review(self) -> None:
        self.task()
        target = self.repo / "src" / "auth"
        target.mkdir(parents=True)
        (target / "session.py").write_text("secure = True\n", encoding="utf-8")
        proof = proof_mod.build(self.repo, run_checks=False)
        self.assertEqual(proof["summary"]["verdict"], "review")
        self.assertTrue(any(item.get("label") == "src/auth/session.py" for item in proof["human"]))

    def test_failed_check_is_evidence_not_a_crash(self) -> None:
        self.task(checks=[[sys.executable, "-c", "raise SystemExit(2)"]])
        (self.repo / "README.md").write_text("changed\n", encoding="utf-8")
        proof = proof_mod.build(self.repo)
        self.assertEqual(proof["summary"]["failed"], 1)
        self.assertTrue(any("Check failed" in item["label"] for item in proof["human"]))

    def test_review_budget_prioritizes_high_risk(self) -> None:
        proof = {
            "human": [
                {"level": "medium", "label": "code", "seconds": 40},
                {"level": "high", "label": "auth", "seconds": 90},
                {"level": "low", "label": "docs", "seconds": 10},
            ]
        }
        selected, deferred = proof_mod.review_queue(proof, 100)
        self.assertEqual([item["label"] for item in selected], ["auth", "docs"])
        self.assertEqual([item["label"] for item in deferred], ["code"])

    def test_review_time_grows_with_changed_lines(self) -> None:
        small = proof_mod.risk_for("src/app.py", lines=1)
        large = proof_mod.risk_for("src/large.py", lines=100)
        self.assertLess(small["seconds"], large["seconds"])

    def test_budget_parser(self) -> None:
        self.assertEqual(proof_mod.parse_budget("2m"), 120)
        self.assertEqual(proof_mod.parse_budget("45s"), 45)
        with self.assertRaises(ValueError):
            proof_mod.parse_budget("0")


if __name__ == "__main__":
    unittest.main()
