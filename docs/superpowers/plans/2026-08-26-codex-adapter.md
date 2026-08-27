# Codex Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the core engine to OpenAI Codex CLI through its currently documented extensibility mechanisms (`notify` external-program events, custom prompts, and skills), declaring every missing capability explicitly and routing test evidence exclusively through the core CLI's own command execution.

**Architecture:** A thin adapter consists of a capability probe over `~/.codex/config.toml` and the environment, pure normalizers for the `notify` JSON payload, one entrypoint that receives the notify payload, and degraded explicit-command paths for what Codex cannot observe natively. Unlike Claude Code, Codex has no per-tool-result hooks, so `bash_exit_status` must be reported as unavailable and real exit codes come only from the core CLI executing the configured test commands itself. Registration edits `config.toml`'s `notify` key with backup/idempotency guarantees and installs prompt/skill assets as standalone files. All host shapes are fixture-locked against current documentation.

**Tech Stack:** Python 3.11+, standard `json`/`re`/`tomllib`/`subprocess`, existing `spec_driven` event/engine interfaces, Codex `config.toml`, Codex custom prompts (`~/.codex/prompts/`) and skills (`~/.codex/skills/`), `pytest`.

## Global Constraints

- Requires `2026-08-26-spec-driven-core-baseline.md`.
- The adapter never parses arbitrary natural-language confirmation as authorization.
- Only an exact configured command `confirm-next` (as a discrete prompt/command, not prose containing it) can create `next_module_confirmed`.
- Codex provides no native per-tool result hook: `bash_exit_status` must be declared degraded/unavailable in the capability report; test evidence may enter only via the core CLI running the configured test command and observing the real exit code itself. Copying "passed"/exit hints out of agent-visible log text is forbidden.
- Notify failures fail closed for confirmation and emit a diagnostic; they do not silently update documents.
- Exact `notify` invocation form (payload position/stdin), event type strings, `config.toml` keys, custom-prompt directory, and skill directory must be copied from the currently installed/documented Codex CLI during implementation and locked by contract fixtures; no guessed field or key is permitted. If documentation disagrees with any example in this plan, documentation wins and the plan section is corrected in the same commit.
- `config.toml` modification preserves unrelated user keys and comments-compatible formatting, is idempotent, backs up before mutation, and returns a receipt able to restore the previous bytes.
- Every task ends with focused tests, `python -m pytest -q`, and a focused commit.

---

## File structure

```text
src/spec_driven/adapters/codex.py
src/spec_driven/adapters/codex_hook.py
src/spec_driven/adapters/__init__.py            # re-export Codex surface alongside others
docs/adapters/codex-capabilities.md
install/manifests/codex.json
adapters/codex/config.fragment.toml
adapters/codex/prompts/confirm-next.md
adapters/codex/skills/spec-driven-development/SKILL.md
tests/contract/test_codex_contract.py
tests/unit/test_codex_adapter.py
tests/integration/test_codex_install.py
tests/e2e/test_codex_workflow.py
fixtures/codex/
  notify-turn-complete.json
  notify-unknown-event.json
  prompt-confirm-next.json
  prompt-natural-language.json
  config.toml
```

`codex.py` contains pure capability-probe and normalization functions. `codex_hook.py` is the only process entrypoint and contains no state policy beyond invoking the core CLI; it reads the notify payload from the location dictated by the verified contract (expected: `argv[1]`; adjust once verified). Prompt/skill files are copied verbatim by installation; the only merged mutation is the single `notify` key in `config.toml`.

---

### Task 1: Lock the Codex notify contract and capability report

**Files:**
- Create: `src/spec_driven/adapters/codex.py`
- Create: `tests/contract/test_codex_contract.py`
- Create: `fixtures/codex/notify-turn-complete.json`
- Create: `fixtures/codex/notify-unknown-event.json`
- Create: `fixtures/codex/prompt-confirm-next.json`
- Create: `fixtures/codex/prompt-natural-language.json`
- Create: `fixtures/codex/config.toml`

**Interfaces:**
- Consumes from core baseline: `Capability`, `CapabilityReport` (`schema_version`, `host`, `adapter_version`, `capabilities` tuple), `InvalidEventError`, `Event`, `TestEvidence` — exact names/types defined by core-baseline Task 2.
- Produces: `CodexCapabilities.detect(environment: Mapping[str, str], config_path: Path) -> CapabilityReport`.
- Produces: `normalize_notify_event(payload: Mapping[str, object]) -> Event | None` (returns `None` for non-session event types).
- Produces: `parse_explicit_confirmation(prompt: str, command: str) -> bool` and `normalize_confirmation(payload: Mapping[str, object], command: str) -> Event | None`.

- [x] **Step 1: Verify and freeze the Codex contract**

Read the currently installed Codex CLI documentation (`github.com/openai/codex/docs/config.md` or the matching docs site page; also run `codex --version`). Record in `docs/adapters/codex-capabilities.md`: how `notify` invokes the external program (argument position of the JSON payload), which event types exist today, whether any user-prompt or approval event reaches an external program, and the directories custom prompts and skills load from. Save one minimal valid JSON fixture per listed fixture using only documented field names. If an expected capability (e.g., a prompt-submission event) does not exist at all, still create the fixture shaped like the closest documented artifact and mark the capability degraded — the degraded path is tested, not skipped.

- [x] **Step 2: Write failing contract tests**

```python
import json
from pathlib import Path

from spec_driven.adapters.codex import (
    normalize_confirmation,
    normalize_notify_event,
    parse_explicit_confirmation,
)


FIXTURES = Path("fixtures/codex")


def _load(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_notify_turn_complete_normalizes_to_versioned_event() -> None:
    event = normalize_notify_event(_load("notify-turn-complete.json"))
    assert event is not None
    assert event.type == "session_turn_completed"
    assert event.schema_version == 1
    assert event.session_id


def test_unknown_notify_event_returns_none() -> None:
    assert normalize_notify_event(_load("notify-unknown-event.json")) is None


def test_only_exact_confirmation_command_is_accepted() -> None:
    assert parse_explicit_confirmation("confirm-next", "confirm-next") is True
    assert parse_explicit_confirmation("confirm-next --extra", "confirm-next") is False
    assert parse_explicit_confirmation("继续下一个模块", "confirm-next") is False
    assert parse_explicit_confirmation("please confirm-next now", "confirm-next") is False
    assert parse_explicit_confirmation("confirm-next", "advance") is False


def test_natural_language_prompt_does_not_create_event() -> None:
    assert normalize_confirmation(_load("prompt-natural-language.json"), "confirm-next") is None
```

- [x] **Step 3: Run contract tests to verify they fail**

Run:

```bash
python -m pytest tests/contract/test_codex_contract.py -q
```

Expected: import errors for the adapter functions.

- [x] **Step 4: Implement normalization with explicit field validation**

`src/spec_driven/adapters/codex.py` (event-type strings and payload keys must match the Step 1 verification; the code below shows the target invariant, not a guess to be kept blindly):

```python
from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from ..capabilities import Capability, CapabilityReport
from ..errors import InvalidEventError
from ..models import Event


class CodexCapabilities:
    @staticmethod
    def detect(environment: Mapping[str, str], config_path: Path) -> CapabilityReport:
        del environment
        configured = False
        if config_path.is_file():
            try:
                import tomllib

                with config_path.open("rb") as handle:
                    config = tomllib.load(handle)
                configured = bool(config.get("notify"))
            except Exception:  # malformed user TOML is a degradation, not a crash
                configured = False
        status = "available" if configured else "degraded"
        return CapabilityReport(
            schema_version=1,
            host="codex",
            adapter_version="0.1.0",
            capabilities=(
                Capability("session_events", status, "notify external program", "turn lifecycle is observable", "install notify bridge"),
                Capability("bash_exit_status", "unavailable", "no per-tool hook in Codex", "core CLI must execute tests itself", "run tests via spec-driven gate"),
                Capability("explicit_confirmation", status, "custom prompt exact command", "only confirm-next can authorize", "use the generic CLI command"),
                Capability("document_update", status, "local core CLI", "core gate controls writes", "run spec-driven doctor"),
            ),
        )


def _required(payload: Mapping[str, object], *keys: str) -> list[object]:
    values = [payload.get(key) for key in keys]
    if any(value in (None, "") for value in values):
        raise InvalidEventError(f"Codex notify payload is missing: {keys}")
    return values


def normalize_notify_event(payload: Mapping[str, object]) -> Event | None:
    kind = str(payload.get("type", ""))
    if kind != "agent-turn-complete":
        return None
    session_id, occurred_at = _required(payload, "session_id", "timestamp")
    return Event(
        event_id=f"{session_id}:session_turn_completed:{occurred_at}",
        schema_version=1,
        session_id=str(session_id),
        type="session_turn_completed",
        occurred_at=str(occurred_at),
        source="codex",
        actor="host",
        module_id=None,
        payload={"cwd": str(payload.get("cwd", ""))},
    )


def parse_explicit_confirmation(prompt: str, command: str) -> bool:
    return bool(re.fullmatch(re.escape(command), prompt.strip()))


def normalize_confirmation(payload: Mapping[str, object], command: str) -> Event | None:
    prompt = str(payload.get("prompt", ""))
    if not parse_explicit_confirmation(prompt, command):
        return None
    session_id, module_id, occurred_at = _required(payload, "session_id", "module_id", "timestamp")
    return Event(
        event_id=f"{session_id}:confirm:{module_id}:{occurred_at}",
        schema_version=1,
        session_id=str(session_id),
        type="next_module_confirmed",
        occurred_at=str(occurred_at),
        source="codex",
        actor="user",
        module_id=str(module_id),
        payload={"confirmation": "explicit_command"},
    )
```

The implementer must adapt `"agent-turn-complete"`, extraction keys, and directory names to whatever Step 1 verified. Invariants that never change: unknown event types return `None`; missing identity fields raise `InvalidEventError`; confirmation matches only the whole stripped prompt equal to the command.

- [x] **Step 5: Run contract tests and the full suite**

Run:

```bash
python -m pytest tests/contract/test_codex_contract.py -q
python -m pytest -q
```

Expected: contract fixtures pass and all core tests remain green.

- [x] **Step 6: Commit the contract adapter**

```bash
git add src/spec_driven/adapters/codex.py tests/contract/test_codex_contract.py fixtures/codex
git commit -m "feat: add Codex notify normalization"
```

---

> **Implementation notes (Task 1 complete):**
> - Raw `notify` payloads lack session/timestamp identity; the installed bridge (Task 2) wrapper-injects `session_id`/`timestamp` into payloads before dispatch — fixtures/codex/notify-turn-complete.json documents this shape. Later tasks must NOT assume Codex itself provides these fields.
> - `_safe_event_id` is mandatory: event ids become filenames under `.spec-driven/events/`, so every host-derived id (session ids, timestamps) must pass through it before constructing an Event.
> - Malformed user TOML must degrade capability detection (`degraded`), never crash — the installer in Task 3 must follow the same philosophy.
> - Tests reference models via module import (`import spec_driven.models as ...`) if dataclasses are needed, to avoid PytestCollectionWarning.

### Task 2: Implement the notify bridge and fail-closed confirmation path

**Files:**
- Create: `src/spec_driven/adapters/codex_hook.py`
- Create: `tests/unit/test_codex_adapter.py`
- Create: `tests/integration/test_codex_hooks.py`

**Interfaces:**
- Consumes from Task 1: `normalize_notify_event`, `normalize_confirmation`, `CodexCapabilities.detect`.
- Consumes from core baseline: `SpecDrivenError`, `Event`, `TestEvidence`, and the core CLI subprocess interface used by the Claude Code adapter hook.
- Produces: `dispatch(payload: Mapping[str, object], project_root: Path, env: Mapping[str, str]) -> HookResult`.
- Produces: `HookResult(exit_code: int, response: Mapping[str, object], emitted: tuple[Event | TestEvidence, ...])`.
- Produces: `main(argv: list[str] | None = None) -> int` — reads the JSON payload from the verified position (default `argv[1]`), emits each event to the core CLI, and always exits `0` unless the payload is structurally unusable (exit `2`); notify output controls nothing at runtime, so unlike Claude Code it must never block on a nonzero exit.

- [x] **Step 1: Write tests for dispatch decisions**

```python
from pathlib import Path

from spec_driven.adapters.codex_hook import dispatch


def test_natural_language_is_non_mutating_context(tmp_path: Path) -> None:
    payload = {
        "type": "user-prompt",
        "session_id": "s1",
        "timestamp": "2026-08-27T00:00:00Z",
        "module_id": "M1",
        "prompt": "可以，继续",
    }
    result = dispatch(payload, tmp_path, {"SPECDRIVEN_CONFIRMATION_COMMAND": "confirm-next"})
    assert result.exit_code == 0
    assert result.emitted == ()
    assert "confirm-next" in str(result.response)


def test_exact_confirmation_emits_core_event(tmp_path: Path) -> None:
    payload = {
        "type": "user-prompt",
        "session_id": "s1",
        "timestamp": "2026-08-27T00:00:00Z",
        "module_id": "M1",
        "prompt": "confirm-next",
    }
    result = dispatch(payload, tmp_path, {"SPECDRIVEN_CONFIRMATION_COMMAND": "confirm-next"})
    assert result.emitted[0].type == "next_module_confirmed"


def test_turn_complete_event_is_forwarded(tmp_path: Path) -> None:
    payload = {"type": "agent-turn-complete", "session_id": "s1", "timestamp": "2026-08-27T00:00:00Z"}
    result = dispatch(payload, tmp_path, {})
    assert result.emitted[0].type == "session_turn_completed"
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/unit/test_codex_adapter.py tests/integration/test_codex_hooks.py -q
```

Expected: import error for `codex_hook`.

- [x] **Step 3: Implement dispatch and core delegation**

`src/spec_driven/adapters/codex_hook.py`:

```python
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ..errors import SpecDrivenError
from ..models import Event, TestEvidence
from .claude_code_hook import emit_to_core
from .codex import normalize_confirmation, normalize_notify_event


@dataclass(frozen=True)
class HookResult:
    exit_code: int
    response: Mapping[str, object]
    emitted: tuple[Event | TestEvidence, ...]


def dispatch(payload: Mapping[str, object], project_root: Path, env: Mapping[str, str]) -> HookResult:
    del project_root
    kind = str(payload.get("type", ""))
    command = env.get("SPECDRIVEN_CONFIRMATION_COMMAND", "confirm-next")
    try:
        if kind == "user-prompt":
            confirmation = normalize_confirmation(payload, command)
            if confirmation is None:
                return HookResult(0, {
                    "status": "context",
                    "message": f"Spec-driven workflow requires explicit `{command}` after both test gates pass.",
                }, ())
            return HookResult(0, {"status": "ok"}, (confirmation,))
        event = normalize_notify_event(payload)
        if event is None:
            return HookResult(0, {"status": "ignored"}, ())
        return HookResult(0, {"status": "ok"}, (event,))
    except SpecDrivenError as error:
        return HookResult(2, {"status": "error", "reason": f"{error.code}: {error}"}, ())


def main(argv: list[str] | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else argv
    try:
        payload = json.loads(raw_argv[0])
    except (IndexError, ValueError):
        json.dump({"status": "error", "reason": "missing or invalid JSON payload argument"}, sys.stdout)
        sys.stdout.write("\n")
        return 2
    result = dispatch(payload, Path.cwd(), os.environ)
    emit_to_core(result.emitted, env=os.environ)
    json.dump(result.response, sys.stdout)
    sys.stdout.write("\n")
    return result.exit_code
```

Requirements locked here regardless of host-shape adjustments: reuse the shared `emit_to_core` helper extracted in the Claude Code hook rather than duplicating subprocess logic; the bridge process never writes spec/plan itself; a rejected confirmation produces a diagnostic message naming the exact command, never a document write.

- [x] **Step 4: Add failure-path tests**

Cover: payload argument missing or unparseable JSON (exit `2`, documents untouched), unknown event types ignored silently, missing module ID on confirmation (nonzero/stable error response), core CLI rejection while gates are open (confirmation refused with actionable reason). Each case must leave both documents byte-identical and everything under `.spec-driven/` unchanged apart from audit events.

- [x] **Step 5: Run integration tests and the full suite**

Run:

```bash
python -m pytest tests/unit/test_codex_adapter.py tests/integration/test_codex_hooks.py -q
python -m pytest -q
```

Expected: exact confirmation reaches the core, natural language only receives context, and all failure paths fail closed.

- [x] **Step 6: Commit the dispatcher**

```bash
git add src/spec_driven/adapters/codex_hook.py tests/unit/test_codex_adapter.py tests/integration/test_codex_hooks.py
git commit -m "feat: add fail-closed Codex notify bridge"
```

---

> **Implementation notes (Task 2 complete):**
> - `emit_to_core` lives in `adapters/_core_bridge.py`, NOT in `claude_code_hook.py` as the plan snippet imports — import from `._core_bridge` (plan's intent, shared helper).
> - Codex bridge is the OPPOSITE fail mode of Claude Code hooks: notify output controls nothing, so core rejection must be REPORTED (`status: "error", reason: "CORE_REJECTED: …"`) while still exiting 0; only structural payload failures exit 2. Never copy Claude Code's blocking behavior here.
> - `main()` reads the payload at argv[1] position because Codex passes it as one JSON argument; response is a single JSON line on stdout.
> - Missing module_id on confirmation raises InvalidEventError inside `normalize_confirmation` → dispatch returns exit 2 with `{code, message}`; documents untouched.

### Task 3: Register the notify bridge, custom prompt, and skill safely

**Files:**
- Create: `adapters/codex/config.fragment.toml`
- Create: `adapters/codex/prompts/confirm-next.md`
- Create: `adapters/codex/skills/spec-driven-development/SKILL.md`
- Create: `install/manifests/codex.json`
- Create: `tests/integration/test_codex_install.py`
- Modify: `src/spec_driven/install.py` (add Codex operations only if the productization installer exists; otherwise install.py ships as part of this plan with the minimal merge/copy/receipt functions defined below)

**Interfaces:**
- Consumes: none new from earlier Codex tasks beyond `emit_to_core` reachability.
- Produces: `merge_toml_fragment(config_path: Path, fragment: Mapping[str, object]) -> InstallReceipt` — sets top-level scalar/array keys only (the `notify` key), preserves all other bytes/keys, refuses to overwrite an existing different value (reports a conflict requiring manual resolution), backs up before mutating, and restores exact prior bytes on rollback.
- Produces: `InstallReceipt(backup_path: Path, applied_keys: tuple[str, ...])` with `rollback(receipt)` restoring byte-identical content.
- Produces: `copy_assets(source_dir: Path, codex_home: Path) -> None` — copies `prompts/` files into `<codex_home>/prompts/` and `skills/` trees into `<codex_home>/skills/` atomically (temp file + rename), idempotent (same bytes → no-op).
- The manifest `install/manifests/codex.json` declares host `"codex"`, the config fragment, the prompt/skill assets, and the verify command (`spec-driven doctor --host codex`).

- [x] **Step 1: Write the TOML merge and asset-copy tests**

```python
import shutil
import subprocess
from pathlib import Path

from spec_driven.install import copy_assets, merge_toml_fragment, rollback


def _read(path: Path) -> bytes:
    return path.read_bytes()


def test_merge_sets_notify_and_preserves_existing_content(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    original = b'# my prefs\nmodel = "o5"\napproval_policy = "never"\n'
    config.write_bytes(original)
    receipt = merge_toml_fragment(config, {"notify": ["python", "/opt/spec-driven/codex-hook"]})
    text = config.read_text(encoding="utf-8")
    assert 'model = "o5"' in text
    assert "# my prefs" in text
    assert 'notify = ["python", "/opt/spec-driven/codex-hook"]' in text
    rollback(receipt)
    assert _read(config) == original


def test_merge_is_idempotent_for_identical_value(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    fragment = {"notify": ["python", "/opt/spec-driven/codex-hook"]}
    merge_toml_fragment(config, fragment)
    once = _read(config)
    receipt = merge_toml_fragment(config, fragment)
    assert receipt.applied_keys == ()  # nothing changed on second pass
    assert _read(config) == once


def test_merge_refuses_conflicting_value(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text('notify = ["other"]\n', encoding="utf-8")
    try:
        merge_toml_fragment(config, {"notify": ["python", "/x"]})
        raised = False
    except Exception:
        raised = True
    assert raised
    assert 'notify = ["other"]' in config.read_text(encoding="utf-8")


def test_copy_assets_is_idempotent(tmp_path: Path) -> None:
    repo_root = Path(__file__).parents[2]
    copy_assets(repo_root / "adapters/codex", tmp_path)
    first = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    copy_assets(repo_root / "adapters/codex", tmp_path)
    second = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert first == second
```

- [x] **Step 2: Run the tests to verify they fail**

Run:

```bash
python -m pytest tests/integration/test_codex_install.py -q
```

Expected: import error for `merge_toml_fragment`/`copy_assets`.

- [x] **Step 3: Author the fragment, prompt, and skill assets**

`adapters/codex/config.fragment.toml` contains exactly the verified notify key:

```toml
# Managed by spec-driven-development; see docs/adapters/codex-capabilities.md
notify = ["python", "<absolute path to installed codex_hook shim>"]
```

`adapters/codex/prompts/confirm-next.md` instructs the model to invoke `spec-driven confirm-next` with no free-text alteration and to relay the CLI's result verbatim. `adapters/codex/skills/spec-driven-development/SKILL.md` mirrors the generic fallback skill: start/status/checkpoint/confirm-next/recover/doctor semantics plus the statement that test evidence in Codex mode is only ever produced by the core CLI executing the commands itself. Adapt prompt/skill frontmatter to the verified current format (name, description keys) — wrong frontmatter means the host ignores the file, so verify with an installed Codex binary if available and note the checked version.

- [x] **Step 4: Add capability documentation**

`docs/adapters/codex-capabilities.md` records the docs/version date checked in Task 1 Step 1 and a table with rows: turn lifecycle, Bash success/failure capture, explicit confirmation, document update, and natural-language confirmation — each with mechanism, fields consumed, availability, and generic fallback. State plainly that Bash exit codes are unavailable via Codex events and that the gate therefore relies on core CLI-executed tests.

- [x] **Step 5: Run installation tests and full regression**

Run:

```bash
python -m pytest tests/integration/test_codex_install.py tests/contract/test_codex_contract.py -q
python -m pytest -q
```

Expected: merge preserves unrelated keys and comments, idempotency holds, conflicting `notify` values are refused with guidance, rollback is byte-equivalent, and assets land under the right directories.

- [x] **Step 6: Commit Codex registration**

```bash
git add adapters/codex install/manifests/codex.json src/spec_driven/install.py tests/integration/test_codex_install.py
git commit -m "feat: register Codex notify and confirmation assets"
```

---

> **Implementation notes (Task 3 complete):**
> - Receipt type is `TomlInstallReceipt` and rollback fn is `rollback_toml` — plan said `InstallReceipt`/`rollback`, but those names are taken by the JSON installer; renaming keeps Claude Code tests untouched. Same semantics: `applied_keys == ()` ⇒ no-op, `backup_path is None` ⇒ file was created by us, so rollback deletes it.
> - TOML merge is TEXT-append based (`tomllib` read-only + managed block appended); comments/other keys survive byte-exact without a round-trip parser. If a future task needs to REMOVE or rewrite managed TOML values, it must parse→rewrite whole-file because positions inside the block shift.
> - Conflicting existing key value raises BEFORE any write — no partial mutation.
> - `copy_assets` treats identical bytes as no-op (idempotency by content, not timestamp), deletes stale differing files first, uses temp+os.replace per file.
> - Capability doc (Step 4 of this task) was authored at Task 1 time alongside the contract tests — keep them in sync when Codex ships new hook surfaces.

### Task 4: Prove the real end-to-end Codex gate

**Files:**
- Create: `tests/e2e/test_codex_workflow.py`

**Interfaces:**
- The E2E test drives notify/prompt fixtures through `dispatch` on a copied temporary fixture project and inspects core state, event files, and both documents.

- [x] **Step 1: Write the E2E scenario skeleton**

```python
import shutil
from pathlib import Path

from spec_driven.adapters.codex_hook import dispatch


ENV = {"SPECDRIVEN_CONFIRMATION_COMMAND": "confirm-next"}


def test_codex_flow_updates_documents_only_after_confirmation(tmp_path: Path) -> None:
    root = tmp_path / "project"
    shutil.copytree("fixtures/markdown-project", root)
    before_spec = (root / "docs/specs/product.md").read_bytes()
    before_plan = (root / "docs/plans/product-plan.md").read_bytes()
    natural = dispatch({
        "type": "user-prompt",
        "prompt": "可以",
        "session_id": "s",
        "module_id": "M1",
        "timestamp": "t",
    }, root, ENV)
    assert natural.emitted == ()
    assert (root / "docs/specs/product.md").read_bytes() == before_spec
    assert (root / "docs/plans/product-plan.md").read_bytes() == before_plan
    # Produce evidence via the core CLI's own gated test execution (unit then regression),
    # submit checkpoint, then send exact confirmation; assert documents_updated exactly once,
    # module M1 completed, M2 activated, and repeat-submission deduplicated.
```

- [x] **Step 2: Run the E2E test to verify it fails**

Run:

```bash
python -m pytest tests/e2e/test_codex_workflow.py -q
```

Expected: the degraded-evidence wiring is incomplete.

- [x] **Step 3: Complete degraded-path assertions**

Use only the temporary copy, never the repository fixture in place. Assert:

- unit evidence enters via the core CLI gate command execution (real exit code recorded), not via adapter-supplied status;
- unit passing + regression failing leaves the module in `testing` with failure evidence retained;
- unit + regression both passing plus complete checkpoint reaches `awaiting_confirmation`;
- natural language leaves both documents unchanged;
- exact `confirm-next` causes one `documents_updated` event, completes `M1`, updates spec and plan, activates `M2`;
- repeating the identical confirmation/event ID appends no second update;
- all state remains under `.spec-driven/`.

- [x] **Step 4: Run all tests**

Run:

```bash
python -m pytest tests/e2e/test_codex_workflow.py -q
python -m pytest -q
```

Expected: the full Codex-degraded gate passes offline using host-shaped fixtures.

- [x] **Step 5: Commit the end-to-end proof**

```bash
git add tests/e2e/test_codex_workflow.py
git commit -m "test: prove Codex gated workflow with degraded evidence path"
```

> **Implementation notes (Task 4 complete):**
> - `session_state` after a completed checkpoint stays `active` at session level; the awaiting state lives on the MODULE (`module_states["M1"] == "awaiting_confirmation"`). Never assert session-level "awaiting_confirmation" — that string does not exist.
> - Real exit codes here come from `subprocess.run(shlex.split(configured_command))` executed inside the copied project, then flow through core CLI `record-test --input -` — never from adapter flags. Config commands are injected with `json.dumps()` so `-c` payloads are YAML-safe.
> - Replay dedup requires byte-identical canonical event id: dispatch twice with SAME timestamp/session, forward both through `emit_to_core`, which runs child CLIs against Path.cwd() → chdir into the project copy around the calls.
> - A gate-refused checkpoint via raw CLI exits nonzero BEFORE any document write; assertion on exit code is enough, no doc comparison needed there.

## Codex acceptance checklist

- [x] Capability report marks `session_events` per real config state, `bash_exit_status` unavailable, and names the generic fallback for each gap.
- [x] Notify bridge forwards turn-completion events and never exits nonzero in ways Codex interprets as blocking.
- [x] Natural-language confirmation cannot create an event.
- [x] Test evidence originates only from the core CLI executing the configured commands; no log-derived exit codes anywhere.
- [x] `config.toml` merge is idempotent, conflict-refusing, backed up, and byte-exact on rollback.
- [x] Prompt and skill assets install atomically and idempotently.
- [x] A successful confirmation updates both spec and plan exactly once.
- [x] Failure paths leave documents byte-identical and provide actionable diagnostics.
