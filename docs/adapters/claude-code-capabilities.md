# Claude Code adapter capabilities

- Contract checked against the Claude Code hook lifecycle documented for the current CLI version at implementation time (2026-08). Field names used by fixtures live in `fixtures/claude-code/` and are locked by `tests/contract/test_claude_code_contract.py`.
- Identity fields that Claude Code does not natively send (`module_id`, `test_kind`, `started_at`, `finished_at`, `exit_code`, `command`) are injected into the hook stdin payload by the installed wrapper command, which reads them from `.spec-driven/state.json` and its own execution of the configured test commands. The invariant: exit codes are captured by a local process running the test command — never parsed out of agent prose.

| Capability | Mechanism | Fields consumed | Status | Fallback when unavailable |
|---|---|---|---|---|
| Session lifecycle | `SessionStart` hook | `session_id`, `timestamp` (wrapper-injected), `cwd` | available after install | generic CLI `start` |
| Bash success | `PostToolUse` + Bash matcher | `tool_name`, real `exit_code`, timing fields | available after install | agent runs tests via core CLI path |
| Bash failure | `PostToolUseFailure` + Bash matcher | same as success, nonzero `exit_code` preserved | available after install | failure evidence recorded via core CLI |
| Explicit confirmation | `UserPromptSubmit` exact-match prompt | `prompt`, `session_id`, `module_id`, `timestamp` | available; whole-prompt match only | type exact command via generic CLI |
| Document update | core engine transaction only | — (adapter never writes spec/plan) | always through core gate | none; unsupported paths stay read-only |
| Natural-language confirmation | rejected by exact match | — | no event created | context reply naming `confirm-next` |

Hook failures fail closed: malformed payloads or missing identity fields produce a nonzero/diagnostic response and leave documents untouched.
