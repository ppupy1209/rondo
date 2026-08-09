"""Independent Rondo testing workflow tests."""
from __future__ import annotations

import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from rondo import testing  # noqa: E402
from rondo.gitcmd import git  # noqa: E402


class IndependentTestingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.cache = self.base / "cache"
        self.repo = self.base / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.name", "Test")
        git(self.repo, "config", "user.email", "test@example.com")
        (self.repo / "app.py").write_text("value = 1\n")
        git(self.repo, "add", "app.py")
        git(self.repo, "commit", "-qm", "initial")
        self.cache_patch = mock.patch.object(testing, "CACHE", self.cache)
        self.cache_patch.start()

    def tearDown(self) -> None:
        run = testing.load(self.repo)
        if run:
            testing.abort(run)
        self.cache_patch.stop()
        self.temp.cleanup()

    def test_all_is_four_independent_roles(self) -> None:
        self.assertEqual(testing.expand_profiles(["all"]), list(testing.ALL_PROFILES))
        with self.assertRaises(testing.TestError):
            testing.expand_profiles(["red", "blue", "load", "security", "review"])

    def test_same_vendor_still_gets_a_fresh_isolated_session(self) -> None:
        (self.repo / "app.py").write_text("value = 2\n")
        (self.repo / "new.py").write_text("created = True\n")
        before = git(self.repo, "diff", "--cached")

        run = testing.start(self.repo, ["red"], "codex", "implementation-session", ["codex"])
        role = run.roles["red"]

        self.assertNotEqual(role["session"], run.implementer_session)
        self.assertNotEqual(Path(role["worktree"]), self.repo)
        self.assertEqual(git(self.repo, "show", f"{run.base}:app.py"), "value = 2\n")
        self.assertEqual(git(self.repo, "show", f"{run.base}:new.py"), "created = True\n")
        self.assertEqual(git(self.repo, "diff", "--cached"), before)
        prompt = testing.role_prompt(run, "red")
        self.assertIn("Never resume or reuse", prompt)
        self.assertIn("implementation-session", prompt)
        self.assertIn("구현 대화를 재개하거나 재사용하지 마세요", testing.role_prompt(run, "red", "ko"))

    def test_finish_preserves_reports_and_flags_tester_source_edits(self) -> None:
        run = testing.start(self.repo, ["security"], "claude", "impl-1", ["codex"])
        role = run.roles["security"]
        report = Path(role["report"])
        report.parent.mkdir(parents=True)
        report.write_text(f"# PASS\n\n{testing.REPORT_COMPLETE}\n")
        worktree = Path(role["worktree"])
        (worktree / "app.py").write_text("value = 99\n")
        git(worktree, "add", "app.py")
        git(worktree, "commit", "-qm", "tester must not edit source")

        result = testing.finish(run)

        self.assertTrue(Path(result["summary"]).is_file())
        self.assertEqual(result["results"][0]["violations"], ["app.py"])
        self.assertTrue(testing.report_complete(result["results"][0]["report"]))
        self.assertTrue((Path(result["summary"]).parent / "security-violation.patch").is_file())
        self.assertIsNone(testing.load(self.repo))
        self.assertFalse(Path(role["worktree"]).exists())

    def test_load_target_is_local_by_default(self) -> None:
        self.assertTrue(testing.allowed_load_url("http://localhost:8080/api"))
        self.assertTrue(testing.allowed_load_url("https://app.localhost/test"))
        self.assertFalse(testing.allowed_load_url("https://example.com"))
        self.assertTrue(testing.allowed_load_url("https://example.com", allow_remote=True))
        self.assertFalse(testing.allowed_load_url("https://user:secret@example.com", allow_remote=True))
        self.assertFalse(testing.allowed_load_url("http://localhost:8080/\nmalicious"))

    def test_load_stack_contains_k6_prometheus_grafana_and_renderer(self) -> None:
        directory = self.base / "stack"
        directory.mkdir()
        testing._write_load_stack(directory, 13000)
        compose = (directory / "compose.yml").read_text()
        dashboard = (directory / "dashboards" / "rondo-k6.json").read_text()

        self.assertIn(testing.K6_IMAGE, compose)
        self.assertIn(testing.PROMETHEUS_IMAGE, compose)
        self.assertIn(testing.GRAFANA_IMAGE, compose)
        self.assertIn(testing.RENDERER_IMAGE, compose)
        self.assertNotIn(":latest", compose)
        self.assertIn('K6_NO_USAGE_REPORT: "true"', compose)
        self.assertIn('GF_ANALYTICS_REPORTING_ENABLED: "false"', compose)
        self.assertIn("--web.enable-remote-write-receiver", compose)
        self.assertIn("k6_http_req_duration_p95", dashboard)

    def test_generated_load_test_does_not_follow_redirects(self) -> None:
        self.assertIn("maxRedirects: 0", testing._generated_k6_script())

    def test_cleanup_failure_marks_load_test_failed(self) -> None:
        run = testing.start(self.repo, ["load"], "human", "declared-human", ["claude"])
        processes = [
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 1, "", "cleanup failed"),
        ]
        png = mock.MagicMock()
        png.__enter__.return_value.read.return_value = b"\x89PNG\r\n"
        with (
            mock.patch.object(testing.shutil, "which", return_value="/usr/bin/docker"),
            mock.patch.object(testing, "_wait_for_grafana"),
            mock.patch.object(testing.time, "sleep"),
            mock.patch.object(testing.urllib.request, "urlopen", return_value=png),
            mock.patch.object(testing.subprocess, "run", side_effect=processes),
        ):
            result = testing.run_load(run, "http://localhost:8080", None, duration="1s")

        self.assertEqual(result["status"], "failed")
        self.assertIn("cleanup failed", Path(result["log"]).read_text())

    def test_missing_docker_becomes_evidence(self) -> None:
        run = testing.start(self.repo, ["load"], "human", "declared-human", ["claude"])
        with mock.patch.object(testing.shutil, "which", return_value=None):
            result = testing.run_load(run, "http://localhost:8080", None, duration="1s")

        self.assertEqual(result["status"], "missing")
        self.assertEqual(testing.load(self.repo).load["status"], "missing")

    def test_custom_load_script_requires_explicit_target_consent(self) -> None:
        (self.repo / "load.js").write_text("export default function () {}\n")
        run = testing.start(self.repo, ["load"], "human", "declared-human", ["claude"])
        with (
            mock.patch.object(testing.shutil, "which", return_value=None),
            self.assertRaises(testing.TestError),
        ):
            testing.run_load(run, None, "load.js", duration="1s")

    def test_load_limits_prevent_accidental_runaway(self) -> None:
        with self.assertRaises(testing.TestError):
            testing.validate_load_options(1001, "30s")
        with self.assertRaises(testing.TestError):
            testing.validate_load_options(10, "2h")
        testing.validate_load_options(10, "60m")

    def test_partial_report_is_not_complete(self) -> None:
        report = self.base / "report.md"
        report.write_text("# Results\n\nPASS so far\n")
        self.assertFalse(testing.report_complete(report))
        report.write_text(f"# Results\n\n{testing.REPORT_COMPLETE}\n")
        self.assertTrue(testing.report_complete(report))


if __name__ == "__main__":
    unittest.main()
