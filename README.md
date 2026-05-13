# claude-account-switcher

Switch between multiple **Claude Code** (Anthropic) accounts on the same machine without re-logging-in every time. Save each native Claude Pro login as a named profile, then swap between them with a single command — `/status` keeps showing the real Email and Organization for the active account.

> Built for macOS (uses the Keychain). Should work on Linux too, with credentials persisted to `~/.claude/.credentials.json` only.

---

## Why

The official `claude` CLI stores one set of credentials at a time in `~/.claude/.credentials.json` (and on macOS, in the login Keychain). Logging out and back in every time you want to switch between, say, a personal Pro account and a work account is tedious.

This tool snapshots a full native login (refresh token, access token, organization metadata) into a per-profile directory, then atomically swaps the live credentials file + Keychain entry + `~/.claude.json` `oauthAccount` field when you say `use <name>`. Claude Code thinks you logged in normally — `/status` shows the right account, your usage counts against the right plan.

---

## Features

- One-command switching between as many Claude Pro accounts as you want.
- **Preserves native login state** — `/status` shows Email/Organization for each account, not just an opaque "Auth token".
- Stores credentials at `0600`, profile dirs at `0700`, with `umask 077` enforced from the first line of the script.
- File-locking on mutating operations (`mkdir`-based mutex, PID-based stale detection, configurable timeout).
- Validates credential JSON against the known Claude schema, with `CLAUDE_SKIP_VALIDATION=1` escape hatch if Anthropic changes it.
- Auto-cleans live credentials (file + Keychain + `oauthAccount` in `~/.claude.json`) when you remove the currently-active profile.
- No dependencies beyond zsh + the real `claude` CLI. `jq` is optional but recommended.

---

## Requirements

- macOS (Linux works too, but you lose Keychain integration)
- `zsh` (default shell on modern macOS)
- The official Claude Code CLI installed somewhere on disk (`~/.local/bin/claude`, `~/.claude/local/claude`, `/opt/homebrew/bin/claude`, `/usr/local/bin/claude`, or pointed at via `CLAUDE_REAL_BIN`)
- `jq` (optional — without it, schema validation and `~/.claude.json` patching are skipped)

---

## Installation

```sh
git clone https://github.com/ntdung6868/claude-account-switcher.git
cd claude-account-switcher
chmod +x claude claude-account
```

That's it. Run it via the absolute path, or add the directory to your `PATH`:

```sh
export PATH="$HOME/path/to/claude-account-switcher:$PATH"
```

Putting the directory **before** the real `claude` binary on `PATH` makes typing `claude` use the wrapper. The wrapper itself resolves the real binary internally and never recurses.

---

## Quick start

Save your first account:

```sh
# 1. Reset to a fresh native-login state
./claude-account use-native

# 2. Log in to your Claude Pro account (interactive browser flow)
./claude auth login --claudeai

# 3. Snapshot the login under a name
./claude-account save-native personal
```

Add a second account:

```sh
./claude-account use-native
./claude auth login --claudeai     # log in as the other account
./claude-account save-native work
```

Switch between them whenever you want:

```sh
./claude-account use personal
./claude
# ... do stuff as personal ...

./claude-account use work
./claude
# ... do stuff as work ...
```

Check who's active:

```sh
./claude-account current   # → personal
./claude-account list
# * personal (native)
#   work (native)
#   native-login
```

---

## Commands

| Command | What it does |
| --- | --- |
| `claude-account init` | Create the data directories. Idempotent. |
| `claude-account save-native <name>` | Snapshot the current native login (from `~/.claude/.credentials.json` or Keychain) into `native-accounts/<name>/` and set it active. |
| `claude-account use <name>` | Restore the snapshotted profile into the live credential locations. Pass `native-login` to switch to bare native mode (whatever credentials happen to be on disk). |
| `claude-account use-native` | Switch to bare native mode without touching the saved profiles. Useful before running `claude auth login --claudeai` to capture a new account. |
| `claude-account remove-native <name>` | Delete a saved profile. If it was the active one, also clears live credentials (file + Keychain + `oauthAccount` field). |
| `claude-account list` | List all profiles, marking the active one with `*`. |
| `claude-account current` | Print the active profile name (or `native-login`). |
| `claude-account status` | Run `claude auth status` with the active account. |
| `claude-account run [args...]` | Run the real `claude` CLI with the active account. The `claude` wrapper script delegates to this. |

---

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `CLAUDE_ACCOUNT_DIR` | directory containing the script | Where profiles, lock, and state files live. |
| `CLAUDE_HOME_DIR` | `$HOME/.claude` | Real Claude config dir, where `.credentials.json` lives. |
| `CLAUDE_JSON_FILE` | `$HOME/.claude.json` | Real Claude top-level config file (holds `oauthAccount`). |
| `CLAUDE_REAL_BIN` | (auto-detected) | Absolute path to the real `claude` CLI. The wrapper searches `$HOME/.local/bin/claude`, `$HOME/.claude/local/claude`, `/opt/homebrew/bin/claude`, `/usr/local/bin/claude` in order; set this if your install is elsewhere. |
| `CLAUDE_LOCK_TIMEOUT` | `30` | Seconds to wait for the lock before failing. |
| `CLAUDE_SKIP_VALIDATION` | (unset) | Set to `1` to bypass strict credential-schema validation. Use only if Anthropic changed the schema and the strict check is wrong. |

---

## How it works

Native Claude Pro credentials live in three places on macOS:

1. **`~/.claude/.credentials.json`** — JSON object with `claudeAiOauth.{refreshToken, accessToken, …}`.
2. **macOS Keychain** — entry with service name `Claude Code-credentials` (suffixed with a hash of `CLAUDE_CONFIG_DIR` if set), account `$USER`.
3. **`~/.claude.json`** — top-level config; the `oauthAccount` field is what powers `/status` showing Email/Org.

`save-native <name>` snapshots all three into `native-accounts/<name>/.credentials.json` and `native-accounts/<name>/oauthAccount.json`. `use <name>` writes them all back. The real `claude` CLI doesn't know it didn't log in normally.

When the active profile is removed, the script wipes the three live locations so the next `claude` invocation isn't tied to a "deleted" account.

The `claude` wrapper itself is a one-liner that delegates to `claude-account run`, which in turn `exec`'s the real CLI after unsetting any `CLAUDE_CODE_OAUTH_TOKEN` / `ANTHROPIC_AUTH_TOKEN` env vars that might shadow the native login.

---

## Security notes

- Profile credentials are stored at `0600` under a `0700` parent. The script enforces `umask 077` from line 3, so even the brief window between file creation and an explicit `chmod` is safe.
- Mutating commands acquire an exclusive lock at `$BASE_DIR/.lock` to prevent two simultaneous switches from corrupting state.
- The script never logs or echoes tokens.
- Add the data directory to your backup tool **only if you understand that you're backing up active Claude Pro tokens**.

---

## Troubleshooting

**`Could not find the real Claude binary`** — your `claude` CLI is installed somewhere unusual. Set `CLAUDE_REAL_BIN=/path/to/claude`.

**`saved credentials for 'X' are not a full Claude Pro login`** — the snapshot is missing `claudeAiOauth.refreshToken` / `accessToken`. Either re-save with `claude-account save-native X` after logging in again, or, if you suspect Anthropic changed the schema, retry the command with `CLAUDE_SKIP_VALIDATION=1`.

**`could not acquire lock after 30s`** — another `claude-account` process is still running, or a previous one crashed without cleanup. The script auto-detects stale PIDs; if it still complains, remove `$BASE_DIR/.lock` manually.

**`/status` still shows the old account after switching** — most often means `~/.claude.json` wasn't patched. Make sure `jq` is installed (`brew install jq`), then re-save the profile (`save-native`) while logged in as the desired account.

---

## License

MIT — see [LICENSE](LICENSE).
