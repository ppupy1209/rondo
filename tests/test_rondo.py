import json
import os
import runpy
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_script(name, config, cache):
    with patch.dict(
        os.environ,
        {"XDG_CONFIG_HOME": str(config), "XDG_CACHE_HOME": str(cache), "LANG": "en_US.UTF-8"},
        clear=False,
    ):
        return runpy.run_path(str(ROOT / "bin" / name))


class RondoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.config = self.base / "config"
        self.cache = self.base / "cache"

    def tearDown(self):
        self.temp.cleanup()

    def test_session_names_are_safe(self):
        rondo = load_script("rondo", self.config, self.cache)
        self.assertEqual(rondo["safe_session_name"]("My project / feature"), "My-project-feature")
        self.assertEqual(rondo["safe_session_name"]("***"), "rondo")
        self.assertEqual(rondo["rondo_session_name"]("my-project"), "rondo-my-project")

    def test_exited_zellij_sessions_are_not_treated_as_active(self):
        rondo = load_script("rondo", self.config, self.cache)
        active, exited = rondo["parse_session_list"](
            "working [Created 2m ago]\n"
            "rondo-project [Created 1h ago] (EXITED - attach to resurrect)\n"
        )
        self.assertEqual(active, {"working"})
        self.assertEqual(exited, {"rondo-project"})

    def test_exited_rondo_session_is_recreated_with_current_layout(self):
        rondo = load_script("rondo", self.config, self.cache)
        rondo["write_setting"]("panels", "claude")
        scope = rondo["open_session"].__globals__

        with (
            patch.dict(
                scope,
                {
                    "repo_root": lambda: Path("/tmp/project"),
                    "zellij_sessions": lambda: (set(), {"rondo-project"}),
                    "installed": lambda _name: True,
                    "write_layout": lambda _panels: Path("/tmp/layout.kdl"),
                },
            ),
            patch.object(scope["shutil"], "which", return_value="/bin/zellij"),
            patch.object(scope["subprocess"], "run") as run,
            patch.object(scope["os"], "chdir"),
            patch.object(scope["os"], "execvp", side_effect=RuntimeError("stop")) as execvp,
        ):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                rondo["open_session"]()

        run.assert_called_once_with(
            ["zellij", "delete-session", "rondo-project"], check=True
        )
        execvp.assert_called_once_with(
            "zellij", ["zellij", "-s", "rondo-project", "-n", "/tmp/layout.kdl"]
        )

    def test_settings_are_atomic_and_private(self):
        rondo = load_script("rondo", self.config, self.cache)
        rondo["write_setting"]("language", "ko")
        path = self.config / "rondo" / "language"
        self.assertEqual(path.read_text(), "ko\n")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_legacy_panels_migrate_once(self):
        legacy = self.config / "ai-tools"
        legacy.mkdir(parents=True)
        (legacy / "panels").write_text("claude unknown codex\n")
        rondo = load_script("rondo", self.config, self.cache)
        rondo["migrate_legacy_config"]()
        target = self.config / "rondo"
        self.assertEqual((target / "panels").read_text().strip(), "claude codex")
        self.assertEqual((target / "relay").read_text().strip(), "ready")

    def test_layout_contains_only_known_commands(self):
        rondo = load_script("rondo", self.config, self.cache)
        layout = rondo["write_layout"](["claude", "codex", "gemini"]).read_text()
        self.assertIn('command="rondo-status"', layout)
        self.assertIn('command="codex-session"', layout)
        self.assertIn('tab name="shell"', layout)


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.config = self.base / "config"
        self.cache = self.base / "cache"
        self.repo = self.base / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.repo, check=True)
        (self.repo / "README.md").write_text("test\n")
        subprocess.run(["git", "add", "README.md"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.repo, check=True)

    def tearDown(self):
        self.temp.cleanup()

    def source(self):
        transcript = self.base / "transcript.jsonl"
        transcript.write_text(
            json.dumps({"type": "user", "message": {"content": "Finish the feature. api_key=super-secret-test-value"}})
            + "\n"
            + json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Implemented most of it."}]}})
            + "\n"
        )
        return {
            "session_id": "session-1",
            "cwd": str(self.repo),
            "workspace": {"project_dir": str(self.repo)},
            "transcript_path": str(transcript),
            "rate_limits": {
                "five_hour": {"used_percentage": 99.2, "resets_at": int(time.time()) + 3600}
            },
        }

    def test_packet_redacts_secrets_and_records_git_state(self):
        relay = load_script("rondo-relay", self.config, self.cache)
        packet = relay["packet_markdown"](self.source(), self.repo)
        self.assertIn("Finish the feature", packet)
        self.assertIn("Implemented most of it", packet)
        self.assertIn("Branch:", packet)
        self.assertIn("[REDACTED]", packet)
        self.assertNotIn("super-secret-test-value", packet)

    def test_capture_is_deduplicated_per_reset_window(self):
        relay = load_script("rondo-relay", self.config, self.cache)
        mode = self.config / "rondo"
        mode.mkdir(parents=True)
        (mode / "relay").write_text("ready\n")
        source = self.source()
        first = self.base / "first.json"
        second = self.base / "second.json"
        first.write_text(json.dumps(source))
        second.write_text(json.dumps(source))
        self.assertEqual(relay["capture"](first), 0)
        self.assertEqual(relay["capture"](second), 0)
        directory = relay["relay_dir"](self.repo)
        packets = list((directory / "packets").glob("*.md"))
        self.assertEqual(len(packets), 1)
        index = json.loads((directory / "pending.json").read_text())
        self.assertEqual(index["status"], "ready")

    def test_claude_status_triggers_ready_packet(self):
        config = self.config / "rondo"
        config.mkdir(parents=True)
        (config / "relay").write_text("ready\n")
        (config / "threshold").write_text("1\n")
        environment = os.environ | {
            "XDG_CONFIG_HOME": str(self.config),
            "XDG_CACHE_HOME": str(self.cache),
        }
        result = subprocess.run(
            [str(ROOT / "bin" / "rondo-claude-status")],
            input=json.dumps(self.source()),
            env=environment,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("5h", result.stdout)
        relay = load_script("rondo-relay", self.config, self.cache)
        pending = relay["relay_dir"](self.repo) / "pending.json"
        for _ in range(40):
            if pending.exists():
                break
            time.sleep(0.05)
        self.assertTrue(pending.exists())
        self.assertEqual(json.loads(pending.read_text())["status"], "ready")

    def test_active_limit_uses_the_most_constrained_window(self):
        relay = load_script("rondo-relay", self.config, self.cache)
        reset = int(time.time()) + 1000
        source = {
            "rate_limits": {
                "five_hour": {"used_percentage": 20, "resets_at": reset},
                "seven_day": {"used_percentage": 99.5, "resets_at": reset},
            }
        }
        left, _, label = relay["active_limit"](source)
        self.assertEqual(left, 0.5)
        self.assertEqual(label, "7d")

    def test_handoff_init_uses_selected_language(self):
        config = self.config / "rondo"
        config.mkdir(parents=True)
        (config / "language").write_text("en\n")
        environment = os.environ | {"XDG_CONFIG_HOME": str(self.config)}
        result = subprocess.run(
            [str(ROOT / "bin" / "handoff"), "--init"],
            cwd=self.repo,
            env=environment,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        document = (self.repo / "docs" / "handoff.md").read_text()
        self.assertIn("## Current stage", document)
        self.assertIn("## Next actions", document)


if __name__ == "__main__":
    unittest.main()
