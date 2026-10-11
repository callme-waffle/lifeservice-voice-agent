# AGENTS.md

This file is the primary entry point for all coding agents working in this repository (project: voice-agent).

Agents MUST read this file before inspecting, modifying, testing, or documenting the project.

The repository is designed as an agent-oriented project harness.
Persistent project knowledge, task records, session state, component documentation, and execution evidence are stored in explicit locations so that agents do not need to reconstruct project state from conversation history.

---

# 1. Repository Structure

```text
voice-agent/
├── .agents/
│   ├── sessions/
│   │   └── <session-id>/
│   │       ├── STATUS.md
│   │       └── subs/
│   │           └── <agent-name>/
│   │               └── STATUS.md
│   ├── templates/
│   └── workflows/
│       ├── issue-creation.md
│       ├── work-planning.md
│       ├── how-to-work.md
│       ├── create-testcase.md
│       └── arch-decision-record.md
│
├── apps/
│   └── <component>/
│       └── README.md
│
├── deploy/
│   └── package/
│       └── <version>/
│           └── PATCHNOTE.md
│
├── docs/
│   ├── guides/
│   ├── ideas/
│   │   ├── prd/
│   │   │   └── <version>.md
│   │   └── srs/
│   │       └── <version>.md
│   └── records/
│       ├── 0_issues/
│       ├── 1_plans/
│       ├── 2_logs/
│       └── 3_decisions/
│
├── scripts/
│
├── tests/
│   ├── integrations/
│   └── units/
│       └── <component>/
│           ├── testcodes/
│           └── logs/
│
├── AGENTS.md
└── README.md
```

Names enclosed in angle brackets such as `<session-id>`, `<agent-name>`, `<component>`, and `<version>` describe naming conventions only. They are not literal directories.

---

# 2. Language Policy

Language requirements depend on where information is being written and who is expected to consume it.

## 2.1 Human Interaction

All direct interaction between an agent and a human MUST be conducted in Korean.

This includes questions to the user, answers, progress reports, approval requests, clarification requests, summaries, warnings, completion reports, and explanations of findings or failures.

When communicating with a human, Korean is the default and mandatory human-facing language unless the user explicitly requests a different language for a specific output.

Technical identifiers do not need to be translated. Source code, commands, file paths, API names, class and function names, configuration keys, protocol names, raw logs, and external error messages SHOULD remain unchanged when appropriate. Explanations surrounding them MUST still be written in Korean.

## 2.2 Files Under `docs/`

All documents created under `docs/` MUST be written in Korean.

This includes, but is not limited to:

```text
docs/guides/
docs/ideas/
docs/records/0_issues/
docs/records/1_plans/
docs/records/2_logs/
docs/records/3_decisions/
```

Technical material that should preserve its original representation MAY remain unchanged (code, shell commands, identifiers, file paths, raw logs, stack traces, configuration, protocol names, product names, quoted external output). Any interpretation, description, rationale, conclusion, or surrounding explanation MUST be written in Korean.

## 2.3 Other Repository Documents

Documents outside `docs/` are not subject to the Korean-language requirement unless another rule explicitly requires it.

In particular, `.agents/` is primarily consumed and maintained by LLM agents. Files under `.agents/` (workflows, templates, sessions) MAY therefore be written in English when English provides clearer or more efficient instructions for agents.

Component `README.md` files and other technical documents outside `docs/` may use Korean or English according to their intended audience and existing project conventions.

---

# 3. General Agent Rules

All agents MUST follow these rules.

1. Read `AGENTS.md` first.
2. Identify whether one or more workflow trigger conditions apply.
3. Read every mandatory workflow before performing the corresponding task.
4. Read the root `README.md` when project-level context is required.
5. Identify the active session before starting or resuming substantial work.
6. Read the active session's `.agents/sessions/<session-id>/STATUS.md`.
7. Read the relevant component `README.md` before modifying that component.
8. Read existing issues, plans, decisions, and logs relevant to the task.
9. Use documents under `.agents/templates/` when creating structured repository records.
10. Do not invent a new document format when a corresponding template exists.
11. Keep session state and persistent repository records synchronized with actual work.
12. Do not declare work complete without recording the relevant verification result.
13. Do not treat conversation history as persistent project state when the same information should be recorded in the repository.
14. Follow the language requirements defined in this file.
15. Never credit an agent as a commit co-author. Git commits MUST NOT contain a `Co-Authored-By` trailer (or any equivalent authorship credit) naming an AI agent, under any circumstances. This is a mandatory, project-wide rule for all work performed in this repository, by all agents, at all times.

Repository files are the source of truth for persistent project state.

---

# 4. Workflow Routing

`.agents/workflows/` contains mandatory procedures for specific categories and stages of work.

Workflow selection is trigger-based. An agent MUST determine whether a workflow applies before beginning substantive work. Multiple workflows MAY apply during a single conversation or session.

For example:

```text
User reports a new problem
        ↓
issue-creation.md
        ↓
Issue created
        ↓
User requests an implementation plan
        ↓
work-planning.md
        ↓
Plan approved
        ↓
how-to-work.md
        ↓
Architectural decision occurs during implementation
        ↓
arch-decision-record.md
```

Workflow boundaries do not imply conversation boundaries.
An agent MUST transition to the appropriate workflow whenever its trigger condition becomes true.

## 4.1 `issue-creation.md`

Path: `.agents/workflows/issue-creation.md`

This workflow MUST be referenced when a new unit of project work needs to begin.

Trigger conditions include situations where the user:

* reports or mentions a problem;
* reports unexpected system behavior;
* requests investigation of a defect;
* requests a new feature or capability;
* requests a meaningful behavioral change;
* identifies a performance, operational, or architectural problem;
* introduces another task that should be tracked as a distinct engineering work item.

When one of these conditions applies, the agent MUST read the workflow before creating or formalizing the work item. The workflow governs creation of an issue under `docs/records/0_issues/`. The resulting issue MUST be written in Korean.

An issue records the problem, requirement, or work objective that starts the engineering lifecycle. A conversation does not need to contain the literal word "issue" for this workflow to apply.

## 4.2 `work-planning.md`

Path: `.agents/workflows/work-planning.md`

This workflow MUST be referenced when producing an implementation or improvement plan based on an issue already recorded under `docs/records/0_issues/`. The resulting plan is stored under `docs/records/1_plans/` and MUST be written in Korean.

The plan should define how the project will address the issue, including as applicable: scope, affected components, implementation sequence, dependencies, risks, validation criteria, test strategy, rollout or migration requirements, and completion gates.

`work-planning.md` governs planning. It does not itself authorize execution.

The agent MUST clearly distinguish between:

```text
proposed plan
approved plan
executed plan
```

A plan MUST NOT be treated as approved solely because it exists in `docs/records/1_plans/`.

## 4.3 `how-to-work.md`

Path: `.agents/workflows/how-to-work.md`

This workflow MUST be referenced before executing an approved plan from `docs/records/1_plans/`. This is a mandatory execution workflow.

If the agent is asked to:

* implement an approved plan;
* continue execution of an approved plan;
* resume partially completed planned work;
* perform the next milestone or stage of an approved plan;

the agent MUST read the workflow before modifying the project.

The agent must also read:

1. the approved plan;
2. the related issue;
3. the active session status;
4. relevant architecture decisions;
5. affected component documentation;
6. relevant prior execution logs.

`how-to-work.md` governs actual implementation and verification behavior. Execution evidence generated while following the plan should be recorded under `docs/records/2_logs/` when the work or workflow requires durable evidence. Such records MUST be written in Korean.

## 4.4 `create-testcase.md`

Path: `.agents/workflows/create-testcase.md`

This workflow MUST be referenced whenever test cases are created or modified under `tests/units/` or `tests/integrations/`.

Trigger conditions include situations where:

* an approved plan's test strategy requires new or updated tests;
* a defect needs a reproduction or regression test;
* the user requests test creation or coverage improvement;
* a change crosses a component boundary that lacks integration coverage;
* existing tests must change because a documented behavior legitimately changed.

The workflow governs test placement (`units` vs `integrations`), required test case content and traceability to record IDs, reproduction-test rules for defects, forbidden placeholder tests, and how test evidence is recorded.

Test creation that occurs while executing an approved plan remains subject to `how-to-work.md`; both workflows apply cumulatively.

## 4.5 `arch-decision-record.md`

Path: `.agents/workflows/arch-decision-record.md`

This workflow MUST be referenced whenever architectural decision context appears during a conversation or task, regardless of whether architecture was the original purpose of the conversation.

Trigger conditions include discussion or selection of: system architecture; service boundaries; component responsibilities; data flow; storage architecture; database technology; model selection when it materially affects system architecture; deployment architecture; communication protocols; integration patterns; runtime topology; infrastructure structure; significant dependency choices; durable technical trade-offs; replacement of one architectural approach with another; explicit rejection of a meaningful architectural alternative.

When architectural context reaches the point where a durable decision is made or an existing decision is materially changed, the agent MUST read the workflow and follow its rules for recording the decision under `docs/records/3_decisions/`. Architecture decision records MUST be written in Korean.

The workflow should be consulted even if the architectural decision emerges incidentally — while investigating an issue, preparing a plan, implementing, reviewing code, debugging, discussing deployment, or answering a user question. Architectural context MUST NOT be allowed to disappear solely because it originated in conversation.

---

# 5. Agent Harness

## 5.1 `.agents/sessions/`

Stores runtime state for individual agent sessions.

```text
.agents/sessions/<session-id>/
```

A session represents one bounded unit of agent-driven work: implementing an approved feature, investigating a defect, performing a refactoring task, running a benchmark, preparing a release, executing an approved plan.

Session directories are runtime coordination records, not permanent project-history records. Permanent findings belong under `docs/records/`.

## 5.2 Session `STATUS.md`

Path: `.agents/sessions/<session-id>/STATUS.md`

This file describes the current state of the main session. It should contain enough information for another agent to continue the session without depending on conversation history.

Typical information includes: session objective; scope; current repository state; relevant issue; active or approved plan; completed work; current work; verification state; blockers; delegated sub-agent work; next action; handoff information.

When resuming an existing session, this file MUST be read before performing new work. When meaningful progress is made, it SHOULD be updated. Use the corresponding template from `.agents/templates/`.

## 5.3 Sub-agent State

Path: `.agents/sessions/<session-id>/subs/<agent-name>/STATUS.md`

Each delegated agent has its own state directory. A sub-agent `STATUS.md` records: delegated objective; permitted scope; files or components owned by the sub-agent; work completed; findings; verification performed; unresolved concerns; output or handoff to the parent agent.

Sub-agents MUST NOT use their `STATUS.md` as a replacement for permanent repository records. Important findings must eventually be reflected in the appropriate `docs/records/` document.

## 5.4 `.agents/templates/`

Contains canonical Markdown templates used by agents.

All structured Markdown records created by agents SHOULD originate from the appropriate template in this directory:

```text
session-status.md
subagent-status.md
issue.md
plan.md
log.md
decision.md
patchnote.md
test-run-log.md
```

The exact files present in `.agents/templates/` are authoritative. If an appropriate template exists, agents MUST use it.

Templates themselves are not active records and MUST NOT be interpreted as current project state. When a template is used to generate a file under `docs/`, the resulting document MUST be written in Korean even if the template itself is written in English.

---

# 6. Application Components

```text
apps/
└── <component>/
    └── README.md
```

`apps/` contains the project's application components. Each component lives in its own directory and MUST contain a `README.md` defining component-specific information such as:

* responsibility;
* runtime;
* architecture;
* dependencies;
* development commands;
* configuration;
* interfaces;
* testing requirements;
* component-specific constraints.

Before modifying any component, read its `README.md`. If the README is missing or lacks information the work depends on, authoring or completing it is part of the work (see `work-planning.md`) — never silently work against an undocumented component.

When a new component is added:

1. create `apps/<component>/` with its `README.md`;
2. create the matching `tests/units/<component>/` directory (see section 10.1);
3. record the addition per `arch-decision-record.md` when it is architecturally meaningful.

Component names are project-specific. The set of directories actually present under `apps/` is authoritative.

---

# 7. Deployment and Packaging

## 7.1 `deploy/`

Contains deployment resources (container images, Dockerfiles, compose or orchestration configuration, environment configuration, infrastructure definitions — whatever the project uses).

Tasks involving deployment environments, container runtime settings, or service topology must inspect this directory.

Application behavior and deployment behavior must not be conflated. If a change affects both, inspect the corresponding application component and `deploy/`.

## 7.2 `scripts/`

Contains deployment, packaging, and operational entry-point scripts (run/launcher scripts, config generation, release packaging).

Generated artifacts must be changed through their generator scripts, never by hand-editing the output. Tasks involving stack startup, config generation, or release packaging must inspect this directory together with `deploy/`.

## 7.3 Release Packages

```text
deploy/package/<version>/
```

Contains version-specific release/package information. `<version>` represents an actual release version and is not a literal directory name.

Version directories may contain `PATCHNOTE.md`, which describes changes relevant to that package or release. When creating a patch note, use the appropriate template from `.agents/templates/`. Release tasks should also inspect relevant logs, decisions, issues, and plans before producing the final patch note.

---

# 8. Project Documentation

## 8.1 Guides

```text
docs/guides/
```

Contains reusable operational or development documentation. All guides MUST be written in Korean.

Guides explain how the system is operated or used rather than recording a single task's history: local development, deployment procedures, troubleshooting, environment setup, operational procedures, component integration instructions.

Before duplicating procedural information in another document, check whether an appropriate guide already exists.

## 8.2 Ideas (PRD / SRS)

```text
docs/ideas/
├── prd/
│   └── <version>.md
└── srs/
    └── <version>.md
```

Contains the product-level requirement documents:

* **PRD** (Product Requirements Document) — `docs/ideas/prd/`;
* **SRS** (Software Requirements Specification) — `docs/ideas/srs/`.

These documents define, from the project user's perspective, the features that must actually work.

Rules:

1. Each document is stored as `docs/ideas/{{prd or srs}}/{{UPDATED_VERSION_NAME}}.md`. The version name follows the version under development at the time the document is updated.
2. PRD and SRS documents are under `docs/`, so they MUST be written in Korean.
3. Creation or update of a PRD or SRS document MUST be handled as an **independent commit** — never mixed with code, test, or other document changes.
4. Integration tests (`tests/integrations/`) are authored against the PRD and SRS, per `.agents/workflows/create-testcase.md`. Before writing integration tests, agents MUST read the latest relevant PRD and SRS versions.

---

# 9. Persistent Work Records

`docs/records/` stores durable project history. All records under this directory MUST be written in Korean.

The four record types represent different stages or purposes and MUST NOT be used interchangeably.

```text
docs/records/
├── 0_issues/
├── 1_plans/
├── 2_logs/
└── 3_decisions/
```

## 9.1 Issues

```text
docs/records/0_issues/
```

Issues describe a problem, requirement, investigation target, feature request, or unresolved engineering concern. Creation of an issue MUST follow `.agents/workflows/issue-creation.md`.

Use an issue when the project needs to record: a defect; unexpected behavior; a performance problem; a technical limitation; an investigation target; a new feature; a new capability; a meaningful behavioral change; an unresolved engineering concern.

An issue describes **what needs attention and why**. It does not replace an implementation plan. Create issue documents using the corresponding template under `.agents/templates/`.

## 9.2 Plans

```text
docs/records/1_plans/
```

Plans describe an intended implementation or execution procedure. Creation of a plan from an existing issue MUST follow `.agents/workflows/work-planning.md`.

A plan describes: what will be done; in what order; what components are affected; what risks exist; how success will be verified. Plans should reference the issue that motivated them.

Agents MUST distinguish between `proposed`, `approved`, and `executed` plans. An existing plan is not automatically an approved plan. Execution of an approved plan MUST follow `.agents/workflows/how-to-work.md`. Use the corresponding template from `.agents/templates/`.

## 9.3 Logs

```text
docs/records/2_logs/
```

Logs contain execution evidence and observed results: test executions; benchmark results; investigation results; deployment results; command/output summaries; measurements; experiments; validation evidence; completed plan execution records.

A log describes **what actually happened**. Do not rewrite a plan after execution to make it appear as though observed results were known beforehand. Record actual results in a log. Use the corresponding template from `.agents/templates/`.

## 9.4 Decisions

```text
docs/records/3_decisions/
```

Contains durable technical and architectural decisions. Creation or modification of an architecture decision record MUST follow `.agents/workflows/arch-decision-record.md`.

Use a decision record when the project chooses between meaningful alternatives and future agents need to understand why: architecture choices; model selections with architectural impact; component boundaries; storage design; protocol selection; deployment architecture; integration patterns; rejected alternatives; important technical trade-offs.

A decision should preserve: context; alternatives considered; chosen option; rationale; consequences; conditions that would justify revisiting the decision.

Decisions describe **why the project intentionally chose a particular direction**. Use the corresponding template from `.agents/templates/`.

---

# 10. Tests

## 10.1 Unit Tests

```text
tests/units/
```

Contains tests for isolated units of application behavior, organized per component:

```text
tests/units/<component>/
├── testcodes/
└── logs/
```

`<component>` matches the component directory names under `apps/`.

Use unit tests when validating behavior that does not require the full service topology or external component integration. When modifying application logic, inspect the relevant unit tests and add or update tests when appropriate.

Creation or modification of any test case MUST follow `.agents/workflows/create-testcase.md`.

## 10.2 Integration Tests

```text
tests/integrations/
```

Contains tests validating interaction between components or services. Use integration tests for behavior involving boundaries such as: component ↔ component interfaces; storage or database interaction; external API boundaries; multi-service execution.

A component-level unit test does not replace an integration test when the behavior being changed depends on an interface between components.

Creation or modification of integration test cases is also governed by `.agents/workflows/create-testcase.md`.

Integration tests are authored against the PRD and SRS under `docs/ideas/` (section 8.2) — from the project user's perspective, based on the features that must actually work.

---

# 11. Task-to-Workflow and Reference Mapping

Use the following table before starting substantive work.

| Situation                                  | Mandatory workflow                           | Additional required references                                     |
| ------------------------------------------ | -------------------------------------------- | ------------------------------------------------------------------ |
| User reports a new problem                 | `.agents/workflows/issue-creation.md`        | relevant component docs and existing records                       |
| User requests a new feature or capability  | `.agents/workflows/issue-creation.md`        | relevant component docs and existing records                       |
| New engineering work item must be started  | `.agents/workflows/issue-creation.md`        | `.agents/templates/`, related records                              |
| Create a plan from an existing issue       | `.agents/workflows/work-planning.md`         | source issue, existing decisions, relevant component docs          |
| Execute an approved plan                   | `.agents/workflows/how-to-work.md`           | approved plan, source issue, session status, decisions, prior logs |
| Resume execution of an approved plan       | `.agents/workflows/how-to-work.md`           | session status, approved plan, prior logs                          |
| Create or update test cases                | `.agents/workflows/create-testcase.md`       | related issue/plan, component README files, existing tests         |
| Create integration tests                   | `.agents/workflows/create-testcase.md`       | PRD/SRS under `docs/ideas/`, approval gates, component docs        |
| Architectural decision context arises      | `.agents/workflows/arch-decision-record.md`  | existing decisions, relevant issue/plan/component docs             |
| Architecture changes during implementation | `how-to-work.md` + `arch-decision-record.md` | approved plan, existing ADRs                                       |
| Single-component change                    | workflow applicable to task stage            | `apps/<component>/README.md`, relevant tests                       |
| Multi-component change                     | workflow applicable to task stage            | all affected component README files, integration tests             |
| Deployment change                          | workflow applicable to task stage            | `deploy/`, affected component docs, guides                         |
| Scripts change                             | workflow applicable to task stage            | `scripts/`, `deploy/`, affected component docs                     |
| Record execution evidence                  | applicable execution workflow                | related issue/plan, log template                                   |
| Release preparation                        | applicable workflow                          | package contents, issues, plans, logs, decisions                   |
| Delegate work to sub-agent                 | current task workflow                        | session status, sub-agent status template                          |

Workflow requirements are cumulative. For example, if an architectural decision occurs while executing an approved plan, the agent MUST follow both `how-to-work.md` and `arch-decision-record.md`.

---

# 12. Default Engineering Lifecycle

The normal lifecycle for substantial engineering work is:

```text
User request / problem / feature
        ↓
issue-creation.md
        ↓
docs/records/0_issues/<issue>.md
        ↓
work-planning.md
        ↓
docs/records/1_plans/<plan>.md
        ↓
Human approval
        ↓
how-to-work.md
        ↓
Implementation
        ↓
Verification
        ↓
docs/records/2_logs/<log>.md
```

Architecture decisions may occur at any stage:

```text
                ┌─────────────────────────┐
                │ Architectural context   │
                └────────────┬────────────┘
                             ↓
                 arch-decision-record.md
                             ↓
               docs/records/3_decisions/
```

Not every minor task requires the entire lifecycle. However, agents MUST NOT bypass a mandatory workflow when its trigger condition applies.

---

# 13. Starting or Resuming a Session

When beginning work in an existing session:

1. Read `AGENTS.md`.
2. Read `.agents/sessions/<session-id>/STATUS.md`.
3. Identify the current objective and next action.
4. Determine which workflow trigger conditions currently apply.
5. Read every mandatory workflow.
6. Read all explicitly referenced issues, plans, logs, and decisions.
7. Read affected component `README.md` files.
8. Inspect current code and tests.
9. Confirm that repository state still matches the recorded session state.
10. Continue the work.

When repository state disagrees with `STATUS.md`, actual repository state takes precedence. The discrepancy MUST be recorded.

---

# 14. Delegating to Sub-agents

Before delegating work:

1. Define a bounded objective.
2. Define the files, components, or investigation scope owned by the sub-agent.
3. Provide required references.
4. Identify mandatory workflows that also apply to the delegated task.
5. Create or initialize the sub-agent `STATUS.md` from the relevant template.
6. Avoid overlapping write ownership between agents unless explicitly coordinated.
7. Match the sub-agent's model tier to the weight of the delegated task to manage token consumption: use smaller/cheaper models for mechanical or survey work (file moves, listing, cataloging, simple lookups), mid-tier models for standard analysis, and the strongest models only for work requiring deep reasoning (architecture, synthesis, adversarial verification).

A sub-agent should return: findings; files changed, if any; tests or verification performed; unresolved issues; recommended next action.

The parent agent is responsible for integrating the result into the main session and permanent project records. Sub-agents are subject to the same workflow and language policies as the parent agent.

---

# 15. Creating Records

Before creating any Markdown record:

1. Determine the correct record type.
2. Determine whether a mandatory workflow applies.
3. Read the required workflow.
4. Check `.agents/templates/` for the corresponding template.
5. Use that template.
6. Write documents under `docs/` in Korean.
7. Place the resulting document in the correct destination.
8. Link related records where applicable.

The basic relationships are:

```text
Issue
  └─ may produce → Plan
                    ├─ produces → Log
                    └─ may produce → Decision
```

A decision may occur at any stage and may also originate independently from architectural discussion. Session status references these records but does not replace them.

---

# 16. Persistent State vs Session State

Agents MUST distinguish between temporary execution state and durable project knowledge.

## Session State

Stored under `.agents/sessions/`. Examples: current step; currently delegated task; temporary blocker; next command to run; pending verification; unfinished handoff.

## Persistent Project State

Stored primarily under:

```text
docs/
apps/*/README.md
deploy/
tests/
```

Examples: known issue; approved implementation plan; completed experiment; benchmark evidence; architectural decision; operational guide; component contract.

If information will matter after the current session ends, it should normally be promoted from session state into an appropriate persistent record.

---

# 17. Completion Criteria

Before marking a task complete, verify that:

* the requested change is implemented;
* mandatory workflows were followed;
* affected tests have been executed;
* integration behavior has been tested when relevant;
* actual results are recorded when evidence is important;
* architectural decisions encountered during the work are recorded when required;
* relevant persistent documentation is updated;
* documents under `docs/` are written in Korean;
* the active session `STATUS.md` reflects the final state;
* remaining blockers or follow-up work are explicitly recorded.

"Implemented" and "verified" are different states. Do not report a task as verified unless the required verification was actually performed.

---

# 18. Documentation Precedence

When repository documentation appears to conflict, use the following precedence for the type of information each document owns:

1. `AGENTS.md` — agent operating rules, language policy, workflow routing, and repository navigation
2. `.agents/workflows/` — mandatory task execution procedures
3. `docs/records/3_decisions/` — accepted technical and architectural decisions
4. approved `docs/records/1_plans/` — approved execution design
5. component `README.md` — component-specific contracts and operation
6. `docs/guides/` — operational procedures
7. `docs/records/2_logs/` — historical observations and evidence
8. `.agents/sessions/*/STATUS.md` — current execution/session state

This precedence applies only when documents are describing the same type of constraint. Historical logs must never be rewritten merely because a newer decision supersedes them.

---

# 19. Core Principle

The repository must contain enough information for a new agent to answer:

```text
What is this project?
What am I working on?
Why are we doing it?
Which workflow applies right now?
What has already been decided?
What work has already been performed?
What am I allowed to change?
What must I read before changing it?
How do I verify the change?
What evidence must I leave behind?
What architectural decisions must be persisted?
What should the next agent do?
```

If any of these answers exist only in conversation history, important project state has not yet been persisted correctly.
