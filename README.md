# csw — Claude Account Switcher

[![npm version](https://img.shields.io/npm/v/claude-cli-switcher.svg)](https://www.npmjs.com/package/claude-cli-switcher)
[![npm downloads](https://img.shields.io/npm/dm/claude-cli-switcher.svg)](https://www.npmjs.com/package/claude-cli-switcher)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform: macOS · Linux](https://img.shields.io/badge/platform-macOS%20%C2%B7%20Linux-lightgrey.svg)](#requirements)

Switch between multiple **Claude Code** (Anthropic) accounts on the same machine in one command. Native Claude Pro logins (refresh token + access token + organization metadata) are snapshotted per profile, so `/status` keeps showing the right Email and Organization no matter which account you're using.

```sh
$ csw
╭───────────────────────────────────────────╮
│  csw — Claude Account Switcher
├───────────────────────────────────────────┤
│  ⚡ Active:   personal
│  👤 Profiles: 3
╰───────────────────────────────────────────╯

What do you want to do?

  ❯ Switch account
    Save current login as new profile
    Remove a profile
    Run claude (with active account)
    Show /status
    Quit

[↑↓ navigate · Enter select · Esc/q back]
```

Pure zsh, zero runtime dependencies, works alongside the official Claude CLI without touching it.

---

## Why

The official `claude` CLI stores **one** set of credentials at a time — in `~/.claude/.credentials.json` and the macOS Keychain. Switching between, say, a personal Pro account and a work one means logging out and back in every single time. Tedious, and `/status` only shows the active login.

`csw` snapshots a full native login into a per-profile directory, then atomically swaps the live credentials file + Keychain entry + the `oauthAccount` field in `~/.claude.json` when you say "switch". The Claude CLI thinks you logged in normally — your `/status` shows the right account, your usage counts against the right plan.

---

## Features

- **Interactive menu** by default — `csw` with no args opens a polished arrow-key menu.
- **One-command switching** between any number of accounts.
- **Preserves native login state** — `/status` shows Email/Organization per profile, not just an opaque "Auth token".
- **Secure by construction** — `umask 077` from line 3, credentials at `0600`, dirs at `0700`.
- **File-locking** on mutating operations: atomic `mkdir`-based mutex, PID-based stale-lock recovery, configurable timeout.
- **Schema validation** with `CLAUDE_SKIP_VALIDATION=1` escape hatch if Anthropic ever changes the credential format.
- **Auto-cleanup** of live credentials (file + Keychain + `~/.claude.json` `oauthAccount`) when you remove the active profile.
- **Zero deps** beyond zsh and the real `claude` CLI. `jq` is optional but recommended.

---

## Requirements

- macOS (Linux works too — you lose Keychain integration, credentials persist to `~/.claude/.credentials.json` only)
- `zsh` (default shell on modern macOS)
- The official Claude Code CLI installed somewhere reasonable — `~/.local/bin/claude`, `~/.claude/local/claude`, `/opt/homebrew/bin/claude`, `/usr/local/bin/claude`, or pointed at via `CLAUDE_REAL_BIN`
- `jq` (optional) — enables credential schema validation and `~/.claude.json` patching

---

## Installation

### Option 1 — npm (recommended)

```sh
npm install -g claude-cli-switcher
```

That puts `csw` on your `PATH`. Done.

### Option 2 — git clone

```sh
git clone https://github.com/ntdung6868/claude-account-switcher.git
cd claude-account-switcher
chmod +x csw

# Put csw on your PATH (any one of these):
ln -s "$PWD/csw" ~/.local/bin/csw          # if ~/.local/bin is on PATH
sudo ln -s "$PWD/csw" /usr/local/bin/csw   # global
# …or add the repo dir to PATH in your shell rc.
```

### Reload your shell, and you're done

```sh
csw          # opens the menu
csw help     # full CLI reference
```

`csw` is **completely independent** of the official `claude` CLI. It doesn't wrap or shadow it — `claude` keeps doing exactly what it always did. All `csw` does is swap which credentials are sitting in `~/.claude/.credentials.json` and the Keychain when you say "use this profile". The next `claude` call picks them up naturally.

The typical workflow is:

```sh
csw use work
claude          # now logged in as the "work" profile
# ... later ...
csw use personal
claude          # now logged in as "personal"
```

Profiles and state live in `~/.claude-switcher/` regardless of where the script is installed. Override with `CLAUDE_ACCOUNT_DIR=/some/path`.

---

## Quick start

### Add your first account

Just run `csw`, choose **Save current login as new profile** from the menu, and follow the prompts — it'll reset state, open the Claude OAuth browser flow, ask for a profile name, and snapshot the result.

Or do it from the CLI:

```sh
csw use-native                       # fresh native-login mode
csw run auth login --claudeai        # log in via browser
csw save-native personal             # snapshot under a name
```

### Add a second account

Same steps, different login:

```sh
csw use-native
csw run auth login --claudeai        # log in as the other account
csw save-native work
```

### Switch between them

```sh
csw use personal
claude                                # the official Claude CLI now uses 'personal'
# ... do stuff as personal ...

csw use work
claude                                # ... and now 'work'
# ... do stuff as work ...
```

### Check who's active

```sh
csw current   # → personal
csw list
# * personal
#   work
```

---

## Commands

| Command | What it does |
| --- | --- |
| `csw` | Open the interactive menu. |
| `csw save-native <name>` | Snapshot the current native login into `native-accounts/<name>/` and set it active. |
| `csw use <name>` | Restore a snapshotted profile to the live credential locations. Only saved profiles are shown in the switch menu. |
| `csw use-native` | Switch to bare native mode without touching saved profiles. This is a utility mode for adding/logging in accounts; it is intentionally not shown as a selectable account in the switch menu. |
| `csw remove-native <name>` | Delete a saved profile. If it was active, also clears the live credentials (file + Keychain + `oauthAccount`). |
| `csw list` | List all profiles, marking the active one with `*`. |
| `csw current` | Print the active profile name (or `native-login`). |
| `csw status` | Run `claude auth status` against the active account. |
| `csw run [args...]` | Run the real `claude` CLI with the active account. Unsets any `*_AUTH_TOKEN` env vars first. |
| `csw init` | Create the data directories. Idempotent. |
| `csw help` | Print full help. |

---

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `CLAUDE_ACCOUNT_DIR` | `$HOME/.claude-switcher` | Where profiles, lock, and state files live. |
| `CLAUDE_HOME_DIR` | `$HOME/.claude` | Real Claude config dir, where `.credentials.json` lives. |
| `CLAUDE_JSON_FILE` | `$HOME/.claude.json` | Real Claude top-level config (holds `oauthAccount`). |
| `CLAUDE_REAL_BIN` | (auto-detected) | Absolute path to the real `claude` CLI. The script searches `$HOME/.local/bin/claude`, `$HOME/.claude/local/claude`, `/opt/homebrew/bin/claude`, `/usr/local/bin/claude` in order; set this if your install is elsewhere. |
| `CLAUDE_LOCK_TIMEOUT` | `30` | Seconds to wait for the lock before failing. |
| `CLAUDE_SKIP_VALIDATION` | (unset) | Set to `1` to bypass strict credential-schema validation. Use only if Anthropic changed the schema and the strict check is wrong. |

---

## How it works

Native Claude Pro credentials live in three places on macOS:

1. **`~/.claude/.credentials.json`** — JSON with `claudeAiOauth.{refreshToken, accessToken, …}`.
2. **macOS Keychain** — entry with service `Claude Code-credentials` (suffixed with a hash of `CLAUDE_CONFIG_DIR` if set), account `$USER`.
3. **`~/.claude.json`** — top-level config; the `oauthAccount` field is what powers `/status` showing Email/Organization.

`save-native <name>` snapshots all three into `native-accounts/<name>/.credentials.json` and `native-accounts/<name>/oauthAccount.json`. `use <name>` writes them all back. The real `claude` CLI never knows it didn't log in normally.

When the active profile is removed, the script wipes all three live locations so the next `claude` run isn't tied to a "deleted" account.

`csw run [args...]` `exec`s the real CLI after unsetting any `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CODE_OAUTH_REFRESH_TOKEN`, or `ANTHROPIC_AUTH_TOKEN` env vars that could shadow the native login.

---

## Concurrency

Mutating commands (`save-native`, `use`, `use-native`, `remove-native`) take an exclusive lock at `$BASE_DIR/.lock`. Concurrent invocations wait up to `CLAUDE_LOCK_TIMEOUT` seconds (default `30`) before failing. Read-only commands (`list`, `current`, `status`, `run`) are not locked. Stale locks from crashed processes are auto-detected via the recorded PID, so you never need to `rm -rf .lock` manually after a Ctrl-C.

---

## Schema-change escape hatch

Credential validation checks for `.claudeAiOauth.refreshToken` and `.claudeAiOauth.accessToken`. If Anthropic changes the format, the strict check fails with a hint. Re-run with `CLAUDE_SKIP_VALIDATION=1` to bypass — the script copies credentials raw and emits a warning rather than failing.

---

## Security notes

- Profile credentials are at `0600` under a `0700` parent. The script forces `umask 077` from its third line, so even the brief window between file creation and an explicit `chmod` is safe.
- The script never logs tokens.
- `csw run` unsets known auth env vars (`CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CODE_OAUTH_REFRESH_TOKEN`, `ANTHROPIC_AUTH_TOKEN`) before exec'ing the real CLI, so a stray env var can't shadow your selected account.
- Add the data directory to backups **only if you understand that you're backing up active Claude Pro tokens**.

---

## Troubleshooting

**`Could not find the real Claude binary`** — your `claude` CLI is installed somewhere unusual. Set `CLAUDE_REAL_BIN=/path/to/claude`.

**`saved credentials for 'X' are not a full Claude Pro login`** — the snapshot is missing `claudeAiOauth.refreshToken` / `accessToken`. Either re-save with `csw save-native X` after logging in again, or, if you suspect Anthropic changed the schema, retry with `CLAUDE_SKIP_VALIDATION=1`.

**`could not acquire lock after 30s`** — another `csw` process is still running or stuck. The script auto-detects stale PIDs; if it still complains, remove `$BASE_DIR/.lock` manually.

**`/status` still shows the old account after switching** — most often means `~/.claude.json` wasn't patched. Make sure `jq` is installed (`brew install jq`), then re-save the profile (`csw save-native`) while logged in as the desired account.

**`interactive menu requires a terminal`** — `csw` was invoked from a non-TTY context (a script, a pipe, CI). Use the CLI subcommands directly: `csw use <name>`, `csw run`, etc.

---

## License

MIT — see [LICENSE](LICENSE).
