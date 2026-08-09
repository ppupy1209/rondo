# Rondo

> One project. Every coding agent. One continuous thread.

[한국어](README.md)

Rondo keeps Claude Code, Codex, Gemini, Kimi, and Grok in one persistent terminal workspace. It removes window juggling, shows local usage state, makes agent-to-agent delegation visible, and carries unfinished work from Claude to Codex when Claude reaches its usage limit.

It provides:

- one persistent workspace per Git project;
- interactive Korean / English setup and agent selection;
- up to four panes and one approval mode shared by every agent;
- one explanation level shared by every agent pane;
- a shared status bar for models, usage, and relay state;
- visible prompts between agent panes through `rondo send`;
- human-approved project memory, reusable procedures, and proactive learning proposals;
- repository-scoped SQLite FTS work journals and session search;
- human-approved scheduled work delivered only to visible panes;
- element-scoped frontend requests through Rondo Lens;
- executable evidence and a risk-based human review queue through Rondo Proof;
- red-team, blue-team, reliability, and security tests physically separated from implementation sessions;
- opt-in Claude → Codex continuity at the usage limit.
- a Command Center that combines repository state into one recommended next action;
- verified version updates, one-generation rollback, and privacy-safe support bundles.

Rondo is local-first. It reads the files that each installed CLI already stores on your machine and does not add a hosted service, account, or API key.

## Install

### macOS / Linux

```sh
curl -fsSL https://raw.githubusercontent.com/ppupy1209/rondo/v0.12.1/install.sh | sh
```

Python 3.10+ is the only runtime requirement. The installer downloads a fixed Rondo release and Zellij 0.44.3, verifies SHA-256, creates the commands in `~/.local/bin`, and adds that directory to your shell `PATH`.

### Windows

Open PowerShell and run:

```powershell
irm https://raw.githubusercontent.com/ppupy1209/rondo/v0.12.1/install.ps1 | iex
```

The Windows installer downloads Rondo and native Zellij. If Python 3.10+ is missing, it installs Python through WinGet. WSL is not required. Open a new terminal after installation.

On every platform, install at least one agent CLI you want to use. Rondo discovers the installed agents during setup; you do not need to install every supported CLI.

Then run this once inside the Git repository you want to work on:

```sh
rondo
```

Only the first run asks for language, explanation level, approval mode, agents, and relay behavior, then opens the panes immediately. Later runs attach directly to the same repository workspace. Run `rondo setup` only when you want to change the saved choices.

To link an existing clone for development, run `sh install.sh` on macOS/Linux or `.\install.ps1` in PowerShell. That mode points directly at source files and is intentionally outside the managed update/rollback lifecycle. Use `rondo update` and `rondo rollback` for a version installed by the one-line command.

Existing `ai-tools` installations are migrated on first run. The old `ai`, `ai-status`, and `claude-statusline` commands remain compatibility aliases.

## Quick start

```sh
cd ~/projects/my-project
rondo             # open outside; show actions from the workspace shell tab
rondo menu        # explicitly open the test, review, knowledge, and settings menu
rondo status      # show current state and one recommended next action
rondo setup       # change saved language, explanation, approval, agents, and relay
rondo audience    # change how every agent explains its results
rondo add         # select and add another agent pane
rondo send codex "Review the current diff"  # type and submit in the Codex pane
rondo learn pending  # review project knowledge proposed by users and agents
rondo recall "authentication"  # search approved knowledge, work history, and Git
rondo history "authentication"  # search the high-signal repository work journal
rondo schedule       # manage proposed and active jobs with a selection menu
rondo lens        # click a UI element and send its focused context
rondo proof       # run checks and build a risk-based review packet
rondo test all --from codex --tester claude  # test outside the implementation session
rondo git         # inspect Git connection, branch, PR policy, and reviewers
rondo doctor      # diagnose dependencies and configuration
rondo update --check  # check for a verified release
```

The first `rondo` launch opens setup automatically. Move with arrow keys, select up to four agents with Space, and save with Enter. Names and modes never need to be typed.

For everyday use, you do not need to memorize subcommands. Ask naturally in an agent pane and that agent starts the matching Rondo action.

```text
Remember this rule for the project
Have Codex inspect CI every day at 9 AM
Independently test the current changes
Run only the security tests in a fresh session
Have every configured agent review the code
Find our earlier authentication work
```

Human decisions such as approving memory or scheduled-work proposals are never automated. Run bare `rondo` from the `shell` tab, select the item with the arrow keys, inspect the original text, then approve or reject it. Existing commands such as `rondo learn`, `rondo schedule`, and `rondo test` remain available for scripts and precise control.

## Command Center and product lifecycle

Run `rondo` from the workspace `shell` tab to see repository and branch, work goal, changed files, pending knowledge, scheduled work, independent tests, race, and latest Proof in one view. Rondo applies a deterministic priority and puts one action at the top with `★`: human approvals first, then active tests or races, missing intent, and verification. `rondo status` prints the same state without the interactive menu.

Command Center quietly checks GitHub for the latest Rondo release at most once per day and caches the result locally. If the network is unavailable, it keeps the previous result, shows no error, and waits an hour before retrying. It also shows the local `--version` result for configured agents such as Claude and Codex plus Zellij. Rondo never changes those external CLIs or runs their vendor installers; it only recommends its own verified update when the worktree is clean, and still requires user approval before installation.

A managed one-line installation supports this lifecycle:

```sh
rondo update --check          # check only
rondo update                  # confirm and update; retain one previous release
rondo update --version 0.12.1 # install a specific newer release
rondo rollback                # exchange current and previous installations
rondo uninstall               # remove the program, keep settings and cache
rondo uninstall --purge       # explicitly remove settings and cache too
rondo support-bundle          # create a private diagnostic zip without raw content
```

Updates, rollbacks, and removal require an interactive user terminal and are rejected from agent panes and pipes. The installer refuses unmanaged directories and symbolic links; uninstall removes only Rondo-owned launchers and hooks. Support bundles use a metadata allowlist and exclude conversations, prompts, goal text, source, file names, local paths, Git remotes, environment variables, and credentials. Nothing is uploaded automatically; inspect `report.json` before sharing.

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

Every agent pane started by Rondo receives the saved level automatically, including supported restored sessions. When `rondo audience` runs inside an active Rondo session, the update is also entered visibly into every open agent pane and applies to future replies. This broadcast can consume agent usage, so Rondo shows the number of target panes first. For unattended setup, use `RONDO_AUDIENCE=default|nondev|guided`.

## Shared approval mode

Rondo translates the setup choice into each agent's native approval option.

| Mode | Behavior |
|---|---|
| `ask` | Default: confirm risky edits and commands before execution |
| `workspace` | Use each CLI's workspace automatic mode, such as Claude `acceptEdits` and Codex `approve-for-me` |

`workspace` removes repetitive confirmations, but providers such as Kimi and Grok can automatically approve a wider command set. Use it only in a trusted repository. Rondo does not offer a mode that completely disables the sandbox. A changed setting applies consistently to every agent pane started or restored afterward.

## Visible agent delegation

`rondo send` finds an open agent pane, pastes the message into its interactive CLI, and submits it with Enter. The request appears in the target pane exactly where a manually entered prompt would appear; Rondo does not start a hidden copy of the agent.

```sh
rondo send codex "Review the current diff and finish the tests"
rondo send claude "Check the proposed API design"
rondo send gemini "Research another implementation approach"
```

Run the command inside a Rondo session, with the target pane open. An agent can invoke the same command through its shell tool, so manual prompts, agent delegation, and automatic relay all use one visible input path.

Before delivery, Rondo reads the pane screen and stops without pressing a key when it sees a trust, approval, or selection prompt. On a safe screen it pastes first, verifies that the message is visible in the input, and only then presses Enter. Rondo never approves folder trust on the user's behalf.

## Human-approved project knowledge

Rondo keeps durable repository facts and reusable procedures. Users and agents can both propose entries, but a proposal never appears in search results or agent launch guidance until a person approves it. Agents cannot read pending text through `list` or `show`, either.

Most users can simply tell an agent to “remember this,” then select the proposal from the bare `rondo` menu in the `shell` tab. The commands below remain useful for direct control and automation.

```sh
rondo learn memory "Public API changes require a compatibility note"
rondo learn skill release-check "Inspect the test report, then deploy only after user approval"
rondo learn pending                 # list pending proposals
rondo learn show a1b2c3d4           # inspect the full text
rondo learn approve a1b2c3d4        # show it again, then require y/N
rondo learn reject a1b2c3d4
rondo learn remove a1b2c3d4         # remove an approved entry

rondo recall "compatibility"        # search approved knowledge, Rondo events, and 100 recent commits
rondo recall --id a1b2c3d4          # load one complete procedure by ID
```

Approved `memory` entries are shared with new agent sessions under a strict size budget. For each `skill`, agents receive only its name, ID, and first-line summary, then load the full procedure on demand with `rondo recall --id ...`. A procedure remains reference text; Rondo never activates it as a plugin or executable code. Already-open sessions can discover new entries through `rondo recall`.

Approval, rejection, and removal require an interactive user terminal. Inside Rondo, the process must also be running in the `shell` tab. Agent panes, race tabs, pipes, and scripts are rejected. Each proposal is limited to 2,000 characters, approved memory to 4,000 characters total, and procedures to 16. Common secret, prompt-injection, and destructive-command patterns plus invisible control characters are rejected before storage. Concurrent agent writes are serialized by a repository lock, and corrupt or symbolic-link state files fail closed.

History contains only short Rondo operation events and Git commit subjects; Rondo does not ingest raw Claude, Codex, or Gemini transcripts. Everything stays private under `~/.cache/rondo/knowledge/` and `~/.cache/rondo/journal/` without a network service. This is not a secret vault against a malicious process that already has the same operating-system user privileges, so never record tokens or passwords.

## Learning loop, work journal, and scheduled work

Every newly started agent receives guidance to choose Rondo actions from natural-language requests. After a complex success, user correction, error recovery, or repository-specific discovery, it proactively proposes the smallest reusable memory or procedure. After meaningful work it records only the outcome and rationale, not the raw conversation. Proposed knowledge never reaches another agent until a person approves it.

The repository-scoped work journal stores up to 5,000 structured events in SQLite. WAL mode and FTS5 provide fast Korean and English search; a plain-search fallback is used when a Python SQLite build omits FTS5. Bounded storage and progressive disclosure avoid copying an entire old conversation into every new prompt.

```sh
rondo note "Login regression tests passed" --ref tests/auth_test.py
rondo history "login"        # search outcomes, delegation, and verification
rondo history --sessions     # provider-neutral Rondo session timeline

rondo schedule add "Inspect CI failures" --agent codex --every 2h
rondo schedule add "Run the release checks" --agent claude --at 2026-08-10T09:00:00+09:00
rondo schedule add "Check dependencies on weekday mornings" --agent codex --cron "0 9 * * 1-5"
rondo schedule              # approve, pause, resume, run, or remove without typing IDs
```

An agent calling `schedule add` can only create a proposal. Only the user in Rondo's `shell` tab can inspect raw pending text or approve, reject, pause, resume, run now, or remove it. Approved jobs never become hidden shell commands: while the Rondo session is alive, its status pane checks every 30 seconds and enters due work visibly into the target agent's prompt. A trust or approval screen blocks delivery; three failures pause the job. SQLite leases prevent concurrent status panes from delivering at the same time. If the process crashes immediately after sending but before recording completion, the next check can deliver the prompt once more.

### Shared Hermes principles and Rondo differences

Rondo 0.12 applies ideas found in Hermes Agent—durable memory, searchable sessions, scheduled work, isolated delegation, and progressively loaded procedures—to coding-agent orchestration. It is not affiliated with the official Hermes project and does not bundle the Hermes runtime.

Design references: [Hermes feature overview](https://hermes-agent.nousresearch.com/docs/user-guide/features/overview/), [Memory](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory/), [Sessions](https://hermes-agent.nousresearch.com/docs/user-guide/sessions/), [Cron](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/cron.md), [Delegation](https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation/), and [Security](https://hermes-agent.nousresearch.com/docs/user-guide/security/)

| Principle | Rondo implementation | Security and product difference |
|---|---|---|
| Durable memory and self-improvement | Agents proactively propose memories and procedures | A non-configurable human gate separates storage from reuse |
| Searchable sessions and history | Repository SQLite WAL + FTS5 journal and Rondo session timeline | Stores secret-redacted, high-signal outcomes instead of raw provider transcripts |
| Cron and recurring work | Intervals, ISO timestamps, five-field cron, up to 100 jobs | No daemon or arbitrary shell execution; work is visibly delivered to an open pane |
| Subagent delegation | `race`, independent `test`, `code-review`, and Claude→Codex relay | Implementation and verification sessions are physically separated; delegation stays visible |
| Skills and tool choice | Approved procedures inject only an index and load details on demand | Procedures never become executable plugins automatically |
| Provider choice | Claude, Codex, Gemini, Kimi, and Grok share one repository workspace | No central model account or direct upload to a model API |

Rondo does not replicate Hermes model-inference speed, provider-side prompt caching, or API routing; each vendor CLI owns those layers. Rondo improves orchestration efficiency through indexed journal lookup, bounded memory, and progressive procedure loading. General messaging gateways, voice-assistant behavior, and always-on unattended execution are intentionally excluded because they would expand a coding tool's authority and attack surface.

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

Rondo classifies changed files as low, medium, or high risk. Authentication, permissions, payments, migrations, security, deployment paths, and changes outside the declared scope are high risk; overlapping reasons are all shown. Review time scales with changed lines, while generated paths such as `__pycache__`, `dist`, `build`, `node_modules`, `.venv`, and `target` are excluded. A clean tree is reported as `no changes`, never as an approval candidate. Python unittest, npm test/lint, Gradle, Cargo, and Go checks are discovered from project files; add task-specific commands with `--check "command"`.

The independent reviewer starts in a fresh pane without the implementer's conversation. Codex uses a read-only sandbox and Claude uses plan permissions. It is instructed to inspect the actual diff, challenge the evidence, and find the strongest counterexample without editing implementation code. `ready` means approval candidate, not automatic approval; sensitive changes always remain in the human queue.

Task intent and proof packets stay under `~/.cache/rondo/proof/` with mode `0600` and are not committed. Check output can contain project data, so inspect a packet before sharing it outside the machine.

## Race, snapshots, and restore

```sh
rondo race "compare two implementations" --agents claude,codex
rondo race --status                 # inspect progress
rondo diff codex                    # inspect one result
rondo take codex                    # apply the selected result
rondo race --abort                  # discard results but preserve patches

rondo snap "before refactor"
rondo undo --list                   # list snapshot IDs
rondo undo a1b2c3d4                 # preview paths, confirm, then restore this ID
rondo undo --steps 2 --yes          # non-interactive restore two snapshots back
```

`undo` restores only the working tree and never rewrites commit history. Because untracked files are included, it shows the affected paths and asks for `y/N` confirmation by default; use `--yes` only in intentional automation. The state immediately before restoration is also preserved as a snapshot.

## Independent tests separated from implementation

Rondo's testing rule cannot be disabled or weakened through configuration.

> The agent session used for implementation is never used for testing. Selecting the same agent vendor still starts a fresh session without resuming the implementation conversation.

Both examples are valid after Codex implements a change:

```sh
rondo test all --from codex --tester claude  # Codex implementation → fresh Claude verification
rondo test all --from codex --tester codex   # Codex implementation → fresh Codex verification
```

When invoked inside an agent pane, Rondo records the implementer and implementation session automatically. From the shell tab, declare it with `--from codex`. Omitting `--tester` opens the selector; multiple testers are assigned to roles in round-robin order.

`all` stays within the four-pane limit by creating four isolated sessions that share no conversation:

| Role | Coverage |
|---|---|
| `red` | hostile inputs, boundaries, authorization bypasses, strongest counterexamples |
| `blue` | expected flows, regressions, controls, recovery, and observability |
| `reliability` | load, concurrency, races/deadlocks, idempotency, transactions, rollback, and isolation |
| `audit` | security, dependencies, secrets, permissions, injection, and actual-diff code review |

Run a narrower profile with commands such as `rondo test security`, `rondo test concurrency`, `rondo test transaction`, or `rondo test review`. Every verifier starts in a separate Git worktree containing the current changes. Temporary tests belong under `.rondo-test/`; product source must not be edited. `rondo test finish` records any source edit as a verification violation and never applies it to the original working tree.

```sh
rondo test status    # show report progress per role
rondo test finish    # after all reports: collect, flag violations, and remove the tab/worktrees
rondo test abort     # stop the run and remove isolated worktrees
```

### k6, Prometheus, and Grafana load tests

With Docker and Docker Compose available, Rondo starts an ephemeral k6, Prometheus, Grafana, and Grafana Image Renderer stack. After the run it saves a dashboard PNG and k6 results in the evidence packet.

```sh
rondo test load --from codex --tester claude \
  --url http://localhost:8080/api/health --vus 20 --duration 30s

rondo test reliability --from claude --tester codex \
  --script tests/load.js --duration 2m --allow-remote
```

The generated script sends GET requests only and does not follow redirects. VUs are limited to 1–1000 and duration to at most 60 minutes. Only localhost is allowed by default; pass `--allow-remote` only after receiving permission from the target system. Because Rondo cannot reliably determine the targets selected by custom code, a repository-local k6 script runs only with the explicit `--script ... --allow-remote` combination after you inspect it. Usage reporting and update checks are disabled for the observability tools. Grafana graphs, summary JSON, logs, and independent agent reports stay private under `~/.cache/rondo/test/`. The version-pinned stack and its volumes are removed after capture.

## Git, PRs, and agent code review

Git policy is stored in the current repository's `.git/config`, not as a global preference, so every project can use a different workflow.

```sh
rondo git                                      # connection, branch, policy, reviewers
rondo git connect https://github.com/me/app.git # initialize Git or connect origin
rondo git policy                               # choose direct | pr | review
rondo git reviewers                            # choose up to four review agents
```

| Policy | Behavior |
|---|---|
| `direct` | Allow direct work on the current branch |
| `pr` | Require a feature branch and pull request |
| `review` | Create a draft PR and require independent agent review before merge |

The `pr` and `review` policies are also included in every agent's launch guidance, keeping their Git behavior consistent. From a committed feature branch, push and create the PR in one command:

```sh
rondo pr "Improve login error UI"
rondo code-review all       # every configured reviewer inspects the real diff read-only
rondo code-review codex     # run only one reviewer
```

Under the `review` policy, `rondo pr` creates a draft and starts the configured reviewers automatically when run inside Rondo. Review panes do not inherit the implementation conversation; Claude starts in plan mode, Codex in read-only, and the other CLIs use their corresponding non-editing mode. PR creation requires an authenticated GitHub CLI, `gh`.

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
7. `rondo test` freezes the current working tree without changing its commit or index, then starts role-specific verification in separate worktrees and sessions that never reuse the implementation conversation.
8. Session wrappers and supported lifecycle hooks update an optional repository handoff log after an agent exits.
9. At Claude's usage threshold, the continuity relay prepares a local packet and can send it to the existing Codex pane.

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

`auto` is deliberately opt-in and requires Codex to be selected as a pane. Rondo types a visible handoff prompt into that pane and submits it exactly like terminal input. If Codex is waiting at a trust or approval prompt, delivery stops and the mode is downgraded to `ready`. The prompt points to the private packet, which carries the current intent, Git state, and safety contract.

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
| `rondo` | Open or attach outside; show the action menu from an open shell tab |
| `rondo menu` | Show test, verification, code-review, knowledge, Git, and settings actions |
| `rondo status` | Print repository state and the recommended next action |
| `rondo setup` | Change language, explanation, approval, up to four panes, and relay |
| `rondo audience [default\|nondev\|guided]` | Change how every agent explains its results |
| `rondo add [agent]` | Add an agent pane; omit the name to select interactively |
| `rondo send <agent> <message>` | Type and submit a visible prompt in that agent's pane |
| `rondo task <goal> [options]` | Record acceptance criteria, boundaries, scope, and checks |
| `rondo learn memory\|skill ...` | Propose repository memory or a reusable procedure for approval |
| `rondo learn pending\|show\|approve\|reject\|remove` | Manage the human-approved knowledge lifecycle |
| `rondo recall [query\|--id ID]` | Search approved knowledge, operation events, and recent Git history |
| `rondo note <summary> [--ref reference]` | Record a secret-redacted, high-signal work outcome |
| `rondo history [query\|--sessions]` | Search the repository work journal and agent sessions |
| `rondo schedule [command]` | Manage human-approved recurring and one-shot work |
| `rondo proof [--reviewer agent]` | Run checks and build an independent review packet |
| `rondo review [--budget 2m]` | Show the highest-risk human decisions within a time budget |
| `rondo git [command]` | Manage Git connection and repository-local PR/reviewer policy |
| `rondo code-review [agent\|all]` | Run independent read-only reviews by selected agents |
| `rondo test [profile] [options]` | Run red, blue, reliability, and security tests outside the implementation session |
| `rondo pr [title]` | Push the feature branch and create a policy-aware PR |
| `rondo handoff [note]` | Create `.rondo/handoff.md` for another computer |
| `rondo resume [claude\|codex]` | Open the workspace and deliver the handoff to one agent |
| `rondo lens [URL]` | Click a UI element and send its focused context after confirmation |
| `rondo race <task> [options]` | Run one task in several isolated worktrees |
| `rondo diff [agent]` / `rondo take <agent>` | Compare race results / apply one result |
| `rondo snap [label]` | Snapshot the current working tree |
| `rondo undo [ID\|--steps N] [--yes]` | Preview affected paths and restore the working tree |
| `rondo kill [session]` | Stop this project's or a named Rondo session |
| `rondo clean` | Remove local cache entries for deleted repositories |
| `rondo language` | Switch Korean / English |
| `rondo relay [off\|ready\|auto]` | Inspect or change the continuity strategy |
| `rondo continue` | Send the pending handoff to the existing Codex pane |
| `rondo doctor` | Check zellij, agents, and configuration |
| `rondo update [--check\|--version X]` | Check or install a verified managed release |
| `rondo rollback` | Restore the previous managed installation once |
| `rondo uninstall [--purge]` | Remove the program and optionally settings/cache |
| `rondo support-bundle [path]` | Create a diagnostic zip without raw content |
| `rondo -l` | List only Rondo-managed sessions |
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
  approval       ask | workspace
  panels         selected agent names (up to four)
  relay          off | ready | auto
  threshold      remaining percentage (default: 1)

~/.cache/rondo/
  layout.kdl     generated zellij layout
  audience/      private launch guidance for CLIs that use a local agent file
  claude.*       local display cache
  lens/          private element context packets and cropped screenshots
  proof/         private task intent, evidence packets, and review queues
  knowledge/     approved repository memory, procedures, and short operation events
  journal/       repository SQLite journal, sessions, and approved scheduled work
  test/          isolated test state, reports, k6 results, and Grafana captures
  relay/         private continuity packets and delivery logs
```

Repository-local `rondo.prPolicy` and `rondo.reviewers` values live in `.git/config`. For non-interactive setup, set `RONDO_LANG=ko|en`, `RONDO_AUDIENCE=default|nondev|guided`, `RONDO_APPROVAL=ask|workspace`, `RONDO_PANELS=claude,codex,...`, and `RONDO_RELAY=off|ready|auto` before running `rondo setup`.

No telemetry is included. Rondo does not store credentials or ingest raw agent transcripts to build project knowledge. A relay excerpt can contain conversation text, so use `ready` mode when work must not cross providers without an explicit action.

## Development

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile bin/rondo bin/rondo-agent-session bin/rondo-lens bin/rondo-relay bin/rondo-claude-status bin/ai-status
sh -n install.sh bin/ai bin/rondo-status bin/*-session
python3 tests/zellij_smoke.py  # real visible delivery and forced restart on macOS/Linux
```

GitHub Actions runs the Python suite and installer smoke tests on macOS, Linux, and Windows, plus real Zellij delivery and forced restart on macOS/Linux. A `v*` tag publishes macOS/Linux tar.gz, Windows zip, and SHA-256 assets only when the tag matches the CLI version.

### Internal notes

- [Adapter layer](docs/adapters.md) — how Rondo reads what each CLI leaves on disk
- [rondo race](docs/race.md) — one task, several agents, one human pick
- [Hands-on audit · 2026-08-09](docs/audit-2026-08-09.md) — every command exercised on 0.7.0, with findings (Korean)
- [0.12 external beta](docs/beta.md) — opt-in validation without telemetry (Korean)
- [Security policy](SECURITY.md) · [Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md)

## License

MIT
