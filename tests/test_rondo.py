import contextlib
import io
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
        from rondo import knowledge as knowledge_lib
        self.knowledge_cache = patch.object(
            knowledge_lib, "CACHE", self.cache / "rondo"
        )
        self.knowledge_cache.start()
        self.output = io.StringIO()
        self.errors = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.output)
        self.redirect_errors = contextlib.redirect_stderr(self.errors)
        self.redirect.__enter__()
        self.redirect_errors.__enter__()

    def tearDown(self):
        self.redirect_errors.__exit__(None, None, None)
        self.redirect.__exit__(None, None, None)
        self.knowledge_cache.stop()
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

    def test_session_name_uses_origin_and_local_clone(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["rondo_session_name"].__globals__
        company = self.base / "company" / "backend"
        personal = self.base / "personal" / "backend"
        copy = self.base / "copy" / "backend"
        origins = {
            company: "git@github.com:company/backend.git",
            personal: "git@github.com:me/backend.git",
            copy: "git@github.com:company/backend.git",
        }
        with patch.dict(scope, {"git_origin": lambda root: origins[root]}):
            names = [rondo["rondo_session_name"](root) for root in origins]
            self.assertEqual(names[0], rondo["rondo_session_name"](company))
        self.assertEqual(len(set(names)), 3)
        self.assertTrue(all(name.startswith("rondo-backend-") for name in names))
        self.assertTrue(all(len(name) <= rondo["MAX_SESSION_NAME_CHARS"] for name in names))
        self.assertLessEqual(
            len(rondo["rondo_session_name"](company, "x" * 200)),
            rondo["MAX_SESSION_NAME_CHARS"],
        )

    @unittest.skipIf(os.name == "nt", "Unix socket paths are not used on Windows")
    def test_cli_uses_a_short_zellij_socket_directory(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["main"].__globals__
        opener = unittest.mock.Mock()
        with (
            patch.dict(scope["os"].environ, {}, clear=True),
            patch.dict(scope, {"open_session": opener}),
            patch.object(scope["sys"], "argv", ["rondo"]),
        ):
            rondo["main"]()
            socket_dir = scope["os"].environ["ZELLIJ_SOCKET_DIR"]

        self.assertEqual(socket_dir, f"/tmp/rondo-{os.getuid()}")
        opener.assert_called_once_with()

    def test_bare_rondo_opens_actions_inside_its_shell_session(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["main"].__globals__
        home = unittest.mock.Mock(return_value=0)
        opener = unittest.mock.Mock()
        with (
            patch.dict(
                scope["os"].environ,
                {"ZELLIJ_SESSION_NAME": "rondo-project", "RONDO_AGENT": ""},
                clear=True,
            ),
            patch.dict(scope, {"home_command": home, "open_session": opener}),
            patch.object(scope["sys"], "argv", ["rondo"]),
        ):
            self.assertEqual(rondo["main"](), 0)

        home.assert_called_once_with()
        opener.assert_not_called()

    def test_exited_zellij_sessions_are_not_treated_as_active(self):
        rondo = load_script("rondo", self.config, self.cache)
        active, exited = rondo["parse_session_list"](
            "working [Created 2m ago]\n"
            "rondo-project [Created 1h ago] (EXITED - attach to resurrect)\n"
        )
        self.assertEqual(active, {"working"})
        self.assertEqual(exited, {"rondo-project"})

    def test_exited_rondo_session_is_resurrected(self):
        rondo = load_script("rondo", self.config, self.cache)
        rondo["write_setting"]("panels", "claude")
        scope = rondo["open_session"].__globals__

        with (
            patch.dict(
                scope,
                {
                "repo_root": lambda: Path("/tmp/project"),
                "rondo_session_name": lambda _root, _custom=None: "rondo-project",
                "require_git_repo": lambda _root: None,
                    "zellij_sessions": lambda: (set(), {"rondo-project"}),
                    "installed": lambda _name: True,
                    "write_layout": lambda _panels: Path("/tmp/layout.kdl"),
                },
            ),
            patch.object(scope["shutil"], "which", return_value="/bin/zellij"),
            patch.object(scope["os"], "chdir") as chdir,
            patch.object(scope["os"], "execvp", side_effect=RuntimeError("stop")) as execvp,
        ):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                rondo["open_session"]()

        chdir.assert_called_once_with(Path("/tmp/project"))
        execvp.assert_called_once_with(
            "zellij",
            ["zellij", "attach", "--force-run-commands", "rondo-project"],
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
        self.assertEqual((target / "audience").read_text().strip(), "default")
        self.assertEqual((target / "relay").read_text().strip(), "ready")

    def test_noninteractive_setup_accepts_audience_environment(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["setup"].__globals__
        environment = {
            "RONDO_LANG": "ko",
            "RONDO_AUDIENCE": "nondev",
            "RONDO_APPROVAL": "workspace",
            "RONDO_PANELS": "claude",
            "RONDO_RELAY": "ready",
        }
        with (
            patch.dict(scope["os"].environ, environment, clear=False),
            patch.dict(scope, {"installed": lambda _name: True}),
        ):
            rondo["setup"]()
        self.assertEqual((self.config / "rondo" / "audience").read_text().strip(), "nondev")
        self.assertEqual((self.config / "rondo" / "approval").read_text().strip(), "workspace")

    def test_setup_rejects_more_than_four_panels(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["choose_agents"].__globals__
        with (
            patch.dict(scope["os"].environ, {"RONDO_PANELS": "claude codex gemini kimi grok"}),
            patch.dict(scope, {"installed": lambda _name: True}),
            patch.object(scope["sys"].stdin, "isatty", return_value=False),
        ):
            with self.assertRaisesRegex(RuntimeError, "4"):
                rondo["choose_agents"](set())

    def test_first_rondo_run_configures_then_opens_the_session(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["open_session"].__globals__
        setup = unittest.mock.Mock(
            side_effect=lambda: rondo["write_setting"]("panels", "claude")
        )
        with (
            patch.dict(scope, {
                "setup": setup,
                "repo_root": lambda: self.base,
                "rondo_session_name": lambda _root, _custom=None: "rondo-first",
                "require_git_repo": lambda _root: None,
                "zellij_sessions": lambda: (set(), set()),
                "installed": lambda _name: True,
                "write_layout": lambda _panels: self.base / "layout.kdl",
                "git_policy": lambda _root: "direct",
            }),
            patch.object(scope["shutil"], "which", return_value="/bin/zellij"),
            patch.object(scope["os"], "chdir"),
            patch.object(scope["os"], "execvp", side_effect=RuntimeError("stop")) as execvp,
        ):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                rondo["open_session"]()

        setup.assert_called_once_with()
        self.assertEqual(execvp.call_args.args[1][:3], ["zellij", "-s", "rondo-first"])

    def test_add_refuses_a_fifth_agent_pane(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["add_agent"].__globals__
        with (
            patch.dict(scope["os"].environ, {"ZELLIJ": "1"}),
            patch.dict(scope, {
                "installed": lambda _name: True,
                "agent_panes": lambda: {
                    "claude": "1", "codex": "2", "gemini": "3", "kimi": "4",
                },
            }),
        ):
            with self.assertRaisesRegex(RuntimeError, "4"):
                rondo["add_agent"]("grok")

    def test_git_connect_and_policy_use_repository_local_config(self):
        rondo = load_script("rondo", self.config, self.cache)
        repo = self.base / "repo"
        repo.mkdir()
        scope = rondo["git_command"].__globals__
        with patch.dict(scope, {"repo_root": lambda: repo}):
            rondo["git_command"](["connect", "https://github.com/me/project.git"])
            rondo["git_command"](["policy", "review"])

        origin = subprocess.run(
            ["git", "-C", str(repo), "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        policy = subprocess.run(
            ["git", "-C", str(repo), "config", "--local", "--get", "rondo.prPolicy"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        self.assertEqual(origin, "https://github.com/me/project.git")
        self.assertEqual(policy, "review")

    def test_code_review_all_starts_at_most_four_read_only_agents(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["code_review_command"].__globals__
        with (
            patch.dict(scope["os"].environ, {"ZELLIJ_SESSION_NAME": "rondo-project"}),
            patch.dict(scope, {
                "repo_root": lambda: self.base,
                "git_output": lambda _root, *args, **_kwargs: (
                    "true" if args[:2] == ("rev-parse", "--is-inside-work-tree")
                    else "origin/main" if args and args[0] == "symbolic-ref"
                    else ""
                ),
                "git_reviewers": lambda _root: list(rondo["AGENTS"]),
                "installed": lambda _name: True,
            }),
            patch.object(scope["shutil"], "which", side_effect=lambda name: f"/bin/{name}"),
            patch.object(scope["subprocess"], "run") as run,
        ):
            self.assertEqual(rondo["code_review_command"](["all"]), 0)

        run.assert_called_once()
        command = run.call_args.args[0]
        self.assertEqual(command[:3], ["zellij", "action", "new-tab"])
        layout = command[-1]
        self.assertEqual(layout.count('name="review-'), 4)
        self.assertIn("plan", layout)
        self.assertIn("read-only", layout)

    def test_same_vendor_tester_never_resumes_implementation_session(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["test_agent_argv"].__globals__
        with (
            patch.dict(scope, {"installed": lambda _name: True}),
            patch.object(scope["shutil"], "which", return_value="/bin/codex"),
        ):
            command = rondo["test_agent_argv"]("codex", "verify independently")

        self.assertEqual(command[0], "/bin/codex")
        self.assertNotIn("resume", command)
        self.assertNotIn("--last", command)
        self.assertEqual(command[-1], "verify independently")

    def test_test_layout_has_only_fresh_verifier_panes(self):
        rondo = load_script("rondo", self.config, self.cache)
        from rondo import testing as testing_lib

        run = unittest.mock.Mock(
            run_id="run123",
            roles={
                "red": {"agent": "codex", "worktree": "/tmp/red"},
                "blue": {"agent": "claude", "worktree": "/tmp/blue"},
            },
        )
        scope = rondo["test_layout"].__globals__
        with (
            patch.object(testing_lib, "role_prompt", return_value="verify independently"),
            patch.object(scope["shutil"], "which", side_effect=lambda name: f"/bin/{name}"),
        ):
            layout = rondo["test_layout"](run)

        self.assertEqual(layout.count('name="test-'), 3)  # tab + two verifier panes
        self.assertIn('tab name="test-run123"', layout)
        self.assertNotIn("resume", layout)
        self.assertNotIn("--last", layout)

    def test_test_layout_keeps_unicode_as_valid_kdl_text(self):
        rondo = load_script("rondo", self.config, self.cache)
        from rondo import testing as testing_lib

        run = unittest.mock.Mock(
            run_id="한글",
            roles={"review": {"agent": "codex", "worktree": "/tmp/한글 저장소"}},
        )
        scope = rondo["test_layout"].__globals__
        with (
            patch.object(testing_lib, "role_prompt", return_value="한국어 검증"),
            patch.object(scope["shutil"], "which", return_value="/bin/codex"),
        ):
            layout = rondo["test_layout"](run)

        self.assertIn("한국어 검증", layout)
        self.assertIn("한글 저장소", layout)
        self.assertNotIn("\\u", layout)

    def test_test_finish_waits_for_every_independent_report(self):
        rondo = load_script("rondo", self.config, self.cache)
        from rondo import testing as testing_lib

        run = unittest.mock.Mock(
            roles={"red": {"report": str(self.base / "missing.md")}},
        )
        with patch.object(testing_lib, "load", return_value=run):
            with self.assertRaisesRegex(RuntimeError, "missing|보고서"):
                rondo["test_command"](["finish"])

    def test_test_tab_closes_in_its_owning_zellij_session(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["_close_test_tab"].__globals__
        run = unittest.mock.Mock(
            tab_id="42", zellij_session="rondo-owner", zellij_socket="/tmp/rondo-owner-socket"
        )
        listed = subprocess.CompletedProcess([], 0, "rondo-owner\n", "")
        closed = subprocess.CompletedProcess([], 0, "", "")
        with (
            patch.object(scope["subprocess"], "run", side_effect=[listed, closed]) as execute,
        ):
            rondo["_close_test_tab"](run)

        self.assertEqual(execute.call_count, 2)
        execute.assert_any_call(
            ["zellij", "-s", "rondo-owner", "action", "close-tab", "--tab-id", "42"],
            capture_output=True,
            text=True,
            env=unittest.mock.ANY,
        )
        self.assertEqual(execute.call_args_list[0].kwargs["env"]["ZELLIJ_SOCKET_DIR"], "/tmp/rondo-owner-socket")

    def test_test_tab_cleanup_fails_closed_when_session_lookup_fails(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["_close_test_tab"].__globals__
        run = unittest.mock.Mock(
            tab_id="42", zellij_session="rondo-owner", zellij_socket="/tmp/rondo-owner-socket"
        )
        failed = subprocess.CompletedProcess([], 1, "", "socket unavailable")
        with patch.object(scope["subprocess"], "run", return_value=failed) as execute:
            with self.assertRaisesRegex(RuntimeError, "socket unavailable"):
                rondo["_close_test_tab"](run)

        execute.assert_called_once()

    def test_review_policy_creates_a_draft_pr_and_starts_reviews(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["pr_command"].__globals__
        outputs = {
            ("rev-parse", "--is-inside-work-tree"): "true",
            ("status", "--porcelain"): "",
            ("branch", "--show-current"): "feature/login",
            ("symbolic-ref", "--short", "refs/remotes/origin/HEAD"): "origin/main",
        }
        reviewer = unittest.mock.Mock(return_value=0)
        with (
            patch.dict(scope["os"].environ, {"ZELLIJ_SESSION_NAME": "rondo-project"}),
            patch.dict(scope, {
                "repo_root": lambda: self.base,
                "git_origin": lambda _root: "https://github.com/me/project",
                "git_output": lambda _root, *args, **_kwargs: outputs.get(args, ""),
                "git_policy": lambda _root: "review",
                "code_review_command": reviewer,
            }),
            patch.object(scope["shutil"], "which", return_value="/bin/gh"),
            patch.object(scope["subprocess"], "run") as run,
        ):
            self.assertEqual(rondo["pr_command"](["Improve", "login"]), 0)

        self.assertEqual(
            run.call_args_list[0].args[0],
            ["git", "-C", str(self.base), "push", "--set-upstream", "origin", "feature/login"],
        )
        self.assertEqual(
            run.call_args_list[1].args[0],
            ["gh", "pr", "create", "--fill", "--draft", "--title", "Improve login"],
        )
        reviewer.assert_called_once_with(["all"])

    def test_layout_contains_only_known_commands(self):
        rondo = load_script("rondo", self.config, self.cache)
        layout = rondo["write_layout"](["claude", "codex", "gemini", "kimi"]).read_text()
        suffix = ".cmd" if os.name == "nt" else ""
        self.assertIn(f'command="rondo-status{suffix}"', layout)
        self.assertIn(f'command="claude-session{suffix}"', layout)
        self.assertIn(f'command="codex-session{suffix}"', layout)
        self.assertIn(f'command="kimi-session{suffix}"', layout)
        self.assertIn('tab name="shell"', layout)

    def test_windows_layout_uses_cmd_launchers(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["write_layout"].__globals__
        with patch.dict(scope, {"WINDOWS": True}):
            layout = rondo["write_layout"](["claude", "codex", "gemini"]).read_text()
        self.assertIn('command="rondo-status.cmd"', layout)
        self.assertIn('command="claude-session.cmd"', layout)
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
        ready = subprocess.CompletedProcess([], 0, stdout="❯")
        pasted = subprocess.CompletedProcess([], 0, stdout="review the diff")
        done = subprocess.CompletedProcess([], 0, stdout="")
        with (
            patch.dict(scope["os"].environ, {"ZELLIJ_SESSION_NAME": "rondo-project"}),
            patch.object(scope["subprocess"], "run", side_effect=[listed, ready, done, pasted, done]) as run,
        ):
            rondo["send_agent_message"]("codex", ["review", "the", "diff"])

        self.assertEqual(
            run.call_args_list[2].args[0],
            ["zellij", "action", "paste", "--pane-id", "2", "--", "review the diff"],
        )
        self.assertEqual(
            run.call_args_list[4].args[0],
            ["zellij", "action", "send-keys", "--pane-id", "2", "Enter"],
        )

    def test_agent_message_never_accepts_a_trust_prompt(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["send_agent_message"].__globals__
        panes = json.dumps(
            [{"id": 2, "title": "claude", "tab_name": "agents", "is_plugin": False, "exited": False}]
        )
        listed = subprocess.CompletedProcess([], 0, stdout=panes)
        trust = subprocess.CompletedProcess(
            [], 0, stdout="Quick safety check: Is this a project you created or one you trust?\nEnter to confirm · Esc to cancel"
        )
        with (
            patch.dict(scope["os"].environ, {"ZELLIJ_SESSION_NAME": "rondo-project"}),
            patch.object(scope["subprocess"], "run", side_effect=[listed, trust]) as run,
        ):
            with self.assertRaises(rondo["PaneNotReady"]):
                rondo["send_agent_message"]("claude", ["do not approve"])

        self.assertEqual(run.call_count, 2)

    def test_agent_message_is_not_submitted_without_visible_delivery(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["_send_to_pane"].__globals__
        ready = subprocess.CompletedProcess([], 0, stdout="❯")
        done = subprocess.CompletedProcess([], 0, stdout="")
        with (
            patch.object(scope["subprocess"], "run", side_effect=[ready, done, ready, done]) as run,
            patch.object(scope["time"], "monotonic", side_effect=[0, 0, 2]),
        ):
            with self.assertRaisesRegex(RuntimeError, "visible|확인"):
                rondo["_send_to_pane"]("codex", "2", "continue", ["zellij"])

        self.assertNotIn("Enter", run.call_args_list[-1].args[0])
        self.assertIn("Esc", run.call_args_list[-1].args[0])

    def test_agent_message_can_target_an_existing_session(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["send_agent_message"].__globals__
        panes = json.dumps(
            [{"id": 7, "title": "codex", "tab_name": "agents", "is_plugin": False, "exited": False}]
        )
        listed = subprocess.CompletedProcess([], 0, stdout=panes)
        ready = subprocess.CompletedProcess([], 0, stdout="❯")
        pasted = subprocess.CompletedProcess([], 0, stdout="continue")
        done = subprocess.CompletedProcess([], 0, stdout="")
        with patch.object(scope["subprocess"], "run", side_effect=[listed, ready, done, pasted, done]) as run:
            rondo["send_agent_message"]("codex", ["continue"], session_name="rondo-project")
        self.assertEqual(
            run.call_args_list[2].args[0],
            ["zellij", "-s", "rondo-project", "action", "paste", "--pane-id", "7", "--", "continue"],
        )

    def test_handoff_creates_a_git_portable_context_file(self):
        rondo = load_script("rondo", self.config, self.cache)
        repo = self.base / "repo"
        repo.mkdir()
        scope = rondo["handoff_command"].__globals__
        outputs = {
            ("branch", "--show-current"): "main",
            ("rev-parse", "--short", "HEAD"): "abc1234",
            ("status", "--short"): " M app.py",
            ("diff", "--stat"): " app.py | 2 ++",
            ("log", "-5", "--pretty=format:%h %s"): "abc1234 feat: work",
        }
        with patch.dict(
            scope,
            {
                "repo_root": lambda: repo,
                "git_origin": lambda _root: "git@github.com:me/project",
                "git_output": lambda _root, *args, **_kwargs: outputs.get(args, ""),
            },
        ):
            self.assertEqual(rondo["handoff_command"](["Finish", "tests"]), 0)
        document = (repo / ".rondo" / "handoff.md").read_text()
        self.assertIn("Finish tests", document)
        self.assertIn("Branch: main", document)
        self.assertIn(" M app.py", document)
        self.assertNotIn(str(repo), document)

    def test_resume_passes_the_handoff_to_the_selected_agent(self):
        rondo = load_script("rondo", self.config, self.cache)
        rondo["write_setting"]("panels", "claude codex")
        repo = self.base / "repo"
        packet = repo / ".rondo" / "handoff.md"
        packet.parent.mkdir(parents=True)
        packet.write_text("handoff")
        scope = rondo["resume_command"].__globals__
        with (
            patch.dict(scope, {"repo_root": lambda: repo, "installed": lambda _name: True}),
            patch.dict(scope["os"].environ, {}, clear=False),
            patch.object(scope["open_session"].__globals__["os"], "execvp"),
            patch.object(scope["open_session"].__globals__["shutil"], "which", return_value="/bin/zellij"),
            patch.object(scope["open_session"].__globals__["subprocess"], "run"),
            patch.dict(
                scope,
                {
                    "open_session": unittest.mock.Mock(),
                },
            ),
        ):
            opener = scope["open_session"]
            rondo["resume_command"]("codex")
            opener.assert_called_once_with(resume_agent="codex", handoff=packet)
            self.assertEqual(scope["os"].environ["RONDO_RESUME_AGENT"], "codex")

    def test_proof_reviewer_opens_a_fresh_read_only_pane(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["start_proof_reviewer"].__globals__
        packet = self.base / "proof.md"
        packet.write_text("proof")
        with (
            patch.dict(scope["os"].environ, {"ZELLIJ_SESSION_NAME": "rondo-project"}),
            patch.dict(scope, {"installed": lambda _name: True}),
            patch.object(scope["shutil"], "which", return_value="/bin/codex"),
            patch.object(scope["subprocess"], "run") as run,
        ):
            rondo["start_proof_reviewer"]("codex", packet, self.base)
        command = run.call_args.args[0]
        self.assertEqual(command[:5], ["zellij", "action", "new-pane", "--name", "proof-codex"])
        self.assertIn("read-only", command)
        self.assertIn(str(packet), command[-1])

    def test_task_command_records_structured_verification_intent(self):
        rondo = load_script("rondo", self.config, self.cache)
        from rondo import proof as proof_lib

        repo = self.base / "repo"
        repo.mkdir()
        scope = rondo["task_command"].__globals__
        with (
            patch.object(proof_lib, "CACHE", self.cache / "rondo"),
            patch.dict(scope, {"repo_root": lambda: repo}),
        ):
            result = rondo["task_command"]([
                "Improve", "login", "errors",
                "--accept", "Invalid passwords show an error",
                "--avoid", "Do not change the API",
                "--scope", "web",
                "--check", "python -m unittest",
            ])
            task = proof_lib.load_task(repo)

        self.assertEqual(result, 0)
        self.assertEqual(task["goal"], "Improve login errors")
        self.assertEqual(task["acceptance"], ["Invalid passwords show an error"])
        self.assertEqual(task["must_not"], ["Do not change the API"])
        self.assertEqual(task["scope"], ["web"])
        self.assertEqual(task["checks"], [["python", "-m", "unittest"]])

    def test_learn_command_keeps_agent_proposals_pending_until_user_approval(self):
        rondo = load_script("rondo", self.config, self.cache)
        from rondo import knowledge as knowledge_lib

        repo = self.base / "repo"
        repo.mkdir()
        scope = rondo["learn_command"].__globals__
        with patch.object(knowledge_lib, "CACHE", self.cache / "rondo"):
            with (
                patch.dict(scope, {
                    "repo_root": lambda: repo,
                    "require_git_repo": lambda _root: None,
                }),
                patch.dict(scope["os"].environ, {"RONDO_AGENT": "codex"}, clear=False),
            ):
                self.assertEqual(
                    rondo["learn_command"](["memory", "Use", "UTC", "timestamps."]), 0
                )
                pending = knowledge_lib.load(repo)["pending"][0]
                with self.assertRaisesRegex(RuntimeError, "interactive terminal"):
                    rondo["learn_command"](["pending"])

            self.assertEqual(pending["source"], "codex")
            self.assertEqual(knowledge_lib.load(repo)["memories"], [])
            key = knowledge_lib.state_path(repo).parent.name
            audience = scope["CACHE_DIR"] / "audience"
            audience.mkdir(parents=True)
            stale_guidance = audience / f"kimi-default-{key}.md"
            stale_guidance.write_text("old project memory")
            with patch.dict(scope, {
                "repo_root": lambda: repo,
                "require_git_repo": lambda _root: None,
                "_knowledge_require_user_terminal": lambda: None,
                "_knowledge_confirm": lambda _prompt, checked=False: True,
            }):
                self.assertEqual(rondo["learn_command"](["approve", pending["id"]]), 0)
                self.assertEqual(rondo["recall_command"](["--id", pending["id"]]), 0)

            self.assertIn("Use UTC timestamps.", self.output.getvalue())
            self.assertFalse(stale_guidance.exists())
            self.assertEqual(knowledge_lib.load(repo)["pending"], [])
            self.assertEqual(len(knowledge_lib.load(repo)["memories"]), 1)

    def test_knowledge_menu_manages_items_without_typing_an_id(self):
        rondo = load_script("rondo", self.config, self.cache)
        from rondo import knowledge as knowledge_lib

        repo = self.base / "repo"
        repo.mkdir()
        proposal = knowledge_lib.propose(repo, "memory", "Use UTC timestamps.")
        active = knowledge_lib.propose(repo, "memory", "Keep APIs compatible.")
        knowledge_lib.approve(repo, active["id"], actor="human")
        scope = rondo["knowledge_review_command"].__globals__
        learn = unittest.mock.Mock(return_value=0)
        with patch.dict(scope, {
            "repo_root": lambda: repo,
            "require_git_repo": lambda _root: None,
            "_knowledge_require_user_terminal": lambda: None,
            "choose_one": unittest.mock.Mock(
                side_effect=[
                    f"pending:{proposal['id']}", "approve",
                    f"active:{active['id']}", "remove",
                ]
            ),
            "learn_command": learn,
        }):
            self.assertEqual(rondo["knowledge_review_command"](), 0)
            self.assertEqual(rondo["knowledge_review_command"](), 0)

        self.assertEqual(
            learn.call_args_list,
            [
                unittest.mock.call(["approve", proposal["id"]]),
                unittest.mock.call(["remove", active["id"]]),
            ],
        )

    def test_agent_started_tests_choose_saved_other_agents_without_a_menu(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["_testers"].__globals__
        chooser = unittest.mock.Mock()
        with (
            patch.dict(scope["os"].environ, {"RONDO_AGENT": "codex"}, clear=True),
            patch.dict(scope, {
                "repo_root": lambda: self.base,
                "git_reviewers": lambda _root: [],
                "configured_panels": lambda: ["codex", "claude"],
                "installed": lambda _name: True,
                "choose_agents": chooser,
            }),
        ):
            self.assertEqual(rondo["_testers"]([]), ["claude"])

        chooser.assert_not_called()

    def test_knowledge_decisions_require_a_user_terminal_or_shell_tab(self):
        rondo = load_script("rondo", self.config, self.cache)
        confirm = rondo["_knowledge_confirm"]
        scope = confirm.__globals__
        stdin = unittest.mock.Mock()
        stdout = unittest.mock.Mock()
        stdin.isatty.return_value = True
        stdout.isatty.return_value = True

        with (
            patch.object(scope["sys"], "stdin", stdin),
            patch.object(scope["sys"], "stdout", stdout),
            patch.dict(scope["os"].environ, {"RONDO_AGENT": "codex"}, clear=True),
        ):
            with self.assertRaisesRegex(RuntimeError, "interactive terminal"):
                confirm("approve? ")

        agent_pane = subprocess.CompletedProcess(
            [], 0, json.dumps([{"id": 7, "tab_name": "agents"}]), ""
        )
        environment = {"ZELLIJ_SESSION_NAME": "rondo-project", "ZELLIJ_PANE_ID": "7"}
        with (
            patch.object(scope["sys"], "stdin", stdin),
            patch.object(scope["sys"], "stdout", stdout),
            patch.dict(scope["os"].environ, environment, clear=True),
            patch.object(scope["subprocess"], "run", return_value=agent_pane),
        ):
            with self.assertRaisesRegex(RuntimeError, "interactive terminal"):
                confirm("approve? ")

        proof_pane = subprocess.CompletedProcess(
            [], 0, json.dumps([{
                "id": 7, "tab_name": "shell", "title": "proof-codex"
            }]), ""
        )
        with (
            patch.object(scope["sys"], "stdin", stdin),
            patch.object(scope["sys"], "stdout", stdout),
            patch.dict(scope["os"].environ, environment, clear=True),
            patch.object(scope["subprocess"], "run", return_value=proof_pane),
        ):
            with self.assertRaisesRegex(RuntimeError, "interactive terminal"):
                confirm("approve? ")

        shell_pane = subprocess.CompletedProcess(
            [], 0, json.dumps([{"id": 7, "tab_name": "shell"}]), ""
        )
        with (
            patch.object(scope["sys"], "stdin", stdin),
            patch.object(scope["sys"], "stdout", stdout),
            patch.dict(scope["os"].environ, environment, clear=True),
            patch.object(scope["subprocess"], "run", return_value=shell_pane),
            patch("builtins.input", return_value="yes"),
        ):
            self.assertTrue(confirm("approve? "))

        external_zellij = {"ZELLIJ_SESSION_NAME": "personal-workspace"}
        with (
            patch.object(scope["sys"], "stdin", stdin),
            patch.object(scope["sys"], "stdout", stdout),
            patch.dict(scope["os"].environ, external_zellij, clear=True),
            patch.object(scope["subprocess"], "run") as run,
            patch("builtins.input", return_value="yes"),
        ):
            self.assertTrue(confirm("approve? "))
        run.assert_not_called()

    def test_audience_mode_is_saved_and_broadcast_to_open_panes(self):
        rondo = load_script("rondo", self.config, self.cache)
        rondo["write_setting"]("panels", "claude codex")
        scope = rondo["audience_command"].__globals__
        sender = unittest.mock.Mock()
        with (
            patch.dict(scope["os"].environ, {"ZELLIJ_SESSION_NAME": "rondo-project"}),
            patch.dict(scope, {
                "send_agent_message": sender,
                "agent_panes": lambda: {"claude": "1", "codex": "2"},
            }),
        ):
            rondo["audience_command"]("guided")

        path = self.config / "rondo" / "audience"
        self.assertEqual(path.read_text().strip(), "guided")
        self.assertEqual([call.args[0] for call in sender.call_args_list], ["claude", "codex"])
        self.assertTrue(all("Rondo audience update" in call.args[1][0] for call in sender.call_args_list))

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

    def test_unknown_command_is_rejected_instead_of_creating_a_session(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["main"].__globals__
        opener = unittest.mock.Mock()
        with (
            patch.dict(scope, {"open_session": opener}),
            patch.object(scope["sys"], "argv", ["rondo", "prooof"]),
        ):
            with self.assertRaisesRegex(RuntimeError, "proof"):
                rondo["main"]()
        opener.assert_not_called()

    def test_open_session_requires_a_git_repository(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["open_session"].__globals__
        with (
            patch.dict(scope, {"repo_root": lambda: self.base}),
            patch.object(scope["shutil"], "which", return_value="/bin/zellij"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Git"):
                rondo["open_session"]()

    def test_missing_configured_agent_is_skipped(self):
        rondo = load_script("rondo", self.config, self.cache)
        rondo["write_setting"]("panels", "claude kimi")
        scope = rondo["open_session"].__globals__
        layouts = []
        with (
            patch.dict(scope, {
                "repo_root": lambda: self.base,
                "require_git_repo": lambda _root: None,
                "git_policy": lambda _root: "direct",
                "zellij_sessions": lambda: (set(), set()),
                "installed": lambda name: name == "claude",
                "write_layout": lambda panels: layouts.append(panels) or self.base / "layout.kdl",
            }),
            patch.object(scope["shutil"], "which", return_value="/bin/zellij"),
            patch.object(scope["os"], "chdir"),
            patch.object(scope["os"], "execvp", side_effect=RuntimeError("stop")),
        ):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                rondo["open_session"]()
        self.assertEqual(layouts, [["claude"]])

    def test_session_list_only_shows_rondo_sessions(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["list_sessions"].__globals__
        with patch.dict(scope, {
            "zellij_sessions": lambda: ({"rondo-project", "other"}, {"rondo-old"}),
            "repo_root": lambda: self.base,
            "git_output": lambda _root, *args: "false",
        }):
            rondo["list_sessions"]()
        output = self.output.getvalue()
        self.assertIn("rondo-project", output)
        self.assertIn("rondo-old", output)
        self.assertNotIn("other", output)

    def test_kill_only_targets_a_named_rondo_session(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["kill_session"].__globals__
        with (
            patch.dict(scope, {"zellij_sessions": lambda: ({"rondo-project"}, set())}),
            patch.object(scope["subprocess"], "run") as run,
        ):
            rondo["kill_session"]("rondo-project")
        run.assert_called_once_with(
            ["zellij", "delete-session", "--force", "rondo-project"], check=True
        )
        with self.assertRaises(RuntimeError):
            rondo["kill_session"]("unrelated")

    def test_clean_removes_only_caches_for_deleted_repositories(self):
        rondo = load_script("rondo", self.config, self.cache)
        cache = rondo["CACHE_DIR"]
        missing = self.base / "deleted"
        cache.mkdir(parents=True)
        (cache / "claude.dead.json").write_text(json.dumps({"project": str(missing)}))
        stale = cache / "proof" / "stale"
        stale.mkdir(parents=True)
        (stale / "latest.json").write_text(json.dumps({"root": str(missing)}))
        live = cache / "proof" / "live"
        live.mkdir(parents=True)
        (live / "latest.json").write_text(json.dumps({"root": str(self.base)}))
        stale_key = "a" * 16
        stale_knowledge = cache / "knowledge" / stale_key
        stale_knowledge.mkdir(parents=True)
        (stale_knowledge / "state.json").write_text(json.dumps({"root": str(missing)}))
        audience = cache / "audience"
        audience.mkdir()
        stale_guidance = audience / f"kimi-default-{stale_key}.md"
        stale_guidance.write_text("private memory")

        self.assertEqual(rondo["clean_cache"](), 3)
        self.assertFalse((cache / "claude.dead.json").exists())
        self.assertFalse(stale.exists())
        self.assertFalse(stale_knowledge.exists())
        self.assertFalse(stale_guidance.exists())
        self.assertTrue(live.exists())

    @unittest.skipIf(os.name == "nt", "creating symbolic links may require Windows privileges")
    def test_clean_never_follows_a_cache_section_symbolic_link(self):
        rondo = load_script("rondo", self.config, self.cache)
        cache = rondo["CACHE_DIR"]
        cache.mkdir(parents=True)
        outside = self.base / "outside"
        child = outside / ("b" * 16)
        child.mkdir(parents=True)
        sentinel = child / "sentinel.txt"
        sentinel.write_text("keep")
        (child / "state.json").write_text(json.dumps({
            "root": str(self.base / "deleted")
        }))
        (cache / "knowledge").symlink_to(outside, target_is_directory=True)

        self.assertEqual(rondo["clean_cache"](), 0)
        self.assertTrue(sentinel.exists())

    def test_pr_without_origin_reports_the_missing_remote(self):
        rondo = load_script("rondo", self.config, self.cache)
        scope = rondo["pr_command"].__globals__
        with patch.dict(scope, {
            "repo_root": lambda: self.base,
            "require_git_repo": lambda _root: None,
            "git_origin": lambda _root: "",
        }):
            with self.assertRaisesRegex(RuntimeError, "origin"):
                rondo["pr_command"]([])

    def test_status_bar_compacts_whole_agents_before_truncating(self):
        from rondo.model import Snapshot, Window

        status = load_script("ai-status", self.config, self.cache)
        reset = time.time() + 3600
        adapters = []
        for name in ("claude", "codex", "gemini"):
            adapter = unittest.mock.Mock()
            adapter.snapshot.return_value = Snapshot(
                name, f"{name}-very-long-model high",
                [Window("5h", 93, reset), Window("wk", 53, reset)],
            )
            adapters.append((name, adapter))
        scope = status["line"].__globals__
        with patch.dict(scope, {
            "AGENTS": adapters,
            "open_panes": lambda: None,
            "relay_field": lambda _root: None,
        }):
            text = status["line"](self.base, 60)

        self.assertLess(len(text), 60)
        self.assertTrue(all(name in text for name in ("cl", "cx", "gm")))
        self.assertGreaterEqual(text.count("%"), 3)


class AgentSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.runner = load_script("rondo-agent-session", self.base / "config", self.base / "cache")
        from rondo import knowledge as knowledge_lib
        self.knowledge = knowledge_lib
        self.knowledge_cache = patch.object(
            knowledge_lib, "CACHE", self.base / "cache" / "rondo"
        )
        self.knowledge_cache.start()

    def tearDown(self):
        self.knowledge_cache.stop()
        self.temp.cleanup()

    def test_claude_resumes_and_falls_back_when_no_session_exists(self):
        packet = self.base / "handoff.md"
        packet.write_text("continue")
        scope = self.runner["run"].__globals__
        missing = subprocess.CompletedProcess([], 1)
        fresh = subprocess.CompletedProcess([], 0)
        environment = {
            "RONDO_RESUME_AGENT": "claude",
            "RONDO_HANDOFF_FILE": str(packet),
            "RONDO_LANG": "en",
        }
        with (
            patch.dict(scope["os"].environ, environment, clear=False),
            patch.object(scope["shutil"], "which", side_effect=lambda name: f"/bin/{name}" if name == "claude" else None),
            patch.object(scope["subprocess"], "run", side_effect=[missing, fresh]) as run,
        ):
            self.assertEqual(self.runner["run"]("claude", []), 0)
        self.assertEqual(run.call_args_list[0].args[0][:2], ["/bin/claude", "--continue"])
        self.assertEqual(run.call_args_list[1].args[0][0], "/bin/claude")
        self.assertIn(str(packet), run.call_args_list[0].args[0][-1])

    def test_codex_resumes_latest_session_for_the_current_directory(self):
        scope = self.runner["run"].__globals__
        done = subprocess.CompletedProcess([], 0)
        with (
            patch.dict(scope["os"].environ, {}, clear=True),
            patch.object(scope["shutil"], "which", side_effect=lambda name: f"/bin/{name}" if name == "codex" else None),
            patch.object(scope["subprocess"], "run", return_value=done) as run,
        ):
            self.assertEqual(self.runner["run"]("codex", []), 0)
        command = run.call_args.args[0]
        self.assertEqual(command[0], "/bin/codex")
        self.assertIn("resume", command)
        self.assertIn("--last", command)

    def test_agent_session_exports_implementation_identity(self):
        scope = self.runner["run"].__globals__
        done = subprocess.CompletedProcess([], 0)
        with (
            patch.dict(scope["os"].environ, {}, clear=True),
            patch.object(scope["shutil"], "which", side_effect=lambda name: f"/bin/{name}" if name == "codex" else None),
            patch.object(scope["subprocess"], "run", return_value=done),
        ):
            self.assertEqual(self.runner["run"]("codex", []), 0)
            self.assertEqual(scope["os"].environ["RONDO_AGENT"], "codex")
            self.assertEqual(len(scope["os"].environ["RONDO_AGENT_SESSION"]), 32)

    def test_audience_guidance_uses_each_cli_native_entry_point(self):
        commands = self.runner["session_commands"]
        claude = commands("claude", "nondev")
        codex = commands("codex", "nondev")
        gemini = commands("gemini", "nondev")
        kimi = commands("kimi", "nondev")
        grok = commands("grok", "nondev")

        self.assertIn("--append-system-prompt", claude[0])
        self.assertTrue(any(value.startswith("developer_instructions=") for value in codex[0]))
        self.assertIn("--prompt-interactive", gemini[1])
        self.assertIn("--agent-file", kimi[1])
        self.assertIn("--rules", grok[1])
        agent_file = Path(kimi[1][-1])
        self.assertIn("${base_prompt}", agent_file.read_text())
        if os.name != "nt":
            self.assertEqual(agent_file.stat().st_mode & 0o777, 0o600)

    def test_natural_requests_are_mapped_to_rondo_actions_for_every_agent(self):
        for agent in ("claude", "codex", "gemini", "kimi", "grok"):
            resume, fresh, _ = self.runner["session_commands"](
                agent, "default", root=self.base
            )
            text = " ".join(resume or fresh)
            if agent == "kimi":
                path = Path(fresh[fresh.index("--agent-file") + 1])
                text = path.read_text()
            self.assertIn("rondo learn memory", text)
            self.assertIn("rondo test", text)
            self.assertIn("rondo code-review all", text)

    def test_only_approved_knowledge_reaches_agent_native_entry_points(self):
        memory = self.knowledge.propose(
            self.base, "memory", "Public APIs require a compatibility note.",
            source="codex",
        )
        skill = self.knowledge.propose(
            self.base,
            "skill",
            "Run the release checks first.\nNever auto-include PRIVATE_SECOND_STEP.",
            name="release-check",
            source="claude",
        )
        before = " ".join(self.runner["session_commands"](
            "codex", "default", root=self.base
        )[1])
        self.assertNotIn("compatibility note", before)

        self.knowledge.approve(self.base, memory["id"], actor="human")
        self.knowledge.approve(self.base, skill["id"], actor="human")
        for agent in ("claude", "codex", "gemini", "kimi", "grok"):
            resume, fresh, _ = self.runner["session_commands"](
                agent, "default", root=self.base
            )
            command = " ".join(resume or fresh)
            if agent == "kimi":
                command = Path(fresh[fresh.index("--agent-file") + 1]).read_text()
            self.assertIn("compatibility note", command)
            self.assertIn("Run the release checks first.", command)
            self.assertNotIn("PRIVATE_SECOND_STEP", command)

        other = self.base / "other-repo"
        other.mkdir()
        other_memory = self.knowledge.propose(
            other, "memory", "This repository uses a separate release train."
        )
        self.knowledge.approve(other, other_memory["id"], actor="human")
        first_fresh = self.runner["session_commands"](
            "kimi", "default", root=self.base
        )[1]
        other_fresh = self.runner["session_commands"](
            "kimi", "default", root=other
        )[1]
        first_file = Path(first_fresh[first_fresh.index("--agent-file") + 1])
        other_file = Path(other_fresh[other_fresh.index("--agent-file") + 1])
        self.assertNotEqual(first_file, other_file)
        self.assertNotIn("compatibility note", other_file.read_text())

    def test_workspace_approval_uses_each_cli_native_mode(self):
        commands = self.runner["session_commands"]
        self.assertIn("acceptEdits", commands("claude", "default", "workspace")[1])
        self.assertIn("--approve-for-me", commands("codex", "default", "workspace")[1])
        self.assertIn("accept-edits", commands("gemini", "default", "workspace")[1])
        self.assertIn("--auto", commands("kimi", "default", "workspace")[1])
        self.assertIn("auto", commands("grok", "default", "workspace")[1])

    def test_git_pr_policy_is_added_to_every_agent_prompt(self):
        commands = self.runner["session_commands"]
        scope = commands.__globals__
        with patch.dict(scope["os"].environ, {"RONDO_GIT_POLICY": "review"}):
            for agent in ("claude", "codex", "gemini", "kimi", "grok"):
                resume, fresh, _ = commands(agent, "default", "ask")
                text = " ".join(resume or fresh)
                if agent == "kimi":
                    path = Path(fresh[fresh.index("--agent-file") + 1])
                    text = path.read_text()
                self.assertIn("Rondo Git policy", text)


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

    def test_auto_relay_downgrades_when_codex_needs_user_input(self):
        relay = load_script("rondo-relay", self.config, self.cache)
        directory = relay["relay_dir"](self.repo)
        packet = directory / "packets" / "handoff.md"
        packet.parent.mkdir(parents=True)
        packet.write_text("handoff")
        blocked = subprocess.CompletedProcess([], relay["PANE_NOT_READY"], "", "trust prompt")
        scope = relay["run_auto"].__globals__

        with patch.object(scope["subprocess"], "run", return_value=blocked):
            self.assertEqual(relay["run_auto"](directory, packet, self.repo), 0)

        self.assertEqual((relay["CONFIG_DIR"] / "relay").read_text().strip(), "ready")
        index = json.loads((directory / "pending.json").read_text())
        self.assertEqual(index["status"], "ready")
        self.assertIn("user decision", index["reason"])

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
