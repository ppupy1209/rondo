# Rondo

> One project. Every coding agent. One continuous thread.

[한국어](README.ko.md)

Rondo keeps Claude Code, Codex, Gemini, Kimi, and Grok in one persistent terminal workspace. It removes window juggling, shows each agent's local usage state, and carries unfinished work from Claude to Codex when Claude reaches its usage limit.

Rondo is local-first. It reads the files that each installed CLI already stores on your machine and does not add a hosted service, account, or API key.

## Install

Requirements: macOS or Linux, Python 3.9+, Git, and [zellij](https://zellij.dev/).

```sh
git clone https://github.com/ppupy1209/rondo.git ~/rondo
sh ~/rondo/install.sh
rondo setup
```

The installer creates symlinks in `~/.local/bin`, so `git -C ~/rondo pull` updates the installation immediately. Make sure `~/.local/bin` is in `PATH`.

Existing `ai-tools` installations are migrated on first run. The old `ai`, `ai-status`, and `claude-statusline` commands remain compatibility aliases.

After pulling this rename into an existing clone, run `sh ~/ai-tools/install.sh` once so the new `rondo*` command symlinks are added. The clone directory itself may stay named `ai-tools`.

## Quick start

```sh
cd ~/projects/my-project
rondo             # open or attach to the project's persistent workspace
rondo setup       # choose language, agents, and relay behavior
rondo add         # select and add another agent pane
rondo send codex "Review the current diff"  # type and submit in the Codex pane
rondo doctor      # diagnose dependencies and configuration
```

`rondo setup` is a real selector: move with arrow keys, toggle agents with Space, and save with Enter. Agent names never need to be typed.

Any agent can run `rondo send` through its shell tool. Manual prompts, agent delegation, and automatic relay therefore use the same visible terminal-input path.

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

## How it works

1. `rondo` resolves the current Git root and maps it to one zellij session.
2. It builds a layout from `~/.config/rondo/panels` and launches each native CLI in the same working tree.
3. `rondo-status` reads local CLI state every five seconds and renders only the panes that are open.
4. Session wrappers and supported lifecycle hooks update an optional repository handoff log after an agent exits.
5. Agents can send visible prompts to one another with `rondo send`; automatic Claude → Codex relay uses the same path.

The agents do not share a vendor chat session. They share the real project directory, Git state, a persistent terminal workspace, and a small provider-neutral continuity packet.

## Continuity Relay

Claude Code exposes its current model, rate limits, session ID, and transcript path to a local status-line command. Rondo uses that signal when either active limit reaches 1% remaining.

```sh
rondo relay             # show mode and pending packet
rondo relay ready       # prepare a packet; wait for explicit continuation (default)
rondo relay auto        # let Codex continue immediately
rondo relay off         # usage display only
rondo continue          # open pending work in interactive Codex
```

A continuity packet contains:

- the latest user and Claude messages, capped to a small excerpt;
- branch, HEAD, working-tree status, diff statistics, and recent commits;
- a handoff contract telling Codex to inspect current work, avoid redoing it, validate the result, and avoid remote or destructive actions.

Packets live under `~/.cache/rondo/relay/`, use file mode `0600`, redact common token formats, and are deduplicated per Claude session and reset window. They are never committed. In `ready` mode, nothing is sent to Codex until you run `rondo continue`.

`auto` is deliberately opt-in. Rondo types a visible handoff prompt into the existing Codex pane and submits it exactly like terminal input. The prompt points to the private packet and keeps the safety contract visible to Codex.

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
| `rondo language` | Switch Korean / English |
| `rondo relay [off\|ready\|auto]` | Inspect or change the continuity strategy |
| `rondo continue` | Claim the pending packet in interactive Codex |
| `rondo doctor` | Check zellij, agents, and configuration |
| `rondo -l` | List persistent sessions |
| `handoff --init` | Enable the optional Git handoff log in a repository |

Inside zellij: `Ctrl+p` + arrows moves panes, `Ctrl+t` + arrows moves tabs, and `Ctrl+o` then `d` detaches.

## Optional Git handoff log

Run `handoff --init` in a repository to create `docs/handoff.md`. On session end, Rondo records commit subjects made since the previous handoff. It keeps the latest 20 entries in the active section and archives older entries instead of deleting them.

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
  relay/         private continuity packets and Codex logs
```

No telemetry is included. Rondo does not store credentials. A relay excerpt can contain conversation text, so use `ready` mode when work must not cross providers without an explicit action.

## Development

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile bin/rondo bin/rondo-relay bin/rondo-claude-status bin/ai-status
sh -n install.sh bin/ai bin/rondo-status bin/*-session
```

## License

MIT
