# Spec-Driven Development Implementation Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a host-neutral spec-driven development engine, its coding-agent adapters, document format plugins, and installation/update tooling.

**Architecture:** The product is split into five independently testable plans. The core baseline owns the state machine, event protocol, evidence gate, Markdown support, generic fallback, and CLI. Claude Code and Codex adapters translate host events into the core protocol. Structured document adapters add YAML/JSON without changing the core. Productization adds packaging, migration, installation, and diagnostics.

**Tech Stack:** Python 3.11+, `argparse`, `dataclasses`, `json`, `hashlib`, `pathlib`, `ruamel.yaml` for comment-preserving YAML, `pytest`, `hatchling`, POSIX shell wrappers where a host requires them.

## Global Constraints

- All runtime state is local to the project; no remote service stores project documents, test output, or confirmations.
- The core accepts only validated versioned events and never infers advancement from arbitrary natural language.
- A module cannot advance unless unit and regression test evidence both have exit code `0` and match the current module.
- The core, adapters, and format plugins have separate interfaces and contract tests.
- Document writes are hash-checked, backed up, atomic, idempotent, and limited to configured spec/plan files plus `.spec-driven/`.
- Adapter capability gaps are reported explicitly and fall back to an explicit command path; they never silently weaken the gate.
- Every implementation task ends with focused tests, the full regression suite, and a focused commit.

---

## Scope decomposition

The approved design covers multiple independent subsystems, so implementation is intentionally split into these plans. Each plan produces a runnable, testable deliverable and has an explicit dependency boundary.

| Order | Plan | Deliverable | Depends on |
|---|---|---|---|
| 1 | `2026-08-26-spec-driven-core-baseline.md` | Local core CLI, state machine, Markdown format, generic fallback | none |
| 2 | `2026-08-26-claude-code-adapter.md` | Claude Code capability probe and adapter package | core baseline |
| 3 | `2026-08-26-codex-adapter.md` | Codex capability probe and adapter package | core baseline |
| 4 | `2026-08-26-structured-document-adapters.md` | YAML/JSON plugins and round-trip guarantees | core baseline |
| 5 | `2026-08-26-productization-toolchain.md` | Packaging, install, upgrade, migration, release diagnostics | core, adapters, plugins |

## Repository layout after all plans

```text
pyproject.toml
src/spec_driven/
  adapters/
  documents/
  cli.py
  config.py
  diagnostics.py
  discovery.py
  errors.py
  events.py
  evidence.py
  models.py
  modules.py
  patches.py
  state.py
  engine.py
skills/spec-driven-development/SKILL.md
adapters/claude-code/
adapters/codex/
install/
migrations/
tests/
  unit/
  contract/
  integration/
  e2e/
fixtures/
```

## Cross-plan checkpoints

After Plan 1:

```bash
python -m pytest -q
python -m spec_driven.cli doctor --project fixtures/markdown-project
```

After Plans 2–4:

```bash
python -m pytest -q
python -m spec_driven.cli start --project fixtures/markdown-project
```

After Plan 5:

```bash
python -m pytest -q
python -m spec_driven.cli self-test
```

The implementation worker must execute plans in order. A later plan may add files and tests, but it may not bypass or duplicate the core state machine and document writer.
