---
name: spec-driven-development
description: Drive modular coding work from spec and plan with unit and regression gates.
---

# Spec-Driven Development

1. Run `spec-driven start --project <root>` when the user explicitly starts this workflow.
2. If discovery reports multiple candidates or unclear modules/tests, show the candidates and wait for a user selection; do not guess.
3. Submit `module_started` through `spec-driven start-module`, then implement only the current module MVP.
4. Run the configured module unit command and full regression command. Submit each real exit code and controlled summary through `spec-driven record-test`.
5. If either test fails, remain in `testing`, report the failure, fix it, and rerun both required commands.
6. After both pass, submit a checkpoint containing completed points and later-module notes.
7. Show the evidence and ask the user to type exactly `confirm-next`.
8. Replies such as “继续” or “可以” are not authorization. Repeat the exact-command request without editing spec or plan.
9. Submit the exact confirmation through `spec-driven confirm-next`; only the core may update documents.
10. Run `spec-driven status` after each transition and `spec-driven recover` after interruption.
