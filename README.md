# Rondo

> One project. Every coding agent. One continuous thread.

[한국어](README.ko.md)

Rondo keeps Claude Code, Codex, Gemini, Kimi, and Grok in one persistent terminal workspace. It removes window juggling, shows local usage state, makes agent-to-agent delegation visible, and carries unfinished work from Claude to Codex when Claude reaches its usage limit.

It provides:

- one persistent workspace per Git project;
- interactive Korean / English setup and agent selection;
- a shared status bar for models, usage, and relay state;
- visible prompts between agent panes through `rondo send`;
- element-scoped frontend requests through Rondo Lens;
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
rondo setup       # choose language, agents, and relay behavior
rondo add         # select and add another agent pane
rondo send codex "Review the current diff"  # type and submit in the Codex pane
rondo lens        # click a UI element and send its focused context
rondo doctor      # diagnose dependencies and configuration
```

`rondo setup` is a real selector: move with arrow keys, toggle agents with Space, and save with Enter. Agent names never need to be typed.

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

## How it works

1. `rondo` resolves the current Git root and maps it to one zellij session.
2. It builds a layout from `~/.config/rondo/panels` and launches each native CLI in the same working tree.
3. `rondo-status` reads local CLI state every five seconds and renders only the panes that are open.
4. `rondo send` targets a pane by its Rondo name and submits a visible prompt through zellij.
5. `rondo lens` captures one selected UI element into a private local packet and sends it only after confirmation.
6. Session wrappers and supported lifecycle hooks update an optional repository handoff log after an agent exits.
7. At Claude's usage threshold, the continuity relay prepares a local packet and can send it to the existing Codex pane.

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
| `rondo setup` | Choose language, panes, and relay mode |
| `rondo add [agent]` | Add an agent pane; omit the name to select interactively |
| `rondo send <agent> <message>` | Type and submit a visible prompt in that agent's pane |
| `rondo lens [URL]` | Click a UI element and send its focused context after confirmation |
| `rondo language` | Switch Korean / English |
| `rondo relay [off\|ready\|auto]` | Inspect or change the continuity strategy |
| `rondo continue` | Send the pending handoff to the existing Codex pane |
| `rondo doctor` | Check zellij, agents, and configuration |
| `rondo -l` | List persistent sessions |
| `handoff --init` | Enable the optional Git handoff log on macOS/Linux |

Inside zellij: `Ctrl+p` + arrows moves panes, `Ctrl+t` + arrows moves tabs, and `Ctrl+o` then `d` detaches.

## Optional Git handoff log

On macOS/Linux, run `handoff --init` in a repository to create `docs/handoff.md`. On session end, Rondo records commit subjects made since the previous handoff. It keeps the latest 20 entries in the active section and archives older entries instead of deleting them. This optional shell-based log is not installed on Windows; the shared workspace, visible delegation, Lens, and continuity relay are available there.

The target lookup order is `$HANDOFF_FILE`, `docs/collab/status.md`, then `docs/handoff.md`. Repositories without one of these files are left untouched.

## Configuration and privacy

```text
~/.config/rondo/
  language       ko | en
  panels         selected agent names
  relay          off | ready | auto
  threshold      remaining percentage (default: 1)

~/.cache/rondo/
  layout.kdl     generated zellij layout
  claude.*       local display cache
  lens/          private element context packets and cropped screenshots
  relay/         private continuity packets and delivery logs
```

For non-interactive setup, set `RONDO_LANG=ko|en`, `RONDO_PANELS=claude,codex,...`, and `RONDO_RELAY=off|ready|auto` before running `rondo setup`.

No telemetry is included. Rondo does not store credentials. A relay excerpt can contain conversation text, so use `ready` mode when work must not cross providers without an explicit action.

## Development

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile bin/rondo bin/rondo-lens bin/rondo-relay bin/rondo-claude-status bin/ai-status
sh -n install.sh bin/ai bin/rondo-status bin/*-session
```

GitHub Actions runs the Python suite and installer smoke tests on macOS, Linux, and Windows.

## License

MIT
