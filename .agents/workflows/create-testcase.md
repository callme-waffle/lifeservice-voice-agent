# Workflow: Test Case Creation

This workflow governs how test cases are created or modified under `tests/`.

Read this file completely before writing or changing any test case.

---

## 1. Trigger

Follow this workflow when:

* an approved plan's test strategy requires new or updated tests (during `how-to-work.md` execution);
* a `BUG` issue needs a reproduction test;
* the user requests test creation or test coverage improvement;
* a change crosses a component boundary that has no integration coverage;
* a fixed defect needs regression protection;
* existing tests must be updated because a documented behavior legitimately changed.

Test creation triggered inside plan execution remains subject to `how-to-work.md`; this workflow adds test-specific rules on top of it.

---

## 2. Preconditions

Before writing any test case, read:

1. the related issue and/or approved plan — especially its `작업 종료조건`, validation criteria, and test strategy;
2. the `README.md` of every component under test (testing requirements, runtime, commands);
3. existing tests under `tests/units/` and `tests/integrations/` for the same area — extend or update existing cases instead of duplicating them;
4. relevant ADRs under `docs/records/3_decisions/` when the tested behavior derives from an architectural decision;
5. for integration tests: the latest relevant PRD and SRS under `docs/ideas/` (section 3.3).

---

## 3. Placement Rules

Per AGENTS.md section 10:

| Location | Use for |
| --- | --- |
| `tests/units/` | Isolated units of application behavior; no full service topology, no external component integration |
| `tests/integrations/` | Behavior across boundaries: component ↔ component interfaces, storage/DB interaction, external API boundaries, multi-service execution |

Hard rules:

* A unit test never substitutes for an integration test when the behavior depends on an interface BETWEEN components. However, integration tests are NOT run automatically — they require double approval per section 4.
* Language, framework, and runner follow the component `README.md`. If the component README does not yet define a test framework, propose one to the user FIRST (this is often an ADR-worthy dependency choice — see `arch-decision-record.md`) instead of inventing one silently.

### 3.1 Unit Test Directory Structure

`tests/units/` MUST be organized in per-component subdirectories, in this exact hierarchy:

```text
tests/units/
└── <component>/
    ├── testcodes/
    │   └── {{ORIGIN_FILE_NAME}}.test.{{ext}}
    └── logs/
        └── M000_S000_T000-TRY{n}.md
```

* Level 1 — **component**: exactly one component directory name matching `apps/<component>/`.
* Level 2 — **`testcodes/`**: contains the test code; mirrors the module structure of the application under test (nested module subdirectories mirror the source layout). **`logs/`**: contains test run records (section 3.2).
* Level 3 (under `testcodes/`) — **one test file per source file**, named after the source file it tests:
  ```text
  {{ORIGIN_FILE_NAME}}.test.{{ext}}
  ```
  where `{{ext}}` is the component's source language extension (e.g., the tests for `chunker.py` live in `chunker.test.py`; the tests for `parser.ts` live in `parser.test.ts` — under the matching component/module path).
* The `.test.<ext>` suffix may not match the chosen framework's default collection patterns (e.g., pytest collects `test_*.py` / `*_test.py` by default). If so, configuring collection (e.g. `python_files = "*.test.py"` in `pyproject.toml` or `pytest.ini` for pytest) is a MANDATORY part of test framework setup — do it when the framework is first introduced, not after tests silently fail to collect.

Do not place test files directly under `tests/units/` or under a component directory outside `testcodes/`.

Integration tests keep the boundary/scenario layout:

```text
tests/integrations/<boundary-or-scenario>/...
```

### 3.2 Test Run Logs (`tests/units/<component>/logs/`)

Every test execution performed for a work unit MUST be recorded as a run log file under the corresponding component's `logs/` directory.

File naming:

```text
M000_S000_T000-TRY{n}.md
```

* The M/S/T identifiers use zero-padded 3-digit numbers of the work unit the run belongs to (per the plan's WBS numbering).
* Include ONLY the scope levels at which the test was executed:
  * Task-level run → `M003_S001_T002-TRY1.md`
  * Slice-level run → `M003_S001-TRY1.md`
  * Milestone-level run → `M003-TRY1.md`
* `TRY{n}` starts at 1 for the first run of a given scope and increments on every re-run of the same scope (never overwrite a previous TRY file — each run gets its own file).

Every run log MUST be created from `.agents/templates/test-run-log.md` and MUST contain:

1. **테스트 진행 시간** — when the run started/ended and how long it took;
2. **진행된 테스트케이스 목록** — every test case executed in the run;
3. **테스트케이스 별 통과 여부 체크리스트** — pass/fail per test case, as a checklist;
4. **실패 원인분석 결과** — root-cause analysis for every failed case (mandatory whenever any case failed).

### 3.3 Integration Test Basis (PRD / SRS)

Integration tests are authored against the **PRD and SRS** — i.e., from the project user's perspective, testing the features that must actually work, not internal implementation details.

* PRD and SRS live under:
  ```text
  docs/ideas/prd/{{UPDATED_VERSION_NAME}}.md
  docs/ideas/srs/{{UPDATED_VERSION_NAME}}.md
  ```
  where the version name follows the version under development at the time the document was updated.
* Before writing any integration test, read the latest relevant PRD and SRS versions. Each integration test case MUST trace to a concrete PRD/SRS requirement (reference the document and requirement in the test's docstring/comment, alongside the record ID).
* If no PRD/SRS covers the behavior an integration test would verify, STOP and report to the user — do not invent user-facing requirements.

---

## 4. Integration Test Approval Gates (Double Approval, MANDATORY)

Integration tests are NOT required for every work item. Because they exercise multiple stacks together, they are large and expensive (setup scale, execution time, token consumption). Therefore:

* **Gate 1 — planning stage (prior approval).** While producing the plan (`work-planning.md`), review whether the work actually requires integration testing. Record the review result and its reasoning in the plan's test strategy, and obtain the user's explicit PRIOR approval for running integration tests BEFORE work begins.
* **Gate 2 — immediately before execution (final approval).** Even with Gate 1 approval, ask the user once more right before actually creating/running the integration tests, and proceed only on explicit approval.

Additional rules:

* Never run integration tests without BOTH approvals. Skipping either gate is a workflow violation.
* If integration testing is skipped (not needed, or not approved), record the resulting coverage state explicitly in the plan and the execution log — a boundary-behavior gap must stay visible, never silently ignored.
* Gate approvals are per-plan (Gate 1) and per-execution (Gate 2); do not generalize one approval to other plans or later runs.

---

## 5. Test Case Requirements

Every test case MUST:

1. **Verify exactly what the source document states.** The assertion target is the documented behavior — the plan's `작업 종료조건`/검증 기준 or the issue's described behavior. Do not over-interpret (asserting unrequested behavior or implementation details) and do not under-interpret (asserting less than the documented goal).
2. **Make its intent visible.** State the purpose and target behavior in the test name and a docstring/comment, structured as given / when / then, with a deterministic pass-fail criterion.
3. **Reference its record ID.** Include the related issue ID (`VOIC-<TYPE>-<NNN>`) in the test name, docstring, or comment so the test traces back to its requirement.
4. **Be deterministic and independent.** No dependence on execution order, wall-clock time, randomness without a fixed seed, or leftover state; each test cleans up what it creates.

For `BUG` issues, write the **reproduction test first** and observe it FAIL against the unfixed code, then PASS after the fix. Record both observations in the execution log.

Forbidden — these do NOT count as test cases (same principle as the scaffold rule in `how-to-work.md` section 4):

* assertion-free tests;
* always-passing dummy tests;
* skipped/disabled placeholders counted as coverage;
* tests weakened (assertions removed/loosened) just to make them pass — a legitimately changed behavior requires the documented source (plan/issue) to change first.

---

## 6. Verification and Evidence

1. Run the new or changed tests and confirm the expected result (including the fail-then-pass sequence for reproduction tests).
2. Record every unit test run as a run log under `tests/units/<component>/logs/` per section 3.2, created from `.agents/templates/test-run-log.md`.
3. Record the executed command and output summary — in the execution log (`docs/records/2_logs/`, Korean) when part of plan execution, per `how-to-work.md` section 7.
4. Commit per `how-to-work.md` section 5, normally:
   ```text
   test(<scope>): <summary> [VOIC-<TYPE>-<NNN>]
   ```
   A reproduction test MAY be committed separately from (and before) the fix.

---

## 7. Postconditions

* Test cases exist in the correct location and structure (section 3.1 hierarchy for units; boundary layout for integrations) with visible intent and record-ID traceability.
* Integration tests, if any, were run only after both approval gates (section 4) passed; skipped integration coverage is explicitly recorded.
* The tests were actually executed and their results recorded — never report tests as passing without running them.
* No forbidden placeholder tests were introduced; any temporarily skipped test is explicitly reported to the user with a reason and a follow-up record.
* The session `STATUS.md` verification state reflects the new tests.
