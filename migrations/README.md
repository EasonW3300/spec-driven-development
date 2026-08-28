# Machine-state migrations

Migrations apply only to `spec-driven.config.*` and `.spec-driven/state.json`.
They advance exactly one schema version, are pure functions, preserve unknown keys,
and must have tests for source input, target output, repeat invocation, invalid input,
and interrupted file replacement. Migrations never read or write spec/plan documents.
