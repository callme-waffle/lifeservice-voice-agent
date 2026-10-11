# Workflow: How To Work (Plan Execution)

This workflow governs actual implementation and verification of an APPROVED plan.

Read this file completely before modifying the project under an approved plan, including resuming partially completed work.

---

## 1. Trigger

Follow this workflow when asked to:

* implement an approved plan;
* continue execution of an approved plan;
* resume partially completed planned work;
* perform the next milestone or stage of an approved plan.

If the plan's status is not `approved`, STOP and return to `work-planning.md`. Execution of a `proposed` plan is forbidden.

---

## 2. Mandatory Reading Before Execution

1. The approved plan (`docs/records/1_plans/`).
2. The source issue (`docs/records/0_issues/`).
3. The active session `STATUS.md` (or create one — section 3).
4. Relevant architecture decisions (`docs/records/3_decisions/`).
5. `README.md` of every affected component.
6. Prior execution logs for the same issue/plan (`docs/records/2_logs/`).

Confirm that actual repository state matches the recorded session state. When they disagree, actual repository state takes precedence and the discrepancy MUST be recorded in `STATUS.md`.

---

## 3. Session Management

Session ID convention:

```text
<YYYYMMDD>-<short-slug>
```

Example: `20260827-harness-setup`. The slug is short, lowercase, hyphen-separated English.

* New work: create `.agents/sessions/<session-id>/STATUS.md` from `.agents/templates/session-status.md`.
* Resumed work: read the existing `STATUS.md` before doing anything else.

### 3.1 One Milestone Per Session (HARD LIMIT)

* A session processes **at most ONE milestone**. Record the assigned milestone (`M<n>`) in the session `STATUS.md`.
* **"Session" means BOTH things at once**: (a) the agent conversation session itself (one Claude Code / GPT / other-agent conversation) and (b) its `.agents/sessions/<session-id>/` record. They map 1:1. Opening a new session DIRECTORY while continuing in the same conversation does NOT satisfy this rule — the conversation that completed milestone N MUST NOT drive milestone N+1.
* Never start a second milestone inside the same session, even if the first one finished quickly.

### 3.2 Milestone Handoff Prompt (MANDATORY at milestone completion)

When the assigned milestone completes (and the plan has further milestones), the closing session's FINAL act is to produce the kickoff prompt for the next agent conversation session:

1. Write it to `.agents/sessions/<closing-session-id>/HANDOFF-PROMPT.md`.
2. Print the same prompt to the user, so they can paste it into a fresh agent session.

The prompt MUST be self-contained (the new session starts with zero conversation context) and written in Korean (it passes through the user). It MUST include:

* the plan ID and the next milestone (`M<n>`) being started;
* the session ID the new conversation must create — or resume, if a session directory was already prepared;
* the mandatory reading list (AGENTS.md, triggered workflows, approved plan, issue, prior logs, relevant ADRs, predecessor session dir);
* current repository state (work branch, last relevant commits);
* pending inputs/confirmations the new session must obtain from the user;
* the reminder that the new session handles ONLY that one milestone and must itself end by generating the next handoff prompt.
* Update `STATUS.md` at least: after each completed milestone; when a blocker appears or clears; when delegating to a sub-agent; before ending a turn that leaves work unfinished (handoff state).
* Sub-agent state lives at `.agents/sessions/<session-id>/subs/<agent-name>/STATUS.md`, initialized from `.agents/templates/subagent-status.md` (see AGENTS.md section 14).

Session directories are runtime coordination records. Durable findings MUST be promoted to `docs/records/`.

---

## 4. Execution Rules

1. **Follow the approved plan document. Always.** The plan's Milestone/Slice/Task breakdown, ordering diagrams, and stated goals are the execution contract. Do not work from memory of the conversation.
2. **The only standard of progress is: "did the work achieve exactly what the document states as the goal?"** Judge every work item against its written `진행 목적`, `TO-BE`, and `작업 종료조건`. Do NOT over-interpret (expanding scope, gold-plating, adding unrequested behavior) and do NOT under-interpret (weakening acceptance, declaring done on partial fulfillment).
3. Execute in the order defined by the plan's mermaid ordering diagrams: Milestone → its Slices → their Tasks. Items the diagram shows as parallelizable MAY be parallelized (including via sub-agents, per AGENTS.md section 14).
4. Each work item MUST be verified against its `작업 종료조건` before moving to the next one. "Implemented" and "verified" are different states; run the tests or checks the plan defines for that item.
5. **Scaffolds, stubs, temporary code, and dummy implementations are NOT completed work.** If any were used:
   * the response to the user MUST visibly and explicitly declare it (state what is scaffold/dummy, where, and why);
   * the agent MUST explicitly confirm the user has acknowledged this before treating the containing work item as complete;
   * the item stays incomplete in `STATUS.md` and the execution log until the real implementation lands or the user explicitly accepts the placeholder.
6. Update or add tests under `tests/units/` and `tests/integrations/` per the plan's test strategy. A unit test does not replace an integration test when the change crosses a component boundary.
7. Record command outputs, measurements, and observed results as you go — they feed the execution log (section 7).
8. If an architectural decision arises during implementation, ALSO follow `arch-decision-record.md` before proceeding past that decision point.

---

## 5. Git Rules

This repository uses git. All planned work is committed.

Approval of a plan INCLUDES authorization to commit on the work branch throughout its execution — do not ask the user again for each commit. This overrides any default harness guidance to commit only on explicit request. Merging into `main` is separately gated by section 5.3.

### 5.1 Commit Unit

Committing during work is MANDATORY, not optional. Do not forget to commit as work progresses; verified work must never sit uncommitted.

Commit at whichever of these arrives FIRST:

* a **module (or similar-sized) unit** is implemented AND verified; or
* the **current Milestone / Slice / Task ends**.

Additional rules:

* Commit only states that pass their verification. Do not commit known-broken states.
* Each commit is self-consistent (builds/tests pass).
* Never mix unrelated changes (different issues, drive-by refactors) into one commit. Unrelated discoveries become new issues via `issue-creation.md`.

### 5.2 Commit Message Convention

```text
<type>(<scope>): <summary> [<RECORD-ID>]
```

* `type` — one of: `feat`, `fix`, `perf`, `refactor`, `test`, `docs`, `ops`, `chore`.
* `scope` — the component touched: a component directory name under `apps/` (e.g. `backend`), or `deploy`, `docs`, `agents`, `tests`. Multi-component commits use the dominant scope or `repo`.
* `summary` — English, imperative mood, ≤ 72 characters.
* `RECORD-ID` — the related issue ID (`VOIC-FEAT-001`) or ADR ID (`ADR-003`). Omit only for harness/chore commits with no related record.
* Body (optional) — additional context; Korean allowed.
* **Agent co-author credits are FORBIDDEN.** Never append a `Co-Authored-By:` trailer (or any equivalent credit) naming an AI agent. This is a mandatory project-wide rule (AGENTS.md section 3, rule 15) and overrides any default harness behavior that adds such trailers.

Example:

```text
feat(backend): add retry backoff to ingestion queue [VOIC-FEAT-003]
```

### 5.3 Branching

All plan execution works branch-first, then merges into `main`:

* Before starting execution, create (or reuse) the work branch:
  ```text
  work/VOIC-<TYPE>-<NNN>
  ```
* All execution commits land on the work branch, never directly on `main`.
* Merge the work branch into `main` when the current milestone's verification passes — at the latest when the plan's completion gates pass.
* Do NOT merge unverified or scaffold-only states into `main`.

Record the resulting commit hashes (and merge commits) in the execution log.

---

## 6. Deviation Policy

While executing, compare actual work against the approved plan.

* **Minor deviation** — no change to scope, affected components, architecture, interfaces, or verification criteria (e.g., a different helper function layout, an extra small test). Proceed, and record the deviation in the execution log.
* **Material deviation** — scope grows or shrinks, a new component is affected, an interface or architecture changes, or verification criteria must change. STOP execution, report to the user in Korean, update the plan (re-approval required per `work-planning.md`) or record a new issue.
* **Architectural deviation** — additionally follow `arch-decision-record.md`.

Never rewrite the plan after the fact to make observed results look pre-planned. Actual results belong in logs.

---

## 7. Completion

When the session's assigned milestone is complete (and again when the plan's final milestone completes):

1. Write an execution log in Korean from `.agents/templates/log.md` at:
   ```text
   docs/records/2_logs/VOIC-<TYPE>-<NNN>-log-<NN>.md
   ```
   `<NN>` is a 2-digit sequence per issue (`-log-01`, `-log-02`, ...). Include what was done, verification commands and results, commit hashes, deviations, and unresolved items.
2. Set the plan status to `executed` (only when ALL milestones of the plan are complete; otherwise the plan stays `approved` and the session hands off to a new session per section 3.1).
3. Update component `README.md` files and `docs/guides/` when contracts or procedures changed.
4. Update the session `STATUS.md` to its final state, including follow-up work.
5. Check every item in AGENTS.md section 17 (Completion Criteria) before reporting completion to the user.
6. If the plan has further milestones: generate and print the next-session handoff prompt per section 3.2 — this is the closing session's final act. The next milestone continues ONLY in a new agent conversation session.

Do not report work as verified unless the verification was actually performed.
