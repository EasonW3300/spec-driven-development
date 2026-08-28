# Spec-Driven Development

Host-neutral workflow engine for driving modular coding work from a spec and plan,
with unit and regression gates. A machine reads a project's spec and plan documents,
tracks one active module at a time, records real test evidence, and only advances to
the next module after an explicit command confirmation from the user.

## Install

```bash
python -m pip install spec-driven-development
spec-driven install --host claude-code --scope user --dry-run
spec-driven install --host claude-code --scope user
spec-driven doctor --project /path/to/project --json
```

Installing sets up the Claude Code or Codex host hooks and copies the skill. Always
review the `--dry-run` preview before a real install. Uninstall with
`spec-driven uninstall --receipt PATH --root ROOT`, which restores the original
settings from the recorded receipt.

## Commands / version

- `spec-driven --version` — prints the installed version (e.g. `0.1.0`).

## Project configuration

A project opts in with a `spec-driven.config.yaml`. Both the unit command and the
regression command are **mandatory**: the engine refuses to advance until real exit
code and summary evidence for both are recorded. The commands are inferred, but every
inferred command must be explicitly confirmed before it is used.

```yaml
schema_version: 1
spec:
  paths: [docs/specs/product.md]
plan:
  paths: [docs/plans/product-plan.md]
tests:
  unit:
    command: python -m pytest tests/unit -q
  regression:
    command: python -m pytest -q
documents:
  adapters: [markdown]
```

The spec and plan documents may be Markdown, YAML, or JSON. The core manages exactly
the managed blocks below and never rewrites anything outside them.

Markdown markers, one per module, are opened with `<!-- spec-driven:module -->` and
closed with `<!-- /spec-driven:module -->`, and contain a completion block delimited
by `<!-- spec-driven:completion -->` ... `<!-- /spec-driven:completion -->`:

```markdown
<!-- spec-driven:module id="M1" order="1" status="pending" -->
## M1: Core workflow

Goal: Create the core workflow.

Acceptance:
- State transitions are validated.
- Both test gates are recorded.

Tests: unit, regression

<!-- spec-driven:completion -->
Status: pending
Next module: M2
Completed points:
Notes:
Evidence:
<!-- /spec-driven:completion -->
<!-- /spec-driven:module -->
```

A YAML project uses structured documents:

```yaml
# Product spec, YAML host format. Prose lives beside the managed section.
purpose: keep product promises testable

stakeholders:
  - name: platform
    role: owner

spec_driven:
  active_module_id: M1
  modules:
    - id: M1
      order: 1
      title: Core
      goal: Build core engine
      status: pending
      prerequisites: []
      acceptance:
        - "gate works"   # reviewer note: keep quotes round-tripping
      tests: [unit, regression]
```

And a JSON project uses JSON documents:

```json
{
  "title": "Product spec, JSON host format",
  "stakeholders": [
    {"name": "platform", "role": "owner"}
  ],
  "spec_driven": {
    "active_module_id": "M1",
    "modules": [
      {
        "id": "M1",
        "order": 1,
        "title": "Core",
        "goal": "Build core engine",
        "status": "pending",
        "prerequisites": [],
        "acceptance": ["gate works"],
        "tests": ["unit", "regression"]
      }
    ]
  }
}
```

## Module workflow

`spec-driven` is a state machine. The module commands are:

- `start` — begin a session for the configured project (optionally from a JSON
  session payload on stdin).
- `start-module` — begin work on the current module; submit a `module_started` event.
- `record-test` — submit real unit and regression test evidence for the active module.
- `checkpoint` — record completed points and notes for the current module.
- `status` — show the current module and state without mutating anything.
- `confirm-next` — the only command that advances the active module and updates the
  spec/plan documents.
- `recover` — re-sync state after an interruption.

Both gates (unit and regression) must pass before a module can be completed.
Natural-language replies such as "继续" or "可以" are **not** authorization.
Confirmation is explicit-command only: the user must type exactly `confirm-next`, and
only the core may update the spec/plan documents.

```bash
spec-driven start --project .
spec-driven start-module --input start-module.json
spec-driven record-test --input evidence.json
spec-driven checkpoint --input checkpoint.json
spec-driven confirm-next --input confirmation.json
spec-driven status --project .
```

## Recovery and uninstall

- `recover` — after an interrupted session, re-reads the state and event log so the
  workflow can continue from the last committed transition.
- `self-test` — runs offline against a packaged fixture project and proves the complete
  gated update path (start, module start, both test gates, checkpoint, explicit
  confirmation, document update, next module gate):

  ```bash
  spec-driven self-test --json
  ```

- `migrate` — advances machine documents (`spec-driven.config.*` and
  `.spec-driven/state.json`) exactly one schema version. Spec/plan files are never
  migration targets. Always preview first:

  ```bash
  spec-driven migrate --project /path/to/project --target-version 2 --dry-run
  ```

  Real migrations create timestamped backups under `.spec-driven/migration-backups/`
  and are idempotent.

- `uninstall` — reverses an install from its receipt. `install` writes receipts under
  the host settings target's `.spec-driven/install-receipts/` directory (for example
  `~/.spec-driven/install-receipts/claude-code.json` for a user-scope install), and
  backs up the original settings so rollback restores them exactly:

  ```bash
  spec-driven uninstall --receipt /path/to/receipt.json --root ROOT
  ```

- `doctor` — checks configuration, document discovery, and test commands and reports
  pass, warning, or failure:

  ```bash
  spec-driven doctor --project /path/to/project --json
  ```

## Development

```bash
python -m pip install -e ".[test]"
python -m pytest -q
python -m spec_driven.cli self-test --json
```

Release validation runs as a unit test (`tests/unit/test_release.py`) and in CI across
Python 3.11, 3.12, and 3.13; CI also builds the wheel, installs it into a clean
virtual environment, and verifies the installed CLI (`spec-driven --version`) and
offline self-test.
