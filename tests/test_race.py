"""rondo race 계약 테스트.

에이전트 실행은 흉내내지 않는다. worktree 에 파일을 직접 써서 "에이전트가 작업한 상태" 를
만들고, git 부분이 맞는지만 본다.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from rondo import race as race_mod  # noqa: E402
from rondo.model import Snapshot, Window  # noqa: E402


def run(root: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, check=True)
    return done.stdout


class RaceTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.cache = base / "cache"
        mock.patch.object(race_mod, "CACHE", self.cache).start()

        self.repo = base / "repo"
        self.repo.mkdir()
        run(self.repo, "init", "-q", "-b", "main")
        run(self.repo, "config", "user.email", "t@t")
        run(self.repo, "config", "user.name", "t")
        (self.repo / "app.py").write_text("print('hello')\n")
        run(self.repo, "add", "-A")
        run(self.repo, "commit", "-qm", "first")

    def tearDown(self) -> None:
        mock.patch.stopall()
        self.tmp.cleanup()

    def work(self, race, agent: str, name: str = "new.py", body: str = "x = 1\n") -> None:
        """에이전트가 worktree 에서 작업한 척."""
        (race.agents[agent] / name).write_text(body)


class StartTest(RaceTestBase):
    def test_worktrees_live_outside_the_repo(self) -> None:
        race = race_mod.start(self.repo, "과제", ["claude", "codex"])
        for path in race.agents.values():
            self.assertTrue(path.exists())
            self.assertNotIn(str(self.repo), str(path))

    def test_original_tree_untouched(self) -> None:
        race_mod.start(self.repo, "과제", ["claude"])
        self.assertEqual(run(self.repo, "status", "--porcelain"), "")
        self.assertEqual((self.repo / "app.py").read_text(), "print('hello')\n")

    def test_dirty_tree_is_frozen_into_the_base(self) -> None:
        # 바이브 코더 트리는 항상 dirty 하다. 막지 않고 그 상태를 출발점으로 삼는다.
        (self.repo / "app.py").write_text("print('edited')\n")
        race = race_mod.start(self.repo, "과제", ["claude"])
        worktree = race.agents["claude"]
        self.assertEqual((worktree / "app.py").read_text(), "print('edited')\n")
        # 원본의 미커밋 변경은 그대로 남는다
        self.assertIn("app.py", run(self.repo, "status", "--porcelain"))

    def test_second_race_is_refused(self) -> None:
        race_mod.start(self.repo, "과제", ["claude"])
        with self.assertRaises(race_mod.RaceError):
            race_mod.start(self.repo, "다른 과제", ["codex"])

    def test_no_agents_is_refused(self) -> None:
        with self.assertRaises(race_mod.RaceError):
            race_mod.start(self.repo, "과제", [])

    def test_state_round_trips(self) -> None:
        started = race_mod.start(self.repo, "과제", ["claude", "codex"])
        loaded = race_mod.load(self.repo)
        self.assertEqual(loaded.run_id, started.run_id)
        self.assertEqual(loaded.task, "과제")
        self.assertEqual(set(loaded.agents), {"claude", "codex"})


class SummaryTest(RaceTestBase):
    def test_uncommitted_agent_work_is_counted(self) -> None:
        race = race_mod.start(self.repo, "과제", ["claude", "codex"])
        self.work(race, "claude", "a.py", "a = 1\n")
        (race.agents["codex"] / "app.py").write_text("print('hello')\nprint('more')\n")

        rows = {row["agent"]: row for row in race_mod.summary(race)}
        self.assertEqual(rows["claude"]["files"], 1)      # 새 파일도 잡힌다
        self.assertEqual(rows["claude"]["added"], 1)
        self.assertEqual(rows["codex"]["files"], 1)
        self.assertEqual(rows["codex"]["added"], 1)

    def test_idle_agent_shows_nothing(self) -> None:
        race = race_mod.start(self.repo, "과제", ["claude"])
        rows = race_mod.summary(race)
        self.assertEqual(rows[0]["files"], 0)


class TakeTest(RaceTestBase):
    def test_take_applies_without_committing(self) -> None:
        race = race_mod.start(self.repo, "과제", ["claude", "codex"])
        self.work(race, "claude", "chosen.py", "chosen = True\n")
        self.work(race, "codex", "other.py", "other = True\n")

        result = race_mod.take(race, "claude")
        self.assertTrue(result["applied"])
        self.assertEqual((self.repo / "chosen.py").read_text(), "chosen = True\n")
        self.assertFalse((self.repo / "other.py").exists())
        # 커밋 여부는 사람이 정한다
        self.assertIn("chosen.py", run(self.repo, "status", "--porcelain"))
        self.assertEqual(run(self.repo, "log", "--oneline").count("\n"), 1)

    def test_take_onto_a_dirty_tree(self) -> None:
        """실제로 제일 흔한 경우다. base 가 stash 객체라 원본 인덱스는 아직 HEAD 다."""
        (self.repo / "app.py").write_text("print('hello')  # 미커밋\n")
        race = race_mod.start(self.repo, "과제", ["codex"])
        (race.agents["codex"] / "app.py").write_text("import guard\nprint('hello')  # 미커밋\n")

        result = race_mod.take(race, "codex")
        self.assertTrue(result["applied"])
        text = (self.repo / "app.py").read_text()
        self.assertIn("import guard", text)      # 에이전트 변경이 얹혔고
        self.assertIn("# 미커밋", text)           # 원래 미커밋 편집도 살아 있다

    def test_take_cleans_up_worktrees_and_branches(self) -> None:
        race = race_mod.start(self.repo, "과제", ["claude", "codex"])
        self.work(race, "claude")
        race_mod.take(race, "claude")

        for path in race.agents.values():
            self.assertFalse(path.exists())
        self.assertNotIn("rondo/race", run(self.repo, "branch", "--list", "rondo/race/*"))
        self.assertIsNone(race_mod.load(self.repo))

    def test_discarded_work_is_still_recoverable(self) -> None:
        race = race_mod.start(self.repo, "과제", ["claude", "codex"])
        self.work(race, "claude", "chosen.py")
        self.work(race, "codex", "discarded.py", "keep_me = 1\n")
        race_mod.take(race, "claude")

        patches = sorted((self.cache / "race").rglob("*-codex.patch"))
        self.assertEqual(len(patches), 1)
        self.assertIn("keep_me = 1", patches[0].read_text())

    def test_unknown_agent_is_refused(self) -> None:
        race = race_mod.start(self.repo, "과제", ["claude"])
        with self.assertRaises(race_mod.RaceError):
            race_mod.take(race, "codex")

    def test_taking_nothing_is_not_an_error(self) -> None:
        race = race_mod.start(self.repo, "과제", ["claude"])
        result = race_mod.take(race, "claude")
        self.assertFalse(result["applied"])
        self.assertIsNone(race_mod.load(self.repo))

    def test_conflicting_original_keeps_the_race(self) -> None:
        race = race_mod.start(self.repo, "과제", ["claude"])
        (race.agents["claude"] / "app.py").write_text("print('agent')\n")
        # race 도중 원본을 직접 고치면 충돌한다
        (self.repo / "app.py").write_text("print('human')\n")

        with self.assertRaises(race_mod.RaceError) as caught:
            race_mod.take(race, "claude")
        self.assertIn("patch", str(caught.exception))
        # 다시 시도할 수 있도록 race 를 지우지 않는다
        self.assertIsNotNone(race_mod.load(self.repo))


class AbortTest(RaceTestBase):
    def test_abort_removes_everything_but_saves_patches(self) -> None:
        race = race_mod.start(self.repo, "과제", ["claude", "codex"])
        self.work(race, "claude", "a.py", "a = 1\n")
        saved = race_mod.abort(race)

        self.assertEqual(len(saved), 2)
        self.assertIsNone(race_mod.load(self.repo))
        for path in race.agents.values():
            self.assertFalse(path.exists())
        self.assertIn("a = 1", Path(saved[0]).read_text())


class OrphanTest(RaceTestBase):
    def test_orphan_worktrees_are_found_and_pruned(self) -> None:
        race = race_mod.start(self.repo, "과제", ["claude"])
        race_mod.state_path(self.repo).unlink()  # 상태만 사라진 상황

        found = race_mod.orphans(self.repo)
        self.assertEqual(found, [race.agents["claude"]])
        race_mod.prune_orphans(self.repo)
        self.assertEqual(race_mod.orphans(self.repo), [])

    def test_live_race_is_not_reported_as_orphan(self) -> None:
        race_mod.start(self.repo, "과제", ["claude"])
        self.assertEqual(race_mod.orphans(self.repo), [])


class EligibleTest(unittest.TestCase):
    def snapshot(self, *windows: Window) -> Snapshot:
        return Snapshot(agent="x", windows=list(windows))

    def test_low_quota_agent_is_skipped(self) -> None:
        import time

        soon = time.time() + 3600
        joining, skipped = eligible = race_mod.eligible({
            "claude": self.snapshot(Window("5h", 28.0, soon)),
            "codex": self.snapshot(Window("wk", 89.0, soon)),
            "gemini": self.snapshot(Window("5h", 4.0, soon)),
        })
        self.assertEqual(joining, ["claude", "codex"])
        self.assertIn("gemini", skipped)
        self.assertIn("4%", skipped["gemini"])

    def test_unknown_quota_agents_still_join(self) -> None:
        # kimi·grok 은 한도를 못 읽는다. 막을 근거가 없으니 통과시킨다.
        joining, skipped = race_mod.eligible({"kimi": self.snapshot()})
        self.assertEqual(joining, ["kimi"])
        self.assertEqual(skipped, {})

    def test_tightest_window_decides(self) -> None:
        import time

        soon = time.time() + 3600
        joining, skipped = race_mod.eligible({
            "claude": self.snapshot(Window("5h", 3.0, soon), Window("wk", 90.0, soon)),
        })
        self.assertEqual(joining, [])
        self.assertIn("5h", skipped["claude"])


if __name__ == "__main__":
    unittest.main()
