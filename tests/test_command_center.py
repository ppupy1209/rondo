"""Command-center priority tests."""
from __future__ import annotations

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from rondo.command_center import build


class CommandCenterTest(unittest.TestCase):
    def state(self, **values):
        return build(repository="rondo", branch="main", **values)

    def test_human_approval_is_always_the_first_recommendation(self) -> None:
        state = self.state(
            goal="Ship it", changed=3, knowledge_pending=2,
            test_run={"id": "run", "complete": 0, "total": 2},
        )
        self.assertEqual((state["next"], state["reason"]), ("knowledge", "knowledge_pending"))

    def test_active_work_precedes_new_verification(self) -> None:
        scheduled = self.state(goal="Ship", changed=2, jobs={"pending": 1})
        testing = self.state(
            goal="Ship", changed=2,
            test_run={"id": "run", "complete": 1, "total": 2},
        )
        racing = self.state(goal="Ship", changed=2, race={"id": "race", "agents": 2})
        self.assertEqual(scheduled["next"], "schedule")
        self.assertEqual(testing["next"], "test-status")
        self.assertEqual(racing["next"], "race-status")

        complete = self.state(
            goal="Ship", changed=2,
            test_run={"id": "run", "complete": 2, "total": 2},
        )
        self.assertEqual(complete["next"], "test-finish")

    def test_changed_work_gets_intent_then_proof(self) -> None:
        self.assertEqual(self.state(changed=1)["next"], "goal")
        self.assertEqual(self.state(changed=1, goal="Fix login")["next"], "proof")
        self.assertEqual(self.state(goal="Fix login")["next"], "test")


if __name__ == "__main__":
    unittest.main()
