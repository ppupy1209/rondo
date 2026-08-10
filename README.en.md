# Rondo

Rondo does not replace Codex CLI, Claude Code, or Gemini CLI. It is a small companion that keeps project context moving between their native interfaces, hands work to another AI after a clear quota stop, and separates implementation from final verification.

## What remains in 0.15

- Only Codex, Claude, and Gemini; enable or disable each with `rondo setup`.
- Bounded project-local context containing goals, checkpoints, changed-file summaries, handoffs, and review results.
- Automatic failover only after an explicit quota-exhaustion message is observed twice.
- A session that implemented the change cannot approve its final review.
- Checkpoints, messages, handoffs, and review requests are visible as text in the Relay tab.

Rondo does not ingest full conversations or hidden reasoning, store provider credentials, run a server, or call a model API.

## Install

Install and sign in to at least one official provider CLI first: `codex`, `claude`, or `gemini`.

Windows PowerShell:

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/ppupy1209/rondo/v0.15.2/install.ps1))) -Version v0.15.2
```

macOS / Linux:

```sh
curl -fsSL https://raw.githubusercontent.com/ppupy1209/rondo/v0.15.2/install.sh | RONDO_VERSION=v0.15.2 sh
```

The installer checks for Python 3.10+ and installs a SHA-256-verified Zellij 0.44.3 build. It never installs or updates provider CLIs.

## First run

Run `rondo` in any project directory. On the first run, move with the arrow keys, toggle AIs with `Space`, and finish with `Enter`; no agent names need to be typed. Later runs enter that project's tabs immediately.

Enabled Claude, Codex, and Gemini CLIs share one `Agents` tab as equal-width split panes. Click a pane or press `Ctrl+p` followed by an arrow key to move between AIs. Relay remains a separate tab; use `Ctrl+t` followed by an arrow key to switch to it. Rondo starts Zellij with mouse support enabled and normal mode selected.

On macOS and Linux, Rondo uses a short private Zellij socket path so long project or temporary paths cannot trigger the misleading `session name must be less than 0 characters` error.

## Typical flow

```text
rondo task "Implement the login API"
rondo checkpoint "Login API implemented; integration tests remain"
rondo next codex
```

Codex reads `.rondo/context.md` and continues. When implementation is ready:

```text
rondo request-review gemini
```

The independent Gemini session tests and reviews, then records one result:

```text
rondo review pass "Unit and integration tests pass; no blocking issue"
```

Rondo rejects that command in any session that participated in implementation. A fresh session of the same provider is independent because it has a different session ID.

## Commands

```text
rondo                         open split AI panes and Relay
rondo setup                   change enabled AIs
rondo context on|off          enable or disable shared context
rondo task "goal"             record the current goal
rondo checkpoint "summary"    record the minimum continuation state
rondo next [AI] ["summary"]   hand work to another AI
rondo message <AI> "message"  send a visible message
rondo request-review [AI]     request independent verification
rondo review pass|fail "text" record the independent result
rondo status                  show current coordination state
```

## Local project data

Rondo creates `.rondo/config.json`, `state.json`, `context.md`, `messages.jsonl`, and `layout.kdl`. Context is capped at 32 KiB; Relay messages rotate at 1 MiB. Rondo adds `/.rondo/` only to the repository's `.git/info/exclude`, leaving the shared `.gitignore` untouched.

`rondo context off` removes `context.md` and stops recreating it. Minimal configuration, session state, and visible messages remain so coordination still works. Secret-like values are redacted, but `.rondo` is not a secret vault; never place passwords, tokens, or personal data in a checkpoint or message.

## Failover boundary

Rondo fails over only when an explicit usage/quota exhaustion message appears in two consecutive screen samples. Ordinary errors, network failures, user exits, and ambiguous non-zero exit codes do not trigger it. If a target is waiting at a trust, approval, or selection prompt, Rondo leaves the message in Relay and does not inject input.

## Upgrading from 0.14

The 0.15 installer removes only Rondo-owned global hooks and status-line entries created by 0.14.x. It first keeps a `.rondo-v014.bak` copy of an affected Claude or Gemini settings file and preserves unrelated settings. Legacy dashboard, `ai`, `handoff`, race, proof, and status launchers are removed from the managed install path.

## Development

```sh
python3 -m py_compile bin/rondo bin/rondo-agent-session bin/rondo-relay lib/rondo/core.py lib/rondo/cleanup.py
python3 -m unittest discover -s tests -v
sh -n install.sh
```

Rondo is licensed under [MIT](LICENSE). See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the bundled Zellij notice and [SECURITY.md](SECURITY.md) for private vulnerability reporting.
