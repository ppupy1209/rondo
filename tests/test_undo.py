"""rondo undo 계약 테스트. 에이전트가 트리를 망친 상황을 파일로 직접 만든다."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from rondo import undo as undo_mod  # noqa: E402
from rondo.gitcmd import GitError, git  # noqa: E402


class UndoTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "t@t")
        git(self.repo, "config", "user.name", "t")
        (self.repo / "app.py").write_text("print('hello')\n")
        (self.repo / ".gitignore").write_text("secret.env\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "first")

    def tearDown(self) -> None:
        self.tmp.cleanup()


class SnapshotTest(UndoTestBase):
    def test_untracked_files_are_captured(self) -> None:
        # git stash create 로는 못 담는다. 에이전트는 새 파일을 계속 만든다.
        (self.repo / "new.py").write_text("x = 1\n")
        snap = undo_mod.snapshot(self.repo)
        listed = git(self.repo, "ls-tree", "-r", "--name-only", snap.sha)
        self.assertIn("new.py", listed)

    def test_ignored_files_stay_out(self) -> None:
        (self.repo / "secret.env").write_text("TOKEN=1\n")
        snap = undo_mod.snapshot(self.repo)
        self.assertNotIn("secret.env", git(self.repo, "ls-tree", "-r", "--name-only", snap.sha))

    def test_index_and_worktree_untouched(self) -> None:
        (self.repo / "app.py").write_text("print('edited')\n")
        before = git(self.repo, "status", "--porcelain")
        undo_mod.snapshot(self.repo)
        self.assertEqual(git(self.repo, "status", "--porcelain"), before)
        self.assertEqual((self.repo / "app.py").read_text(), "print('edited')\n")

    def test_snapshot_does_not_move_branch(self) -> None:
        head = git(self.repo, "rev-parse", "HEAD").strip()
        undo_mod.snapshot(self.repo)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), head)
        self.assertEqual(git(self.repo, "log", "--oneline").count("\n"), 1)

    def test_snapshots_are_newest_first(self) -> None:
        first = undo_mod.snapshot(self.repo, "하나")
        (self.repo / "app.py").write_text("print('two')\n")
        second = undo_mod.snapshot(self.repo, "둘")
        history = undo_mod.snapshots(self.repo)
        self.assertEqual([s.sha for s in history[:2]], [second.sha, first.sha])
        self.assertEqual(history[0].label, "둘")

    def test_old_snapshots_are_pruned(self) -> None:
        for i in range(undo_mod.KEEP + 3):
            (self.repo / "app.py").write_text(f"print({i})\n")
            undo_mod.snapshot(self.repo)
        self.assertEqual(len(undo_mod.snapshots(self.repo)), undo_mod.KEEP)


class UndoTest(UndoTestBase):
    def test_edit_is_reverted(self) -> None:
        undo_mod.snapshot(self.repo, "작업 전")
        (self.repo / "app.py").write_text("print('에이전트가 망침')\n")
        result = undo_mod.undo(self.repo)
        self.assertTrue(result["undone"])
        self.assertEqual((self.repo / "app.py").read_text(), "print('hello')\n")

    def test_files_created_after_the_snapshot_are_removed(self) -> None:
        undo_mod.snapshot(self.repo, "작업 전")
        (self.repo / "junk.py").write_text("나쁜 코드\n")
        undo_mod.undo(self.repo)
        self.assertFalse((self.repo / "junk.py").exists())

    def test_files_deleted_by_the_agent_come_back(self) -> None:
        undo_mod.snapshot(self.repo, "작업 전")
        (self.repo / "app.py").unlink()
        undo_mod.undo(self.repo)
        self.assertEqual((self.repo / "app.py").read_text(), "print('hello')\n")

    def test_commits_are_not_touched(self) -> None:
        undo_mod.snapshot(self.repo, "작업 전")
        (self.repo / "app.py").write_text("print('작업')\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "에이전트 커밋")
        head = git(self.repo, "rev-parse", "HEAD").strip()
        undo_mod.undo(self.repo)
        # 작업 트리만 되돌린다. 커밋 이력은 그대로다.
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), head)
        self.assertEqual((self.repo / "app.py").read_text(), "print('hello')\n")

    def test_undo_is_itself_undoable(self) -> None:
        undo_mod.snapshot(self.repo, "작업 전")
        (self.repo / "app.py").write_text("print('살리고 싶은 작업')\n")
        undo_mod.undo(self.repo)
        self.assertEqual((self.repo / "app.py").read_text(), "print('hello')\n")
        undo_mod.undo(self.repo)  # 되돌리기 직전 상태로 복귀
        self.assertEqual((self.repo / "app.py").read_text(), "print('살리고 싶은 작업')\n")

    def test_nothing_changed_is_not_an_error(self) -> None:
        undo_mod.snapshot(self.repo, "작업 전")
        result = undo_mod.undo(self.repo)
        self.assertFalse(result["undone"])

    def test_no_snapshot_is_refused(self) -> None:
        with self.assertRaises(GitError):
            undo_mod.undo(self.repo)

    def test_steps_reaches_further_back(self) -> None:
        undo_mod.snapshot(self.repo, "1단계")
        (self.repo / "app.py").write_text("print('2')\n")
        undo_mod.snapshot(self.repo, "2단계")
        (self.repo / "app.py").write_text("print('3')\n")
        undo_mod.undo(self.repo, steps=2)
        self.assertEqual((self.repo / "app.py").read_text(), "print('hello')\n")

    def test_snapshot_id_selects_the_exact_target(self) -> None:
        first = undo_mod.snapshot(self.repo, "first")
        (self.repo / "app.py").write_text("print('second')\n")
        undo_mod.snapshot(self.repo, "second")
        (self.repo / "app.py").write_text("print('third')\n")

        changes = undo_mod.preview(self.repo, first)
        result = undo_mod.undo(self.repo, target_id=first.short)

        self.assertTrue(any("app.py" in row for row in changes))
        self.assertEqual(result["target"], first.short)
        self.assertEqual((self.repo / "app.py").read_text(), "print('hello')\n")

    def test_unknown_snapshot_id_is_rejected(self) -> None:
        undo_mod.snapshot(self.repo, "known")
        with self.assertRaisesRegex(GitError, "does-not-exist|스냅샷"):
            undo_mod.undo(self.repo, target_id="does-not-exist")


if __name__ == "__main__":
    unittest.main()
