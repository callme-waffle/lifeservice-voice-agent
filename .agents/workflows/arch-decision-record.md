# Workflow: Architecture Decision Record (ADR)

This workflow governs recording durable technical and architectural decisions under `docs/records/3_decisions/`.

Read this file completely whenever architectural decision context appears — regardless of what the conversation was originally about.

---

## 1. Trigger

Follow this workflow when a durable decision is made, or an existing decision is materially changed, concerning:

* system architecture, service boundaries, component responsibilities;
* data flow, storage architecture, database technology;
* model selection that materially affects system architecture;
* deployment architecture, runtime topology, infrastructure structure;
* communication protocols, integration patterns;
* significant dependency choices;
* durable technical trade-offs;
* replacement of one architectural approach with another;
* explicit rejection of a meaningful architectural alternative.

The trigger applies even when the decision emerges incidentally — while investigating an issue, planning, implementing, reviewing, debugging, or answering a question. Architectural context MUST NOT disappear into conversation history.

Not every technical choice is an ADR. Record a decision when future agents would otherwise be unable to understand WHY the project went a particular direction, or might accidentally reverse it.

---

## 2. Preconditions

1. Search `docs/records/3_decisions/` for existing ADRs touching the same area.
2. If an existing accepted ADR conflicts with the new direction, this is a SUPERSEDE case (section 5), not a silent overwrite.
3. Read the related issue, plan, and component `README.md` files as applicable.

---

## 3. ID and File Naming

```text
docs/records/3_decisions/ADR-<NNN>-<slug>.md
```

* `<NNN>` — zero-padded 3-digit global sequence, independent from issue numbering. Allocate by scanning existing ADR files and taking `max + 1` (or `001`).
* `<slug>` — short, lowercase, hyphen-separated English summary of the subject (e.g., `ADR-001-database-selection.md`).

ADRs are numbered independently because they may originate from conversation without any issue.

---

## 4. ADR Status Lifecycle

| Status | Meaning | Who may set it |
| --- | --- | --- |
| `proposed` | Drafted; decision not yet confirmed by the human | agent (at creation) |
| `accepted` | Human explicitly confirmed the decision in conversation | agent, ONLY after explicit human confirmation |
| `superseded` | Replaced by a newer accepted ADR | agent, when the replacement is accepted |

An agent MUST NOT set `accepted` on its own judgment. If the human already made the decision explicitly in conversation before the ADR was written, the ADR may be created directly as `accepted`, citing that confirmation.

---

## 5. Superseding an Existing ADR

When a new decision replaces an existing one:

1. Create the new ADR normally; its metadata links the old ADR (`대체 대상`).
2. In the OLD ADR: change status to `superseded` and add a link to the new ADR (`대체 문서`).
3. NEVER delete the old ADR or rewrite its content. Historical decisions and their rationale must remain readable.

---

## 6. Creation Steps

1. Copy `.agents/templates/decision.md` as the document skeleton.
2. Write the document in Korean. Identifiers, protocol names, product names, code, and configuration may remain unchanged.
3. The ADR MUST preserve:
   * context — the situation and forces that required a decision;
   * alternatives considered — each with its essential pros/cons;
   * the chosen option;
   * rationale — why this option over the alternatives;
   * consequences — what becomes easier, harder, or constrained;
   * revisit conditions — concrete circumstances that would justify re-opening the decision.
4. Link related records: the issue and/or plan the decision arose from, and any superseded ADR.
5. Report the ADR to the user in Korean; obtain explicit confirmation before marking it `accepted`.

---

## 7. Postconditions

* The ADR exists with correct ID, status, and cross-links.
* Superseded ADRs are marked and cross-linked, not deleted.
* Related plan/issue documents link to the ADR.
* The active session `STATUS.md` (if any) references the decision.
