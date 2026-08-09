import json
import os
import runpy
import subprocess
import sys
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

    def test_missing_git_falls_back_to_current_directory(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["repo_root"].__globals__
        with patch.object(scope["subprocess"], "run", side_effect=FileNotFoundError):
            self.assertEqual(rondo["repo_root"](), Path.cwd())
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
            "zellij",
            ["zellij", "-s", "rondo-project", "-n", str(Path("/tmp/layout.kdl"))],
        )

    def test_settings_are_atomic_and_private(self):
        rondo = load_script("rondo", self.config, self.cache)
        rondo["write_setting"]("language", "ko")
        path = self.config / "rondo" / "language"
        self.assertEqual(path.read_text(), "ko\n")
        if os.name != "nt":
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
        suffix = ".cmd" if os.name == "nt" else ""
        self.assertIn(f'command="rondo-status{suffix}"', layout)
        self.assertIn(f'command="codex-session{suffix}"', layout)
        self.assertIn('tab name="shell"', layout)

    def test_windows_layout_uses_cmd_launchers(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["write_layout"].__globals__
        with patch.dict(scope, {"WINDOWS": True}):
            layout = rondo["write_layout"](["codex", "gemini"]).read_text()
        self.assertIn('command="rondo-status.cmd"', layout)
        self.assertIn('command="codex-session.cmd"', layout)
        self.assertIn('command="agy-session.cmd"', layout)

    def test_windows_runs_companion_scripts_with_python(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["script_argv"].__globals__
        with patch.dict(scope, {"WINDOWS": True}):
            command = rondo["script_argv"]("rondo-lens", "http://localhost:3000")
        self.assertEqual(command[0], scope["sys"].executable)
        self.assertEqual(command[1], str(ROOT / "bin" / "rondo-lens"))

    def test_agent_message_is_pasted_and_submitted_to_named_pane(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["send_agent_message"].__globals__
        panes = json.dumps(
            [
                {"id": 1, "title": "claude", "tab_name": "agents", "is_plugin": False, "exited": False},
                {"id": 2, "title": "codex", "tab_name": "agents", "is_plugin": False, "exited": False},
            ]
        )
        listed = subprocess.CompletedProcess([], 0, stdout=panes)
        with (
            patch.dict(scope["os"].environ, {"ZELLIJ_SESSION_NAME": "rondo-project"}),
            patch.object(scope["subprocess"], "run", side_effect=[listed, None, None]) as run,
        ):
            rondo["send_agent_message"]("codex", ["review", "the", "diff"])

        self.assertEqual(
            run.call_args_list[1].args[0],
            ["zellij", "action", "paste", "--pane-id", "2", "--", "review the diff"],
        )
        self.assertEqual(
            run.call_args_list[2].args[0],
            ["zellij", "action", "send-keys", "--pane-id", "2", "Enter"],
        )

    def test_lens_command_executes_the_companion_cli(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["open_lens"].__globals__
        with patch.object(scope["os"], "execv") as execv:
            rondo["open_lens"](["http://localhost:4173", "--allow-remote"])
        script = ROOT / "bin" / "rondo-lens"
        expected = [str(script), "http://localhost:4173", "--allow-remote"]
        program = script
        if os.name == "nt":
            expected.insert(0, sys.executable)
            program = sys.executable
        execv.assert_called_once_with(program, expected)


class LensTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.config = self.base / "config"
        self.cache = self.base / "cache"
        self.lens = load_script("rondo-lens", self.config, self.cache)

    def tearDown(self):
        self.temp.cleanup()

    def selection(self):
        return {
            "url": "http://localhost:3000/work",
            "title": "Rondo",
            "selector": "main > button:nth-of-type(2)",
            "tag": "button",
            "role": "button",
            "accessibleName": "Save",
            "html": '<button class="primary">Save</button>',
            "text": "Save",
            "styles": {"display": "flex", "color": "rgb(0, 0, 0)"},
            "rect": {"left": 10, "top": 20, "right": 110, "bottom": 60, "width": 100, "height": 40},
            "viewport": {"width": 800, "height": 600, "deviceScaleFactor": 2},
        }

    def test_only_local_http_urls_are_allowed_by_default(self):
        allowed = self.lens["allowed_url"]
        self.assertTrue(allowed("http://localhost:3000"))
        self.assertTrue(allowed("https://app.localhost/path"))
        self.assertFalse(allowed("https://example.com"))
        self.assertTrue(allowed("https://example.com", allow_remote=True))
        self.assertFalse(allowed("https://user:secret@example.com", allow_remote=True))
        self.assertFalse(allowed("file:///tmp/index.html", allow_remote=True))

    def test_screenshot_is_cropped_to_the_selected_element(self):
        clip = self.lens["screenshot_clip"](self.selection())
        self.assertEqual(clip, {"x": 0.0, "y": 4, "width": 126.0, "height": 72, "scale": 1})

    def test_context_packet_and_image_are_private(self):
        packet, image = self.lens["write_packet"](
            self.selection(), b"png", "Make this button quieter"
        )
        document = packet.read_text()
        self.assertIn("Make this button quieter", document)
        self.assertIn("main > button:nth-of-type(2)", document)
        self.assertEqual(image.read_bytes(), b"png")
        if os.name != "nt":
            self.assertEqual(packet.stat().st_mode & 0o777, 0o600)
            self.assertEqual(image.stat().st_mode & 0o777, 0o600)
            self.assertEqual(packet.parent.stat().st_mode & 0o777, 0o700)

    def test_capture_script_removes_form_values_and_masks_the_screenshot(self):
        script = self.lens["SELECTION_SCRIPT"]
        self.assertIn("node.removeAttribute('value')", script)
        self.assertIn("url: `${location.origin}${location.pathname}`", script)
        self.assertNotIn("__RONDO_LENS_BANNER__", self.lens["selection_script"]())
        source = Path(ROOT / "bin" / "rondo-lens").read_text(encoding="utf-8")
        self.assertIn("input,textarea,select,[contenteditable]", source)

    def test_page_readiness_retries_a_replaced_execution_context(self):
        failed = RuntimeError("Execution context was destroyed")
        devtools = unittest.mock.Mock()
        devtools.call.side_effect = [failed, {"result": {"value": "complete"}}]
        with patch.object(self.lens["time"], "sleep"):
            self.lens["wait_for_page"](devtools)
        self.assertEqual(devtools.call.call_count, 2)


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

    def test_auto_relay_sends_visible_prompt_to_codex_pane(self):
        relay = load_script("rondo-relay", self.config, self.cache)
        directory = relay["relay_dir"](self.repo)
        packet = directory / "packets" / "handoff.md"
        packet.parent.mkdir(parents=True)
        packet.write_text("handoff")
        result = subprocess.CompletedProcess([], 0, stdout="sent\n", stderr="")
        scope = relay["run_auto"].__globals__

        with patch.object(scope["subprocess"], "run", return_value=result) as run:
            self.assertEqual(relay["run_auto"](directory, packet, self.repo), 0)

        command = run.call_args.args[0]
        self.assertEqual(command[-3:-1], ["send", "codex"])
        self.assertIn(str(packet), command[-1])
        index = json.loads((directory / "pending.json").read_text())
        self.assertEqual(index["status"], "sent")

    def test_claude_status_triggers_ready_packet(self):
        config = self.config / "rondo"
        config.mkdir(parents=True)
        (config / "relay").write_text("ready\n")
        (config / "threshold").write_text("1\n")
        environment = os.environ | {
            "XDG_CONFIG_HOME": str(self.config),
            "XDG_CACHE_HOME": str(self.cache),
        }
        script = ROOT / "bin" / "rondo-claude-status"
        command = [sys.executable, str(script)] if os.name == "nt" else [str(script)]
        result = subprocess.run(
            command,
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
        window = relay["active_limit"](source)
        self.assertAlmostEqual(window.remaining, 0.5)
        # 라벨은 claude 어댑터가 정한다 — 예전에는 여기만 "7d" 로 달랐다
        self.assertEqual(window.label, "wk")

    @unittest.skipIf(os.name == "nt", "optional Git handoff log requires a POSIX shell")
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
