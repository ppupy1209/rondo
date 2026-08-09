"""Process-level CLI tests that do not replace Rondo internals with mocks."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RONDO = ROOT / "bin" / "rondo"


class ProcessE2ETest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "Rondo Test"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "rondo@example.invalid"], check=True)
        (self.repo / "README.md").write_text("initial\n")
        subprocess.run(["git", "-C", str(self.repo), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "initial"], check=True)
        self.env = os.environ.copy()
        self.env.update({
            "XDG_CONFIG_HOME": str(self.base / "config"),
            "XDG_CACHE_HOME": str(self.base / "cache"),
            "RONDO_LANG": "en",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(ROOT / "lib"),
        })

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_rondo(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(RONDO), *args], cwd=self.repo, env=self.env,
            capture_output=True, text=True, timeout=15, check=check,
        )

    def test_state_survives_separate_cli_processes(self) -> None:
        created = self.run_rondo("note", "Process boundary complete")
        self.assertIn("Recorded work journal entry", created.stdout)
        history = self.run_rondo("history", "boundary")
        self.assertIn("Process boundary complete", history.stdout)

        self.run_rondo("task", "Keep process state durable", "--accept", "history survives")
        status = self.run_rondo("status")
        self.assertIn("Keep process state durable", status.stdout)
        self.assertIn("Rondo Command Center", status.stdout)

        bundle = self.base / "support.zip"
        created_bundle = self.run_rondo("support-bundle", str(bundle))
        self.assertIn(str(bundle), created_bundle.stdout)
        self.assertTrue(bundle.is_file())

    def test_lifecycle_mutation_is_rejected_without_a_user_terminal(self) -> None:
        result = self.run_rondo("uninstall", "--yes", check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("must be performed by the user", result.stderr)

    def test_forced_lock_holder_exit_recovers_without_corruption(self) -> None:
        holder = subprocess.Popen(
            [
                sys.executable,
                "-c",
                (
                    "import pathlib,time; from rondo import knowledge; "
                    f"knowledge.CACHE=pathlib.Path({str(self.base / 'cache' / 'rondo')!r}); "
                    f"root=pathlib.Path({str(self.repo)!r}); "
                    "lock=knowledge._locked(root); lock.__enter__(); "
                    "print('LOCKED', flush=True); time.sleep(60)"
                ),
            ],
            cwd=self.repo, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertEqual(holder.stdout.readline().strip(), "LOCKED")
            holder.terminate()
            holder.communicate(timeout=5)
            result = self.run_rondo("learn", "memory", "The lock recovery path works")
            self.assertIn("Pending proposal", result.stdout)
            states = list((self.base / "cache" / "rondo" / "knowledge").glob("*/state.json"))
            self.assertEqual(len(states), 1)
            value = json.loads(states[0].read_text())
            self.assertEqual(value["pending"][0]["content"], "The lock recovery path works")
        finally:
            if holder.poll() is None:
                holder.kill()
                holder.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
