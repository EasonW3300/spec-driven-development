# Product Specification

This document captures what the product must guarantee for every supported host.
The managed blocks below are updated only by the spec-driven core, never by hand.

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

Constraints outside managed blocks stay untouched across module completions.
