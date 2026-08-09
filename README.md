# Rondo

> One project. Every coding agent. One continuous thread.

[한국어](README.ko.md)

Rondo keeps Claude Code, Codex, Gemini, Kimi, and Grok in one persistent terminal workspace. It removes window juggling, shows local usage state, makes agent-to-agent delegation visible, and carries unfinished work from Claude to Codex when Claude reaches its usage limit.

It provides:

- one persistent workspace per Git project;
- interactive Korean / English setup and agent selection;
- one explanation level shared by every agent pane;
- a shared status bar for models, usage, and relay state;
- visible prompts between agent panes through `rondo send`;
- element-scoped frontend requests through Rondo Lens;
- executable evidence and a risk-based human review queue through Rondo Proof;
- opt-in Claude → Codex continuity at the usage limit.

Rondo is local-first. It reads the files that each installed CLI already stores on your machine and does not add a hosted service, account, or API key.

## Install

### macOS / Linux

```sh
curl -fsSL https://raw.githubusercontent.com/ppupy1209/rondo/main/install.sh | sh
```

Python 3.10+ is the only runtime requirement. The installer downloads Rondo and Zellij, creates the commands in `~/.local/bin`, and adds that directory to your shell `PATH`.

### Windows

Open PowerShell and run:

```powershell
irm https://raw.githubusercontent.com/ppupy1209/rondo/main/install.ps1 | iex
```

The Windows installer downloads Rondo and native Zellij. If Python 3.10+ is missing, it installs Python through WinGet. WSL is not required. Open a new terminal after installation.

On every platform, install at least one agent CLI you want to use. Rondo discovers the installed agents during setup; you do not need to install every supported CLI.

Then run:

```sh
rondo setup
rondo
```

To install from an existing clone instead, run `sh install.sh` on macOS/Linux or `.\install.ps1` in PowerShell. Rerun the same installer to update or repair an installation.

Existing `ai-tools` installations are migrated on first run. The old `ai`, `ai-status`, and `claude-statusline` commands remain compatibility aliases.

## Quick start

```sh
cd ~/projects/my-project
rondo             # open or attach to the project's persistent workspace
rondo setup       # choose language, explanation level, agents, and relay behavior
rondo audience    # change how every agent explains its results
rondo add         # select and add another agent pane
rondo send codex "Review the current diff"  # type and submit in the Codex pane
rondo lens        # click a UI element and send its focused context
rondo proof       # run checks and build a risk-based review packet
rondo doctor      # diagnose dependencies and configuration
```

`rondo setup` is a real selector: move with arrow keys, toggle agents with Space, and save with Enter. Agent names and explanation levels never need to be typed.

```text
┌────────────────────────────────────────────────────┐
│ claude 42%   codex 88%   gemini 61%   relay ready │
├────────────────────────┬───────────────────────────┤
│                        │          codex            │
│        claude          ├───────────────────────────┤
│                        │          gemini           │
└────────────────────────┴───────────────────────────┘
  tabs: agents | shell
```

The first selected agent gets the left half. Additional agents stack on the right. Detaching or closing the terminal does not stop the zellij session.

## Audience-aware explanations

Rondo gives every selected agent the same explanation level without changing engineering quality, permissions, or implementation behavior.

| Level | Explanation style |
|---|---|
| `default` | Keep each agent's normal response style |
| `nondev` | Start with the practical outcome, define jargon, and use a concrete example and simple flow |
| `guided` | Assume general development knowledge, but explain the unfamiliar technology's role, mechanics, rationale, and a key tradeoff |

Choose the level during setup or change it later:

```sh
rondo audience nondev
rondo audience guided
rondo audience default
```

Every agent pane started by Rondo receives the saved level automatically, including supported restored sessions. When `rondo audience` runs inside an active Rondo session, the update is also entered visibly into every open agent pane and applies to future replies. For unattended setup, use `RONDO_AUDIENCE=default|nondev|guided`.

## Visible agent delegation

`rondo send` finds an open agent pane, pastes the message into its interactive CLI, and submits it with Enter. The request appears in the target pane exactly where a manually entered prompt would appear; Rondo does not start a hidden copy of the agent.

```sh
rondo send codex "Review the current diff and finish the tests"
rondo send claude "Check the proposed API design"
rondo send gemini "Research another implementation approach"
```

Run the command inside a Rondo session, with the target pane open. An agent can invoke the same command through its shell tool, so manual prompts, agent delegation, and automatic relay all use one visible input path.

## Rondo Lens

Lens turns a visual frontend request into an element-scoped prompt. Run it from the Rondo shell tab, point at the UI in the dedicated browser window, and click the element you want changed.

```sh
rondo lens                              # defaults to http://localhost:3000/
rondo lens http://localhost:5173/
rondo lens https://staging.example.com --allow-remote
```

Hover gives immediate element highlighting. Click selects, Esc cancels, and the terminal then asks for the instruction and receiving agent. Before anything is sent, Rondo shows the URL, selector, included data, destination, and a `y/N` confirmation. The visible prompt in the agent pane contains your instruction and a path to the focused context packet.

The packet includes a cropped screenshot around the selection, sanitized DOM and visible text, a small computed-style set, and accessibility metadata. Form values are removed from the DOM and masked during the screenshot. Cookies, browser storage, credentials, and full-page screenshots are never read. Localhost is the default boundary; remote pages require the explicit `--allow-remote` flag.

Lens launches an isolated Chrome, Chromium, or Microsoft Edge profile and deletes that temporary profile when the selection ends. Set `RONDO_BROWSER=/path/to/browser` if the browser is not discovered automatically.

## Rondo Proof

Proof replaces a full-diff handoff with executable evidence and a queue containing only the decisions that still need a person.

```sh
rondo task "Improve login error messages" \
  --accept "Invalid passwords show an error" \
  --accept "Successful login still works" \
  --avoid "Do not change the authentication API" \
  --scope web

rondo proof                    # run checks and build an evidence packet
rondo review --budget 2m       # show highest-risk items that fit two minutes
rondo proof --reviewer codex   # open a separate read-only Codex verifier
```

Rondo classifies changed files as low, medium, or high risk. Authentication, permissions, payments, migrations, security, deployment paths, and changes outside the declared scope are high risk. Documentation and test-only changes are low risk. Python unittest, npm test/lint, Gradle, Cargo, and Go checks are discovered from project files; add task-specific commands with `--check "command"`.

The independent reviewer starts in a fresh pane without the implementer's conversation. Codex uses a read-only sandbox and Claude uses plan permissions. It is instructed to inspect the actual diff, challenge the evidence, and find the strongest counterexample without editing implementation code. `ready` means approval candidate, not automatic approval; sensitive changes always remain in the human queue.

Task intent and proof packets stay under `~/.cache/rondo/proof/` with mode `0600` and are not committed. Check output can contain project data, so inspect a packet before sharing it outside the machine.

## Handoff and resume

Rondo restores work differently depending on where you continue.

### Same computer, including after a reboot

Run `rondo` again in the same repository. Rondo resurrects the saved zellij workspace, then Claude Code continues the latest conversation for that directory with `--continue` and Codex continues it with `resume --last`. If a provider has no saved conversation, its pane starts a fresh one instead.

### Another computer

Before leaving computer A, create a small provider-neutral handoff:

```sh
rondo handoff "Finish the login tests and review the current diff"
git add .rondo/handoff.md
git commit -m "docs: add Rondo handoff"
git push
```

After cloning or pulling on computer B:

```sh
rondo resume codex       # or: rondo resume claude
```

The target pane receives a visible prompt pointing to `.rondo/handoff.md`. The file contains only your note, origin, branch, HEAD, working-tree filenames/statistics, and recent commits. Rondo does not copy vendor transcripts, credentials, or local paths into Git. Uncommitted code is not transferred, so commit and push the actual work as well as the handoff file.

## How it works

1. `rondo` resolves the current Git root and keys one zellij session by its `origin` URL plus the local clone path.
2. It builds a layout from `~/.config/rondo/panels` and launches each native CLI in the same working tree. Saved zellij sessions and supported vendor conversations are resumed after a reboot.
3. `rondo-status` reads local CLI state every five seconds and renders only the panes that are open.
4. `rondo send` targets a pane by its Rondo name and submits a visible prompt through zellij.
5. `rondo lens` captures one selected UI element into a private local packet and sends it only after confirmation.
6. `rondo proof` runs discovered checks, classifies risk, and keeps only unresolved decisions in the human review queue.
7. Session wrappers and supported lifecycle hooks update an optional repository handoff log after an agent exits.
8. At Claude's usage threshold, the continuity relay prepares a local packet and can send it to the existing Codex pane.

The agents do not share a vendor chat session. They share the real project directory, Git state, a persistent terminal workspace, and a small provider-neutral continuity packet.

## Continuity Relay

Claude Code exposes its current model, rate limits, session ID, and transcript path to a local status-line command. Rondo uses that signal when either active limit reaches 1% remaining.

```sh
rondo relay             # show mode and pending packet
rondo relay ready       # prepare a packet; wait for explicit continuation (default)
rondo relay auto        # send the handoff to the existing Codex pane immediately
rondo relay off         # usage display only
rondo continue          # send a pending handoff to the existing Codex pane
```

A continuity packet contains:

- the latest user and Claude messages, capped to a small excerpt;
- branch, HEAD, working-tree status, diff statistics, and recent commits;
- a handoff contract telling Codex to inspect current work, avoid redoing it, validate the result, and avoid remote or destructive actions.

Packets live under `~/.cache/rondo/relay/`, use file mode `0600`, redact common token formats, and are deduplicated per Claude session and reset window. They are never committed. In `ready` mode, nothing is sent to Codex until you run `rondo continue`.

`auto` is deliberately opt-in and requires Codex to be selected as a pane. Rondo types a visible handoff prompt into that pane and submits it exactly like terminal input. The prompt points to the private packet, which carries the current intent, Git state, and safety contract.

## Supported agents

| Pane | Executable | Status source |
|---|---|---|
| Claude Code | `claude` | Claude status-line JSON |
| Codex CLI | `codex` | local thread SQLite + rollout rate-limit snapshots |
| Gemini / Antigravity | `agy` | local conversation DB + cached `/usage` output |
| Kimi Code | `kimi` | pane presence only |
| Grok Build | `grok` | pane presence only |

Rondo never reads saved credentials or calls a vendor API directly. Gemini's own `agy -p "/usage"` command runs in the background at most once every ten minutes while its pane is open.

## Commands

| Command | Purpose |
|---|---|
| `rondo` | Open or attach to the current project's session |
| `rondo setup` | Choose language, explanation level, panes, and relay mode |
| `rondo audience [default\|nondev\|guided]` | Change how every agent explains its results |
| `rondo add [agent]` | Add an agent pane; omit the name to select interactively |
| `rondo send <agent> <message>` | Type and submit a visible prompt in that agent's pane |
| `rondo task <goal> [options]` | Record acceptance criteria, boundaries, scope, and checks |
| `rondo proof [--reviewer agent]` | Run checks and build an independent review packet |
| `rondo review [--budget 2m]` | Show the highest-risk human decisions within a time budget |
| `rondo handoff [note]` | Create `.rondo/handoff.md` for another computer |
| `rondo resume [claude\|codex]` | Open the workspace and deliver the handoff to one agent |
| `rondo lens [URL]` | Click a UI element and send its focused context after confirmation |
| `rondo language` | Switch Korean / English |
| `rondo relay [off\|ready\|auto]` | Inspect or change the continuity strategy |
| `rondo continue` | Send the pending handoff to the existing Codex pane |
| `rondo doctor` | Check zellij, agents, and configuration |
| `rondo -l` | List persistent sessions |
| `handoff --init` | Enable the optional Git handoff log on macOS/Linux |

Inside zellij: `Ctrl+p` + arrows moves panes, `Ctrl+t` + arrows moves tabs, and `Ctrl+o` then `d` detaches.

## Optional commit history log

This is separate from the cross-computer `rondo handoff` command above. On macOS/Linux, `handoff --init` creates `docs/handoff.md`. On session end, Rondo records commit subjects made since the previous handoff. It keeps the latest 20 entries in the active section and archives older entries instead of deleting them. This optional shell-based log is not installed on Windows; `rondo handoff` and `rondo resume` work on Windows too.

The target lookup order is `$HANDOFF_FILE`, `docs/collab/status.md`, then `docs/handoff.md`. Repositories without one of these files are left untouched.

## Configuration and privacy

```text
~/.config/rondo/
  language       ko | en
  audience       default | nondev | guided
  panels         selected agent names
  relay          off | ready | auto
  threshold      remaining percentage (default: 1)

~/.cache/rondo/
  layout.kdl     generated zellij layout
  audience/      private launch guidance for CLIs that use a local agent file
  claude.*       local display cache
  lens/          private element context packets and cropped screenshots
  proof/         private task intent, evidence packets, and review queues
  relay/         private continuity packets and delivery logs
```

For non-interactive setup, set `RONDO_LANG=ko|en`, `RONDO_AUDIENCE=default|nondev|guided`, `RONDO_PANELS=claude,codex,...`, and `RONDO_RELAY=off|ready|auto` before running `rondo setup`.

No telemetry is included. Rondo does not store credentials. A relay excerpt can contain conversation text, so use `ready` mode when work must not cross providers without an explicit action.

## Development

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile bin/rondo bin/rondo-agent-session bin/rondo-lens bin/rondo-relay bin/rondo-claude-status bin/ai-status
sh -n install.sh bin/ai bin/rondo-status bin/*-session
```

GitHub Actions runs the Python suite and installer smoke tests on macOS, Linux, and Windows.

## License

MIT
