"""어댑터 계약 테스트.

벤더 CLI 없이도 도는 픽스처 테스트다. 노리는 것은 '조용한 고장'이다 —
스키마가 바뀌었을 때 빈 값이 아니라 이유가 나와야 한다.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from rondo import registry  # noqa: E402
from rondo.adapters import codex  # noqa: E402
from rondo.model import Window  # noqa: E402


def make_state_db(path: Path, rows: list[tuple]) -> None:
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE threads (cwd TEXT, thread_source TEXT, model TEXT, "
        "reasoning_effort TEXT, updated_at_ms INTEGER)"
    )
    con.executemany("INSERT INTO threads VALUES (?,?,?,?,?)", rows)
    con.commit()
    con.close()


def make_rollout(directory: Path, payload: dict | None) -> Path:
    day = directory / "2026" / "08" / "09"
    day.mkdir(parents=True, exist_ok=True)
    path = day / "rollout-2026-08-09T00-00-00-test.jsonl"
    lines = [json.dumps({"type": "session_meta", "payload": {"cwd": "/tmp/x"}})]
    if payload is not None:
        lines.append(json.dumps({"type": "event", "payload": {"rate_limits": payload}}))
    path.write_text("\n".join(lines) + "\n")
    return path


class CodexModelTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.other = self.root / "other"
        self.db = self.root / "state.sqlite"
        make_state_db(
            self.db,
            [
                (str(self.repo), "user", "gpt-5.6-sol", "xhigh", 200),
                # 더 최근이지만 서브에이전트 행이다. 골라지면 안 된다.
                (str(self.repo), "subagent", "codex-auto-review", None, 300),
                (str(self.other), "user", "gpt-other", None, 400),
            ],
        )
        self.patch = mock.patch.object(codex, "STATE_DB", self.db)
        self.patch.start()

    def tearDown(self) -> None:
        self.patch.stop()
        self.tmp.cleanup()

    def test_subagent_rows_excluded(self) -> None:
        with mock.patch.object(codex, "read_limits", return_value=([], None)):
            snap = codex.CodexAdapter().snapshot(self.repo)
        self.assertEqual(snap.model, "gpt-5.6-sol xhigh")

    def test_other_repo_not_used(self) -> None:
        with mock.patch.object(codex, "read_limits", return_value=([], None)):
            snap = codex.CodexAdapter().snapshot(self.root / "repo-없음")
        self.assertIsNone(snap.model)


class CodexLimitsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.sessions = Path(self.tmp.name)
        self.patch = mock.patch.object(codex, "SESSIONS", self.sessions)
        self.patch.start()

    def tearDown(self) -> None:
        self.patch.stop()
        self.tmp.cleanup()

    def test_used_percent_becomes_remaining(self) -> None:
        reset = time.time() + 3600
        make_rollout(
            self.sessions,
            {"primary": {"used_percent": 7.0, "window_minutes": 10080, "resets_at": reset},
             "secondary": {"used_percent": 40.0, "window_minutes": 300, "resets_at": reset}},
        )
        windows, error = codex.read_limits()
        self.assertIsNone(error)
        # 짧은 창이 앞에 온다
        self.assertEqual([w.label for w in windows], ["5h", "wk"])
        self.assertAlmostEqual(windows[0].remaining, 60.0)
        self.assertAlmostEqual(windows[1].remaining, 93.0)

    def test_missing_secondary_is_not_an_error(self) -> None:
        make_rollout(
            self.sessions,
            {"primary": {"used_percent": 1.0, "window_minutes": 10080,
                         "resets_at": time.time() + 60},
             "secondary": None},
        )
        windows, error = codex.read_limits()
        self.assertIsNone(error)
        self.assertEqual([w.label for w in windows], ["wk"])

    def test_schema_change_is_reported_not_silent(self) -> None:
        make_rollout(self.sessions, None)  # rate_limits 키 자체가 없는 로그
        windows, error = codex.read_limits()
        self.assertEqual(windows, [])
        self.assertIn("스키마 변경", error)

    def test_renamed_fields_are_reported(self) -> None:
        make_rollout(
            self.sessions,
            {"primary": {"consumed_percent": 7.0, "window_minutes": 10080,
                         "resets_at": time.time() + 60}},
        )
        _, error = codex.read_limits()
        self.assertIn("스키마 변경", error)

    def test_no_rollout_at_all(self) -> None:
        windows, error = codex.read_limits()
        self.assertEqual(windows, [])
        self.assertIn("없음", error)


class WindowTest(unittest.TestCase):
    def test_expired_window_filtered(self) -> None:
        from rondo.model import Snapshot

        snap = Snapshot(
            agent="codex",
            windows=[
                Window("5h", 50.0, time.time() - 1),
                Window("wk", 90.0, time.time() + 60),
            ],
        )
        self.assertEqual([w.label for w in snap.live_windows()], ["wk"])


class FingerprintTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(
            registry, "FINGERPRINT", Path(self.tmp.name) / "adapters.json"
        )
        self.patch.start()
        mock.patch.object(registry, "CACHE", Path(self.tmp.name)).start()

    def tearDown(self) -> None:
        mock.patch.stopall()
        self.tmp.cleanup()

    def _adapter(self, version: str, limits_ok: bool):
        from rondo.model import Check

        adapter = codex.CodexAdapter()
        adapter.version = lambda: version  # type: ignore[method-assign]
        adapter.diagnose = lambda root: [  # type: ignore[method-assign]
            Check("model", True, "threads.model"),
            Check("limits", limits_ok, "rollout rate_limits" if limits_ok else "스키마 변경 가능"),
        ]
        return adapter

    def test_first_run_is_quiet(self) -> None:
        warnings = registry.check_fingerprint(self._adapter("0.147.0", True), Path("/repo"))
        self.assertEqual(warnings, [])

    def test_upgrade_that_breaks_a_capability_warns(self) -> None:
        registry.check_fingerprint(self._adapter("0.147.0", True), Path("/repo"))
        warnings = registry.check_fingerprint(self._adapter("0.150.0", False), Path("/repo"))
        self.assertEqual(len(warnings), 1)
        self.assertIn("limits", warnings[0])
        self.assertIn("0.150.0", warnings[0])

    def test_capability_removed_entirely_does_not_crash(self) -> None:
        """지문에만 있고 지금은 존재하지 않는 capability 여도 진단은 살아 있어야 한다."""
        registry.check_fingerprint(self._adapter("0.147.0", True), Path("/repo"))
        store = json.loads(registry.FINGERPRINT.read_text())
        store["codex"]["ok"].append("transcript")
        registry.FINGERPRINT.write_text(json.dumps(store))
        warnings = registry.check_fingerprint(self._adapter("0.150.0", True), Path("/repo"))
        self.assertEqual(len(warnings), 1)
        self.assertIn("transcript", warnings[0])

    def test_upgrade_that_keeps_working_is_quiet(self) -> None:
        registry.check_fingerprint(self._adapter("0.147.0", True), Path("/repo"))
        warnings = registry.check_fingerprint(self._adapter("0.150.0", True), Path("/repo"))
        self.assertEqual(warnings, [])



class ClaudeAdapterTest(unittest.TestCase):
    """Claude 는 파일을 뒤지지 않고 statusLine payload 가 유일한 입구다."""

    def setUp(self) -> None:
        from rondo.adapters import claude

        self.claude = claude
        self.tmp = tempfile.TemporaryDirectory()
        cache = Path(self.tmp.name)
        self.repo = cache / "repo"
        self.other = cache / "other"
        mock.patch.object(claude, "CACHE", cache).start()
        mock.patch.object(claude, "LIMITS", cache / "claude-limits.json").start()

    def tearDown(self) -> None:
        mock.patch.stopall()
        self.tmp.cleanup()

    def payload(self, **overrides) -> dict:
        reset = time.time() + 3600
        data = {
            "model": {"display_name": "Opus 5"},
            "effort": {"level": "high"},
            "workspace": {"project_dir": str(self.repo)},
            "rate_limits": {
                "five_hour": {"used_percentage": 72, "resets_at": reset},
                "seven_day": {"used_percentage": 36, "resets_at": reset},
            },
        }
        data.update(overrides)
        return data

    def test_used_percentage_becomes_remaining(self) -> None:
        windows = self.claude.windows_from_payload(self.payload())
        self.assertEqual([(w.label, w.remaining) for w in windows], [("5h", 28.0), ("wk", 64.0)])

    def test_expired_window_dropped(self) -> None:
        payload = self.payload()
        payload["rate_limits"]["five_hour"]["resets_at"] = time.time() - 1
        self.assertEqual([w.label for w in self.claude.windows_from_payload(payload)], ["wk"])

    def test_tightest_window_drives_relay(self) -> None:
        tightest = self.claude.tightest(self.claude.windows_from_payload(self.payload()))
        self.assertEqual(tightest.label, "5h")

    def test_model_includes_effort(self) -> None:
        self.assertEqual(self.claude.model_from_payload(self.payload()), "Opus 5 high")

    def test_limits_are_account_wide_not_per_repo(self) -> None:
        # /repo 에서 한도를 받고, 아직 메시지를 안 보낸 /other 에서도 보여야 한다
        self.claude.write_cache(self.payload())
        self.claude.write_cache(
            self.payload(workspace={"project_dir": str(self.other)}, rate_limits={})
        )
        windows, age = self.claude.cached_limits()
        self.assertEqual([w.label for w in windows], ["5h", "wk"])
        self.assertLess(age, 5)

    def test_empty_limits_do_not_erase_cached_ones(self) -> None:
        self.claude.write_cache(self.payload())
        self.claude.write_cache(self.payload(rate_limits={}))
        windows, _ = self.claude.cached_limits()
        self.assertEqual(len(windows), 2)

    def test_model_is_scoped_to_its_repo(self) -> None:
        self.claude.write_cache(self.payload())
        adapter = self.claude.ClaudeAdapter()
        self.assertEqual(adapter.snapshot(self.repo).model, "Opus 5 high")
        self.assertIsNone(adapter.snapshot(self.other).model)

    def test_stale_model_is_dropped_but_limits_stay(self) -> None:
        self.claude.write_cache(self.payload())
        path = self.claude.CACHE / f"claude.{self.claude.repo_key(self.repo)}.json"
        data = json.loads(path.read_text())
        data["at"] = time.time() - self.claude.STALE_MODEL - 10
        path.write_text(json.dumps(data))
        snap = self.claude.ClaudeAdapter().snapshot(self.repo)
        self.assertIsNone(snap.model)
        self.assertEqual(len(snap.live_windows()), 2)

    def test_missing_cache_explains_itself(self) -> None:
        snap = self.claude.ClaudeAdapter().snapshot(self.repo)
        self.assertIsNone(snap.model)
        self.assertIn("Claude 패널", snap.error)


class DeepProbeTest(unittest.TestCase):
    """`rondo doctor --deep` 이 어댑터 결과와 지문 경고를 사람 말로 내놓는지."""

    def setUp(self) -> None:
        import runpy

        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        env = {
            "XDG_CONFIG_HOME": str(base / "config"),
            "XDG_CACHE_HOME": str(base / "cache"),
            "LANG": "en_US.UTF-8",
        }
        with mock.patch.dict("os.environ", env, clear=False):
            self.rondo = runpy.run_path(
                str(Path(__file__).resolve().parent.parent / "bin" / "rondo")
            )

    def tearDown(self) -> None:
        mock.patch.stopall()
        self.tmp.cleanup()

    def _fake_adapter(self, name: str, ok: bool):
        from rondo.model import Check

        adapter = mock.Mock()
        adapter.name = name
        adapter.installed.return_value = True
        adapter.version.return_value = "9.9.9"
        adapter.diagnose.return_value = [Check("limits", ok, "rollout rate_limits" if ok else "스키마 변경 가능")]
        return adapter

    def _run(self, adapters, warnings):
        registry_stub = mock.Mock()
        registry_stub.all_adapters.return_value = adapters
        registry_stub.check_fingerprint.return_value = warnings
        module = mock.Mock(registry=registry_stub)
        with mock.patch.dict(sys.modules, {"rondo": module, "rondo.registry": registry_stub}):
            with mock.patch("builtins.print") as printed:
                broken = self.rondo["deep_probe"]()
        return broken, "\n".join(str(c.args[0]) for c in printed.call_args_list if c.args)

    def test_healthy_probe_reports_no_break(self) -> None:
        broken, output = self._run([self._fake_adapter("codex", True)], [])
        self.assertFalse(broken)
        self.assertIn("codex 9.9.9", output)
        self.assertIn("✓ limits", output)

    def test_broken_capability_is_visible(self) -> None:
        _, output = self._run([self._fake_adapter("codex", False)], [])
        self.assertIn("✗ limits", output)
        self.assertIn("스키마 변경", output)

    def test_vendor_upgrade_regression_fails_doctor(self) -> None:
        broken, output = self._run(
            [self._fake_adapter("codex", False)],
            ["codex 0.147.0 → 0.150.0: 'limits' 를 더 못 읽습니다"],
        )
        self.assertTrue(broken)          # doctor 종료 코드가 0 이 아니게 된다
        self.assertIn("0.150.0", output)

    def test_uninstalled_agents_are_skipped(self) -> None:
        adapter = self._fake_adapter("kimi", True)
        adapter.installed.return_value = False
        _, output = self._run([adapter], [])
        self.assertNotIn("kimi", output)


class GeminiAdapterTest(unittest.TestCase):
    """모델은 대화 DB 문자열, 한도는 `agy -p /usage` 캐시."""

    def setUp(self) -> None:
        from rondo.adapters import gemini

        self.gemini = gemini
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        (base / "conversations").mkdir()
        mock.patch.object(gemini, "CONVERSATIONS", base / "conversations").start()
        mock.patch.object(gemini, "USAGE_CACHE", base / "gemini-usage.json").start()

    def tearDown(self) -> None:
        mock.patch.stopall()
        self.tmp.cleanup()

    USAGE = (
        "Gemini Models\tWeekly Limit Remaining\t99%\t2036-08-10T06:07:01Z\n"
        "Gemini Models\tFive Hour Limit Remaining\t100%\t2036-08-09T06:06:04Z\n"
        "Claude and GPT models\tWeekly Limit Remaining\t42%\t2036-08-16T01:34:50Z\n"
    )

    def test_remaining_is_not_flipped(self) -> None:
        windows = self.gemini.parse_usage(self.USAGE)
        self.assertEqual(windows["wk"]["remaining"], 99.0)
        self.assertEqual(windows["5h"]["remaining"], 100.0)

    def test_other_model_families_ignored(self) -> None:
        self.assertEqual(set(self.gemini.parse_usage(self.USAGE)), {"wk", "5h"})

    def test_reset_time_is_utc(self) -> None:
        windows = self.gemini.parse_usage(self.USAGE)
        self.assertEqual(
            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(windows["wk"]["resets_at"])),
            "2036-08-10T06:07:01Z",
        )

    def test_garbage_output_yields_nothing(self) -> None:
        self.assertEqual(self.gemini.parse_usage("agy: command failed\n"), {})

    def test_old_cache_format_still_readable(self) -> None:
        # 예전 캐시는 used_percentage 로 저장했다. 10분 기다리지 않고 바로 읽힌다.
        self.gemini.USAGE_CACHE.write_text(json.dumps({
            "windows": {"wk": {"used_percentage": 1.0, "resets_at": time.time() + 600}},
            "at": time.time(),
        }))
        windows = self.gemini.cached_usage(refresh=False)
        self.assertEqual([(w.label, w.remaining) for w in windows], [("wk", 99.0)])

    def test_expired_window_dropped(self) -> None:
        self.gemini.USAGE_CACHE.write_text(json.dumps({
            "windows": {"wk": {"remaining": 50.0, "resets_at": time.time() - 1}},
            "at": time.time(),
        }))
        self.assertEqual(self.gemini.cached_usage(refresh=False), [])

    def test_model_picks_most_specific_name(self) -> None:
        path = self.gemini.CONVERSATIONS / "a.db"
        path.write_bytes(b"\x00gemini-3.6-flash\x00gemini-3.6-flash-high\x00")
        self.assertEqual(self.gemini.read_model(), "gemini-3.6-flash-high")

    def test_no_conversation_explains_itself(self) -> None:
        snap = self.gemini.GeminiAdapter().snapshot(Path("/repo"))
        self.assertIsNone(snap.model)
        self.assertIn("agy 패널", snap.error)

    def test_empty_usage_does_not_erase_cache(self) -> None:
        self.gemini.USAGE_CACHE.write_text(json.dumps({
            "windows": {"wk": {"remaining": 50.0, "resets_at": time.time() + 600}},
            "at": time.time(),
        }))
        with mock.patch.object(self.gemini.subprocess, "run",
                               return_value=mock.Mock(stdout="")):
            self.gemini.refresh_usage()
        self.assertEqual(len(self.gemini.cached_usage(refresh=False)), 1)

if __name__ == "__main__":
    unittest.main()
