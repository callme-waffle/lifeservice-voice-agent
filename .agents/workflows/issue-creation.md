# Workflow: Issue Creation

This workflow governs how a new engineering work item is recorded under `docs/records/0_issues/`.

Read this file completely before creating or formalizing any issue.

---

## 1. Trigger

Follow this workflow when the user:

* reports a problem or unexpected system behavior;
* requests investigation of a defect;
* requests a new feature or capability;
* requests a meaningful behavioral change;
* identifies a performance, operational, or architectural problem;
* introduces any other task that should be tracked as a distinct engineering work item.

The conversation does not need to contain the literal word "issue".

---

## 2. Preconditions

Before creating the issue:

1. Read the active session `STATUS.md` if a session exists.
2. Search `docs/records/0_issues/` for an existing issue covering the same problem.
   * If a matching issue exists, do NOT create a duplicate. Report the existing issue to the user and ask whether to extend it or create a genuinely new item.
3. Read the `README.md` of every component the issue concerns.
4. Read related records under `docs/records/` (plans, logs, decisions) when they exist.

---

## 3. Issue Type Codes

Every issue MUST use exactly one of the following type codes:

| Code | Meaning |
| --- | --- |
| `BUG` | Defect, unexpected behavior, incorrect result |
| `FEAT` | New feature or capability, meaningful behavioral change |
| `PERF` | Performance problem or performance improvement target |
| `OPS` | Operational, deployment, or infrastructure concern |

Do not invent additional type codes. If a new type appears necessary, ask the user first.

If the correct type is ambiguous from the conversation (e.g., `PERF` vs `FEAT` hinges on whether an implementation already exists), ask the user BEFORE allocating the ID. Derived records inherit the issue ID (section 5), so a wrongly typed ID contaminates every downstream record.

---

## 4. ID Allocation

Issue IDs use the form:

```text
VOIC-<TYPE>-<NNN>
```

* `<TYPE>` is one of the codes above.
* `<NNN>` is a zero-padded 3-digit sequence number.
* Numbering is a SINGLE global sequence shared across all types (not per-type).

Allocation procedure:

1. List every file in `docs/records/0_issues/`.
2. Extract the numeric part of every existing issue ID regardless of type.
3. The new number is `max + 1` (or `001` when the directory is empty).

Example: if `VOIC-BUG-001.md` and `VOIC-FEAT-002.md` exist, the next issue is `VOIC-<TYPE>-003`.

---

## 5. File Naming

```text
docs/records/0_issues/VOIC-<TYPE>-<NNN>.md
```

No slug or date suffix in the filename. Derived records inherit the issue ID:

```text
docs/records/1_plans/VOIC-<TYPE>-<NNN>-plan.md
docs/records/2_logs/VOIC-<TYPE>-<NNN>-log-<NN>.md
```

---

## 6. Creation Steps

1. Copy `.agents/templates/issue.md` as the document skeleton. Do not invent a new format.
2. Write the document in Korean (repository language policy). Technical identifiers, code, commands, and raw logs may remain unchanged.
3. Fill the metadata table:
   * `이슈 ID` — allocated per section 4;
   * `생성 시간` — actual current time, `YYYY-MM-DD HH:MM:SS`;
   * `생성자` — the human user;
   * `생성 에이전트` — the agent model/name creating the record.
4. Describe in section 1 (`이슈 내용`):
   * background: why this matters now, observed behavior, environment;
   * the problem or requirement itself — WHAT needs attention and WHY.
5. Section 2 (`결정 사항`) records conclusions reached about the issue itself (e.g., confirmed scope, chosen direction at issue level). Leave it minimal at creation time if nothing is decided yet.
6. An issue MUST NOT contain an implementation plan. Design and sequencing belong in `docs/records/1_plans/` via `work-planning.md`.

---

## 7. User Confirmation

After creating the issue file:

1. Report a Korean summary of the issue (ID, type, problem statement) to the user.
2. Incorporate any corrections the user provides and update the file.
3. Do not proceed to planning (`work-planning.md`) unless the user requests a plan.

---

## 8. Postconditions

* The issue file exists at the correct path with a correctly allocated ID.
* The active session `STATUS.md` (if any) references the new issue.
* Related existing records are linked from the issue's reference section where applicable.
