---
name: spec-driven-development
description: Drive modular coding work from spec and plan with unit and regression gates (Codex host).
---

# Spec-Driven Development

Drive coding tasks from numbered modules declared in managed blocks of your project's spec and plan documents. Every state change flows through the core CLI (`spec-driven ...`); you never edit those documents directly for status purposes.

## Commands

- `spec-driven start --project <root>` — open a session when the user explicitly starts this workflow.
- `spec-driven start-module --input <event.json> --project <root>` — activate a module.
- `spec-driven record-test --input <evidence.json> --project <root>` — record one test run.
- `spec-driven record-checkpoint --input <checkpoint.json> --project <root>` — record the user checkpoint.
- `spec-driven confirm-next --input <event.json> --project <root>` — advance after an EXPLICIT exact command.
- `spec-driven recover --project <root>` / `spec-driven doctor --host codex` — repair and diagnose.

## Codex-specific doctrine

- Codex delivers only turn-complete notifications through its `notify` bridge; it has NO per-tool hook.
- Therefore test evidence is ONLY ever produced by the core CLI executing the configured commands itself. Never fabricate test evidence and never parse agent prose into evidence.
- Confirmation is exclusively the whole-prompt exact command `confirm-next`. "可以，继续", "go ahead", or any paraphrase never advances the gate.
- The bridge never writes spec/plan documents; all document updates are engine transactions gated on two passing test runs plus a checkpoint.

## Steps

1. On explicit workflow start, run `start`.
2. Run `start-module` with a sanitized event id for the first pending module.
3. Let the core CLI execute the configured unit command, then the regression command.
4. Record both results via `record-test`; failures keep the module in `testing`.
5. When the user gives their checkpoint, record it via `record-checkpoint`.
6. Only when BOTH test gates pass and the checkpoint is complete, relay the exact `confirm-next` requirement.
7. After the user types `confirm-next`, forward it via `confirm-next`; report the resulting module transition verbatim.
8. Repeat for remaining modules until `status` reports session completed.
9. If anything conflicts, run `recover` and follow its remediation; never hand-edit `.spec-driven/`.
