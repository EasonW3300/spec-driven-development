# Changelog

## 0.1.0 — 2026-08-28

Initial release.

### Core

- Module-based spec-driven workflow engine with `start`, `start-module`,
  `record-test`, `checkpoint`, `confirm-next`, `status`, and `recover`.
- Versioned machine-state and configuration migrations.

### Host adapters

- `generic`
- `claude-code`
- `codex`

### Installation

- `spec-driven install` with dry-run previews, install receipts, and rollback for
  `claude-code` and `codex` hosts.
- `spec-driven uninstall` restores original host settings from receipts.

### Migration

- Sequential, backed-up, idempotent migrations for `spec-driven.config.*` and
  `.spec-driven/state.json`; spec/plan documents are never migration targets.

### Diagnostics

- `spec-driven doctor` distinguishes pass, warning, and failure.
- `spec-driven self-test` runs offline and proves the complete gated update path.

### Supported Python versions

- 3.11, 3.12, 3.13
