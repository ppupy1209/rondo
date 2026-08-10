from __future__ import annotations

import importlib.util
import importlib.machinery
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import uuid
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "lib"))

from rondo import __version__, core
from rondo.cleanup import cleanup_file

TEST_TEMP = ROOT / "tests" / ".tmp"
TEST_TEMP.mkdir(exist_ok=True)


def test_directory() -> Path:
    path = TEST_TEMP / ("case-" + uuid.uuid4().hex)
    path.mkdir()
    return path


def load_cli():
    path = ROOT / "bin" / "rondo"
    loader = importlib.machinery.SourceFileLoader("rondo_cli", str(path))
    spec = importlib.util.spec_from_loader("rondo_cli", loader)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


class ProjectCase(unittest.TestCase):
    def setUp(self):
        self.root = test_directory()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def initialize(self, agents=None):
        config = dict(core.DEFAULT_CONFIG)
        if agents:
            config["agents"] = agents
            config["failover_order"] = agents
        return core.init_project(self.root, config)


class MinimalCoreTests(ProjectCase):
    def test_version_and_supported_agents_are_deliberately_small(self):
        self.assertEqual(__version__, "0.15.4")
        self.assertEqual(core.AGENTS, ("claude", "codex", "gemini"))
        with self.assertRaises(core.RondoError):
            core.normalize_agent("grok")

    def test_project_state_is_locally_excluded(self):
        self.initialize()
        exclude = subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", "--git-path", "info/exclude"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        path = Path(exclude)
        if not path.is_absolute():
            path = self.root / path
        self.assertIn("/.rondo/", path.read_text(encoding="utf-8"))
        status = subprocess.run(
            ["git", "-C", str(self.root), "status", "--short"], capture_output=True, text=True, check=True
        ).stdout
        self.assertNotIn(".rondo", status)

    def test_state_directory_link_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        try:
            (self.root / ".rondo").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("directory symlinks need extra privileges on this system")
        with self.assertRaises(core.RondoError):
            core.ensure_safe_state_dir(self.root)

    def test_linked_state_file_is_rejected(self):
        self.initialize()
        outside = self.root / "outside.jsonl"
        outside.write_text("protected", encoding="utf-8")
        messages = core.state_dir(self.root) / "messages.jsonl"
        try:
            messages.symlink_to(outside)
        except OSError:
            self.skipTest("file symlinks need extra privileges on this system")
        with self.assertRaises(core.RondoError):
            core.append_message(self.root, "Claude", "Codex", "hello")
        self.assertEqual(outside.read_text(encoding="utf-8"), "protected")

    def test_context_can_be_disabled_and_contains_only_bounded_summary(self):
        config, state = self.initialize()
        core.set_task(self.root, "ship the minimal coordinator")
        core.checkpoint(self.root, "implemented state machine", "claude", "impl-1")
        context = core.state_dir(self.root) / "context.md"
        text = context.read_text(encoding="utf-8")
        self.assertIn("implemented state machine", text)
        self.assertIn("- Approval: manual", text)
        self.assertLessEqual(len(text.encode("utf-8")), core.MAX_CONTEXT_BYTES)
        config["context"] = False
        core.save_config(self.root, config)
        core.render_context(self.root, config=config)
        self.assertFalse(context.exists())

    def test_messages_are_visible_and_secrets_are_redacted(self):
        self.initialize()
        item = core.append_message(
            self.root, "Claude", "Codex", "continue; api_key=super-secret-value", "handoff"
        )
        self.assertNotIn("super-secret-value", item["text"])
        messages = core.recent_messages(self.root)
        self.assertEqual(messages[0]["kind"], "handoff")
        self.assertIn("[REDACTED]", core.format_message(messages[0]))

    def test_approval_mode_is_bounded_to_two_safe_choices(self):
        config = core.validate_config({"agents": ["codex"], "approval": "workspace"})
        self.assertEqual(config["approval"], "workspace")
        with self.assertRaises(core.RondoError):
            core.validate_config({"agents": ["codex"], "approval": "unrestricted"})

    def test_checkpoint_then_handoff_preserves_context(self):
        self.initialize(["claude", "codex"])
        core.register_session(self.root, "claude", "claude-1", "1")
        core.register_session(self.root, "codex", "codex-1", "2")
        core.checkpoint(self.root, "API implementation half complete", "claude", "claude-1")
        with mock.patch.object(core, "deliver_to_session", return_value=True):
            result = core.handoff(self.root, "claude", "claude-1", "finish remaining endpoint")
        self.assertEqual(result["to"], "codex")
        state = core.load_state(self.root)
        self.assertEqual(state["task"]["owner"], "codex")
        self.assertIn("claude-1", state["task"]["implementers"])
        self.assertIn("finish remaining endpoint", (core.state_dir(self.root) / "context.md").read_text(encoding="utf-8"))

    def test_handoff_never_targets_the_exhausted_session_itself(self):
        self.initialize(["claude"])
        core.register_session(self.root, "claude", "only-session", "1")
        with self.assertRaises(core.RondoError):
            core.handoff(self.root, "claude", "only-session", "continue")

    def test_blocked_target_keeps_visible_handoff_without_injecting(self):
        self.initialize(["claude", "codex"])
        core.register_session(self.root, "claude", "impl", "1")
        core.register_session(self.root, "codex", "target", "2")
        with mock.patch.object(core, "deliver_to_session", side_effect=core.RondoError("approval prompt")):
            result = core.handoff(self.root, "claude", "impl", "continue safely")
        self.assertFalse(result["delivered"])
        self.assertEqual(result["delivery_error"], "approval prompt")
        self.assertEqual(core.recent_messages(self.root)[-1]["kind"], "handoff")

    def test_zellij_control_timeout_keeps_message_flow_non_fatal(self):
        self.initialize(["codex"])
        core.register_session(self.root, "codex", "target", "2")
        with mock.patch.object(core, "dump_pane", return_value=""), mock.patch.object(
            core.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(["zellij"], 8),
        ):
            self.assertFalse(core.deliver_to_session(self.root, "target", "continue"))

    def test_quota_detection_is_narrow(self):
        self.assertTrue(core.quota_exhausted("You've hit your usage limit"))
        self.assertTrue(core.quota_exhausted("usage window: 0% remaining"))
        self.assertFalse(core.quota_exhausted("The tests reached 0% coverage"))
        self.assertFalse(core.quota_exhausted("command exited with status 1"))

    def test_implementer_cannot_approve_own_work(self):
        self.initialize(["claude", "codex"])
        core.register_session(self.root, "claude", "impl", "1")
        core.register_session(self.root, "codex", "reviewer", "2")
        core.checkpoint(self.root, "implementation done", "claude", "impl")
        with mock.patch.object(core, "deliver_to_session", return_value=True):
            review = core.request_review(self.root, "claude", "impl", "codex")
        self.assertEqual(review["reviewer"], "reviewer")
        with self.assertRaises(core.RondoError):
            core.record_review(self.root, "pass", "looks good", "claude", "impl")
        accepted = core.record_review(self.root, "pass", "tests and review passed", "codex", "reviewer")
        self.assertEqual(accepted["status"], "passed")


class LayoutTests(ProjectCase):
    def test_interactive_picker_uses_keys_instead_of_agent_text(self):
        cli = load_cli()
        output = StringIO()
        keys = ("down", "down", "toggle", "confirm")
        with redirect_stdout(output), mock.patch.object(output, "isatty", return_value=True), mock.patch.object(
            cli.sys.stdin, "isatty", return_value=True
        ), mock.patch.object(cli, "_read_key", side_effect=keys):
            selected = cli.choose_agents(list(core.AGENTS), list(core.AGENTS))

        self.assertEqual(selected, ["claude", "codex"])
        self.assertIn("Space 선택/해제", output.getvalue())

    def test_interactive_approval_picker_uses_two_choices(self):
        cli = load_cli()
        output = StringIO()
        with redirect_stdout(output), mock.patch.object(output, "isatty", return_value=True), mock.patch.object(
            cli.sys.stdin, "isatty", return_value=True
        ), mock.patch.object(cli, "_read_key", side_effect=("down", "confirm")):
            selected = cli.choose_approval("manual")

        self.assertEqual(selected, "workspace")
        self.assertIn("프로젝트 안에서 자동 승인", output.getvalue())

    @unittest.skipIf(os.name == "nt", "Unix socket paths do not apply on Windows")
    def test_rondo_uses_a_short_private_zellij_socket_directory(self):
        with mock.patch.dict(os.environ, {"ZELLIJ_SOCKET_DIR": "/an/intentionally/long/user/socket/path"}):
            with mock.patch.object(core.shutil, "which", return_value="/usr/bin/zellij"):
                self.assertEqual(core.zellij_executable(), "/usr/bin/zellij")
            socket_dir = Path(os.environ["ZELLIJ_SOCKET_DIR"])
            self.assertEqual(socket_dir, Path("/tmp") / ("rondo-zellij-%s" % os.getuid()))
            self.assertTrue(socket_dir.is_dir())
            self.assertEqual(socket_dir.stat().st_mode & 0o777, 0o700)

    def test_layout_splits_enabled_agents_in_one_tab_and_keeps_relay_separate(self):
        cli = load_cli()
        core.ensure_safe_state_dir(self.root)
        path = cli.write_layout(self.root, ["claude", "gemini"])
        layout = path.read_text(encoding="utf-8")
        self.assertIn('tab name="Agents" focus=true', layout)
        self.assertIn('pane split_direction="vertical"', layout)
        self.assertIn('pane name="Claude"', layout)
        self.assertIn('pane name="Gemini"', layout)
        self.assertIn('tab name="Relay"', layout)
        self.assertNotIn('pane name="Codex"', layout)
        self.assertNotIn('tab name="Claude"', layout)
        self.assertNotIn('tab name="Gemini"', layout)
        self.assertNotIn("dashboard", layout.lower())
        self.assertEqual(layout.count("rondo-agent-session"), 2)
        self.assertEqual(layout.count('plugin location="tab-bar"'), 2)
        self.assertEqual(layout.count('plugin location="status-bar"'), 2)

    def test_three_agents_keep_one_large_pane_and_stack_two(self):
        cli = load_cli()
        core.ensure_safe_state_dir(self.root)
        layout = cli.write_layout(self.root, list(core.AGENTS)).read_text(encoding="utf-8")

        self.assertIn(
            'pane split_direction="vertical" {\n'
            '            pane name="Claude"',
            layout,
        )
        self.assertIn(
            '            pane split_direction="horizontal" {\n'
            '                pane name="Codex"',
            layout,
        )
        self.assertIn('                pane name="Gemini"', layout)

    def test_native_provider_commands_use_manual_approval_by_default(self):
        with mock.patch.dict(
            os.environ,
            {
                "RONDO_CLAUDE_COMMAND": "claude-test",
                "RONDO_CODEX_COMMAND": "codex-test",
                "RONDO_GEMINI_COMMAND": "gemini-test",
            },
            clear=False,
        ):
            claude = core.provider_command("claude", self.root)
            codex = core.provider_command("codex", self.root)
            gemini = core.provider_command("gemini", self.root)
        self.assertEqual(claude[:3], ["claude-test", "--permission-mode", "manual"])
        self.assertIn("--append-system-prompt", claude)
        self.assertEqual(codex[:5], ["codex-test", "--sandbox", "workspace-write", "--ask-for-approval", "untrusted"])
        self.assertIn("developer_instructions=", codex[-1])
        self.assertNotIn('"', codex[-1])
        self.assertIn("lightweight coordinator", codex[-1])
        self.assertIn("immediately execute `rondo message AGENT TEXT`", codex[-1])
        self.assertEqual(gemini[:3], ["gemini-test", "--approval-mode", "default"])
        self.assertIn("--prompt-interactive", gemini)

    def test_workspace_approval_keeps_each_provider_guarded(self):
        config = dict(core.DEFAULT_CONFIG)
        config["approval"] = "workspace"
        core.save_config(self.root, config)
        with mock.patch.dict(
            os.environ,
            {
                "RONDO_CLAUDE_COMMAND": "claude-test",
                "RONDO_CODEX_COMMAND": "codex-test",
                "RONDO_GEMINI_COMMAND": "gemini-test",
            },
            clear=False,
        ):
            commands = {
                agent: core.provider_command(agent, self.root)
                for agent in core.AGENTS
            }

        self.assertEqual(commands["claude"][:3], ["claude-test", "--permission-mode", "auto"])
        self.assertIn("--approve-for-me", commands["codex"])
        self.assertIn("workspace-write", commands["codex"])
        self.assertIn("auto_edit", commands["gemini"])
        self.assertIn("--sandbox", commands["gemini"])
        all_arguments = " ".join(argument for command in commands.values() for argument in command)
        self.assertNotIn("bypassPermissions", all_arguments)
        self.assertNotIn("dangerously-bypass", all_arguments)
        self.assertNotIn(" yolo ", " " + all_arguments + " ")

    def test_exited_zellij_session_is_not_treated_as_active(self):
        output = "rondo-demo [Created 2m ago] (EXITED - attach to resurrect)\nother [Created 1m ago]"
        completed = subprocess.CompletedProcess(["zellij"], 0, stdout=output, stderr="")
        with mock.patch.object(core, "zellij_executable", return_value="zellij"), mock.patch.object(
            core.subprocess, "run", return_value=completed
        ):
            self.assertEqual(core.zellij_session_status("rondo-demo"), "exited")
            self.assertEqual(core.zellij_session_status("other"), "active")
            self.assertFalse(core.zellij_session_exists("rondo-demo"))

    def test_fresh_screen_retires_stale_active_panes(self):
        self.initialize(["claude", "codex"])
        core.register_session(self.root, "claude", "old-claude", "0")
        core.register_session(self.root, "codex", "old-codex", "1")
        core.register_relay(self.root, "2")

        core.retire_active_sessions(self.root)

        state = core.load_state(self.root)
        self.assertEqual({item["status"] for item in state["sessions"].values()}, {"closed"})
        self.assertEqual(state["relay"]["status"], "closed")


class DistributionTests(unittest.TestCase):
    def test_installers_expose_only_three_rondo_launchers(self):
        powershell = (ROOT / "install.ps1").read_text(encoding="utf-8")
        shell = (ROOT / "install.sh").read_text(encoding="utf-8")
        for name in ("rondo", "rondo-relay", "rondo-agent-session"):
            self.assertIn('"%s"' % name, powershell)
            self.assertIn(name, shell)
        self.assertNotIn("Write-AgentLauncher", powershell)
        self.assertIn("RONDO_ZELLIJ_PATH", powershell)
        self.assertNotIn('setdefault("hooks"', shell)
        self.assertIn("python3 -m rondo.cleanup", shell)

    def test_repository_runtime_is_small(self):
        files = sorted(path.name for path in (ROOT / "bin").iterdir() if path.is_file())
        self.assertEqual(files, ["rondo", "rondo-agent-session", "rondo-relay"])
        modules = sorted(path.name for path in (ROOT / "lib" / "rondo").glob("*.py"))
        self.assertEqual(modules, ["__init__.py", "cleanup.py", "core.py"])

    def test_release_version_is_consistent(self):
        for name in ("README.md", "README.en.md", "CHANGELOG.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("0.15.4", text)


class CleanupTests(unittest.TestCase):
    def test_only_exact_legacy_entries_are_removed(self):
        temporary = test_directory()
        try:
            path = temporary / "settings.json"
            value = {
                "statusLine": {"type": "command", "command": "rondo-claude-status"},
                "hooks": {
                    "Stop": [
                        {"hooks": [{"type": "command", "command": "rondo snap --auto"}]},
                        {"hooks": [{"type": "command", "command": "my-company-hook"}]},
                    ]
                },
                "theme": "dark",
            }
            path.write_text(json.dumps(value), encoding="utf-8")
            removed = cleanup_file(path)
            cleaned = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(removed, 2)
            self.assertEqual(cleaned["theme"], "dark")
            self.assertIn("my-company-hook", json.dumps(cleaned))
            self.assertNotIn("rondo snap --auto", json.dumps(cleaned))
            self.assertTrue(path.with_name("settings.json.rondo-v014.bak").exists())
        finally:
            shutil.rmtree(temporary, ignore_errors=True)

    def test_windows_bom_settings_are_cleaned(self):
        temporary = test_directory()
        try:
            path = temporary / "settings.json"
            path.write_text(
                json.dumps({"statusLine": {"command": "rondo-claude-status"}, "theme": "light"}),
                encoding="utf-8-sig",
            )
            self.assertEqual(cleanup_file(path), 1)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"theme": "light"})
        finally:
            shutil.rmtree(temporary, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
