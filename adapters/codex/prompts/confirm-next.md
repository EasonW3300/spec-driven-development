---
name: confirm-next
description: Advance the spec-driven workflow to the next module after both test gates pass.
---

# Confirm-next

Run exactly:

```
spec-driven confirm-next --project <root>
```

Rules (no exceptions):

1. Run the command only when the module's unit AND regression gates have both passed, as reported by `spec-driven status`.
2. Do not edit the command in any way and do not append free text before or after it.
3. Relay the command's output verbatim to the user, including any rejection reason.
4. If the core rejects the confirmation (e.g. a gate is still open), report the remediation verbatim; never work around the gate.

This prompt is intentionally exact-command-only: natural language such as "继续" or "looks good" must never be interpreted as confirmation.
