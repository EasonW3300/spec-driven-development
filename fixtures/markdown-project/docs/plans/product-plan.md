# Product Implementation Plan

Work is split into ordered modules. Each module advances only after its unit and
regression gates pass plus explicit confirmation. Prose here differs from the spec
on purpose; only managed blocks are machine-written.

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

<!-- spec-driven:module id="M2" order="2" status="pending" -->
## M2: Host translation

Goal: Translate host events.

Acceptance:
- Host payloads normalize to versioned core events.

Tests: unit, regression

<!-- spec-driven:completion -->
Status: pending
Next module:
Completed points:
Notes:
Evidence:
<!-- /spec-driven:completion -->
<!-- /spec-driven:module -->

Delivery notes below the last block describe release checkpoints and ownership.
