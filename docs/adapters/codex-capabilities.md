# Codex adapter capabilities

- Contract checked against the OpenAI Codex CLI's documented extensibility surface at implementation time (2026-08): `notify` external-program events in `~/.codex/config.toml`, custom prompts under `~/.codex/prompts/`, skills under `~/.codex/skills/`. Source of record: `github.com/openai/codex/docs/config.md`. Field names used by fixtures live in `fixtures/codex/` and are locked by `tests/contract/test_codex_contract.py`.
- The documented `notify` payload carries `type: agent-turn-complete` plus turn context; session identity (`session_id`, `timestamp`, `cwd`) is wrapper-injected by the installed bridge, mirroring the Claude Code approach.
- **Codex has no per-tool hook**, so real test exit codes can never come from notify payloads or log text. Evidence enters only through the core CLI executing the configured commands itself; the capability report marks `bash_exit_status: unavailable` permanently for this host.

| Capability | Mechanism | Fields consumed | Status | Fallback when unavailable |
|---|---|---|---|---|
| Turn lifecycle | `notify` external program | `type`, wrapper-injected `session_id`/`timestamp` | available after install | generic CLI only |
| Bash success/failure capture | none in host | — | **unavailable** | core CLI executes tests, records exit codes |
| Explicit confirmation | exact-command prompt via installed skill/prompt asset | whole `prompt` equal to command | whole-prompt match only | type exact command via generic CLI |
| Document update | core engine transaction only | — (adapter never writes spec/plan) | always through core gate | none |
| Natural-language confirmation | rejected by exact match | — | no event created | context reply naming `confirm-next` |

Bridge behavior: the notify program must exit 0 for delivery failures it handles itself; structural payload errors exit 2 with a diagnostic, but runtime forwarding failures are reported as a message rather than blocking the host.
