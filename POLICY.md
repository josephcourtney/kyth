# Project Documentation and History Policy

This document defines the purpose, intended contents, and usage policies for the primary project documents and for git commit messages.

Its goals are to:

- preserve clarity of intent,
- prevent scope overlap,
- minimize document drift, and
- maintain a coherent, auditable development history.

---

## 0. Core Rules

### 0.1 Single source of truth
Each class of information has one canonical home.

- architecture and invariants → `DESIGN.md`
- execution sequencing → `PLAN.md`
- current state → `STATUS.md`
- immediate work → `TODO.md`
- notable user-facing changes → `CHANGELOG.md`
- durable architectural rationale → ADRs
- fine-grained implementation history → git commits

Documents may reference one another, but they must not silently duplicate or override one another.

### 0.2 Durable vs ephemeral information
Place information according to how stable it is:

- **durable** → `DESIGN.md`, ADRs, narrow design notes
- **short-horizon** → `PLAN.md`, `STATUS.md`, `TODO.md`
- **historical implementation detail** → commits and, where appropriate, `CHANGELOG.md`

### 0.3 Authority order
When documents overlap, authority descends in this order:

1. `DESIGN.md`
2. ADRs in `docs/adr/`
3. narrow design notes in `notes/design/`
4. `PLAN.md`
5. `STATUS.md`
6. `TODO.md`
7. `CHANGELOG.md`
8. supporting documents under `docs/` and `notes/`
9. git commits as implementation history

This ordering resolves conflicts; it is not a license to duplicate content.

---

## 1. Scope Levels (Workspace vs Package)

These rules apply at both:

- the **workspace level** (repository root), and
- the **package level** (e.g. `packages/<pkg>/`), if package-local documentation exists.

### 1.1 Workspace-level documents
Workspace-level documents define system-wide intent, sequencing, and state.

Canonical workspace-level documents may include:

- `DESIGN.md`
- `PLAN.md`
- `STATUS.md`
- `TODO.md`
- `CHANGELOG.md`
- `POLICY.md`

### 1.2 Package-level documents
Package-level documents define intent and execution details for a specific package or subsystem, consistent with workspace-level design.

Canonical package-level documents may include:

- `packages/<pkg>/DESIGN.md`
- `packages/<pkg>/PLAN.md`
- `packages/<pkg>/STATUS.md` (optional)

Package-level `TODO.md` files are discouraged unless there is a clear need.

### 1.3 Conflict resolution
If workspace-level and package-level documents disagree:

- **workspace-level design invariants win**
- **package-level design governs only package-local mechanics and contracts**
- **package plans must remain consistent with workspace sequencing constraints**

### 1.4 Cross-referencing and anti-duplication
To reduce drift:

- workspace-level documents SHOULD reference package-level documents rather than restating package-local details
- package-level documents SHOULD reference workspace-level invariants rather than restating system-wide architecture
- if two documents repeat the same content, the higher-authority document is canonical and duplicated text SHOULD be removed

### 1.5 Referential integrity
Documents must not imply the existence of documentation that does not exist.

- if a document references `packages/<pkg>/DESIGN.md`, that file MUST exist
- if a referenced file is only a placeholder, it MUST say so explicitly
- if a document is intentionally deferred, higher-level documents MUST say that it is not yet present rather than implying it exists

Broken references are documentation defects.

---

## 2. `DESIGN.md`

### Purpose
`DESIGN.md` is the canonical, durable record of the project's intent and architecture. It defines **what the system is** and **what properties it must preserve**.

It is the constitutional layer of the documentation stack.

### Contents
`DESIGN.md` SHOULD contain:

- project goals and non-goals
- core architectural structure and decomposition
- package/component boundaries and responsibilities where relevant
- key abstractions and control boundaries
- invariants and correctness constraints
- external and internal requirements (functional and non-functional)
- policies (e.g. security, compatibility, privacy, data ownership, error handling)
- stable architectural decisions
- references to ADRs and narrow design notes where applicable

`DESIGN.md` SHOULD NOT contain:

- implementation plans
- task lists or sequencing details
- temporary workarounds
- progress/status tracking
- low-level implementation details that change frequently
- narrow subsystem specifications better maintained elsewhere

### Usage Policy
- update `DESIGN.md` only when intended architecture, invariants, or requirements change
- keep it deliberate and relatively stable
- describe the **current intended design**, not implementation history
- keep it compact enough to reason about as a whole

If a topic is too detailed or too volatile for `DESIGN.md` but still important, it likely belongs in a narrow design note.

---

## 3. Architecture Decision Records (ADRs)

### Purpose
ADRs capture the rationale behind significant, durable architectural decisions.

They answer: **Why was this decision made?**

### Location
ADRs live under:

- `docs/adr/`

### Contents
Each ADR SHOULD contain:

- identifier (e.g. `ADR-001`)
- title
- date
- status (`Proposed`, `Accepted`, `Superseded`, etc.)
- context / problem statement
- decision
- consequences
- alternatives considered (briefly)

### Usage Policy
- write ADRs for decisions that are durable, costly to reverse, or likely to be questioned later
- `DESIGN.md` should reference ADRs for rationale rather than duplicating long-form decision history
- superseded ADRs MUST be marked explicitly and linked forward
- ADRs SHOULD NOT contain implementation task lists or rollout sequencing

Not every decision deserves an ADR.

---

## 4. Narrow Design Notes

### Purpose
Narrow design notes capture subsystem designs that are too detailed or too changeable for `DESIGN.md`, but too important to leave implicit.

They answer: **How is this subsystem intended to work?**

### Location
Narrow design notes live under:

- `notes/design/`

### Contents
A narrow design note SHOULD contain:

- the subsystem or concern it covers
- scope and ownership boundaries
- invariants inherited from `DESIGN.md`
- data models, contracts, or state transitions as needed
- interface expectations and decision rules
- failure / abstention / degradation behavior where relevant
- references to relevant `DESIGN.md` sections, ADRs, and implementation modules

A narrow design note SHOULD NOT contain:

- project-wide constitutional architecture
- long-form architectural rationale better captured in ADRs
- short-horizon execution tasks
- rollout sequencing or ownership planning

### Usage Policy
- narrow design notes are the preferred home for concrete subsystem guidance
- they may evolve more freely than `DESIGN.md`, but should still be deliberate and pruned
- if a narrow design note introduces a durable, architectural, costly-to-reverse decision, that decision SHOULD also be captured in an ADR

---

## 5. `PLAN.md`

### Purpose
`PLAN.md` defines how the design in `DESIGN.md` will be realized.

It records **execution strategy, sequencing, migration logic, and non-obvious implementation considerations**.

### Contents
`PLAN.md` SHOULD contain:

- high-level implementation phases or milestones
- ordering constraints and dependencies
- migration strategies and transitional states
- cross-component or cross-package sequencing where relevant
- non-obvious implementation considerations
- temporary or contingent execution decisions
- references to relevant `DESIGN.md` sections, ADRs, and package plans where applicable

`PLAN.md` SHOULD NOT contain:

- detailed per-function or per-file task breakdowns
- routine progress/status reporting
- long-term architectural rationale
- exhaustive low-level checklists

### Usage Policy
- `PLAN.md` may evolve as implementation proceeds
- completed or obsolete sections may be pruned or explicitly marked
- `PLAN.md` explains **how and in what order** work should proceed, not whether it has already happened

If a plan item becomes a small, immediate task, it probably belongs in `TODO.md`.

---

## 6. `STATUS.md`

### Purpose
`STATUS.md` captures the current state of the project for continuity and handoff.

It answers:

> Where are we now, and what matters next?

### Contents
`STATUS.md` SHOULD contain:

- current focus or active work area
- summary of recently completed plan elements
- known gaps, limitations, or incomplete areas
- identified problems, risks, or blockers
- notes helpful for resuming work
- references to relevant `PLAN.md`, ADRs, or narrow design notes where useful

`STATUS.md` SHOULD NOT contain:

- detailed task lists
- long-term plans
- architectural restatements
- historical narrative that is no longer useful

### Usage Policy
- `STATUS.md` is short-horizon and pragmatic
- update it as work progresses and prune it aggressively
- obsolete information SHOULD be removed rather than accumulated
- it is not an archive
- keep it compact and high-signal

---

## 7. `TODO.md`

### Purpose
`TODO.md` is an ephemeral, execution-level task list used to drive immediate development work.

### Contents
`TODO.md` SHOULD contain:

- highly concrete tasks
- short-horizon work items
- explicit references to files, classes, methods, tests, tools, or commands where useful
- acceptance criteria or required verification steps where useful

`TODO.md` SHOULD NOT contain:

- completed tasks
- long-term plans
- speculative ideas
- architectural rationale
- historical records

### Usage Policy
- `TODO.md` is temporary by design
- it may be rewritten freely as understanding evolves
- completed items SHOULD be removed before committing unless there is a strong reason not to
- the absence of an item from `TODO.md` does not imply it was never done

`TODO.md` is for immediate execution, not record-keeping.

---

## 8. `CHANGELOG.md`

### Purpose
`CHANGELOG.md` records notable changes for users, downstream consumers, and operators.

### Contents
`CHANGELOG.md` SHOULD contain:

- user-visible additions, changes, fixes, deprecations, and removals
- notable internal changes that affect behavior, performance, compatibility, or operations
- breaking changes
- migration notes where applicable

`CHANGELOG.md` SHOULD NOT contain:

- task-level detail
- implementation minutiae
- abandoned work
- development process notes
- exhaustive internal history

### Usage Policy
- add entries as meaningful work is completed
- the changelog is curated and narrative, not exhaustive
- `CHANGELOG.md` is not a substitute for commit history

---

## 9. Git Commit Messages

### Purpose
Commit messages, together with diffs, form the authoritative fine-grained technical history of the project.

### Contents
Each commit message SHOULD include:

- a concise, imperative subject line describing the change
- a body (when non-trivial) explaining:
  - rationale and intent
  - notable tradeoffs or constraints
  - behavioral changes or edge cases
  - tests added or modified
  - references to relevant documents and ADR IDs where applicable

### Usage Policy
- commits should be logically scoped and self-contained
- commit messages are the primary location for detailed implementation history
- commits document **what changed and why**, not project status or task tracking
- stable identifiers SHOULD be used where useful for traceability, including:
  - ADR IDs (e.g. `ADR-001`)
  - `DESIGN.md` section names or anchors
  - `PLAN.md` milestone identifiers

---

## 10. Summary of Responsibilities

### Canonical artifacts

- `DESIGN.md` → system intent, architecture, boundaries, invariants
- `docs/adr/` → durable architectural rationale
- `notes/design/` → subsystem design detail
- `PLAN.md` → execution strategy and sequencing
- `STATUS.md` → current state and continuity
- `TODO.md` → immediate execution detail
- `CHANGELOG.md` → curated notable changes
- git commits → detailed technical history

### Package-level artifacts (when used)

- `packages/<pkg>/DESIGN.md` → package-local intent, boundaries, contracts, invariants
- `packages/<pkg>/PLAN.md` → package-local execution strategy consistent with workspace sequencing
- `packages/<pkg>/STATUS.md` → optional package-local continuity notes

Each artifact has a distinct role. Prefer explicit references over overlap.

---

## 11. Documentation Structure

The preferred documentation hierarchy is:

- `DESIGN.md` for constitutional architecture and invariants
- `docs/adr/` for durable architectural decisions and rationale
- `notes/design/` for narrow subsystem design notes
- `PLAN.md` for execution strategy and rollout ordering
- `STATUS.md` for current state and handoff continuity
- `TODO.md` for immediate task execution
- `CHANGELOG.md` for curated change history
- `docs/` for explanatory or operator-facing material
- `notes/` for useful but non-canonical working notes
- `notes/archive/` for retained historical material

### Intended flow

1. `DESIGN.md` states what the system must be.
2. ADRs explain why durable architectural choices were made.
3. narrow design notes explain how individual subsystems are intended to satisfy that design.
4. `PLAN.md` records in what order and under what migration strategy implementation should proceed.
5. `STATUS.md` and `TODO.md` support execution continuity.
6. commits preserve the detailed implementation record.

No lower-level document may silently override a higher-level one.

---

## 12. Supporting and Archived Documents

Supporting documents under `docs/`, `notes/`, examples, and similar locations may elaborate on workflows, examples, operations, or implementation guidance.

These documents are subordinate to the canonical artifacts above.

### Rules
- supporting documents SHOULD explain or operationalize canonical artifacts, not redefine them
- archived material under `notes/archive/` is explicitly **non-authoritative**
- archived material may preserve historical context, superseded examples, or prior analysis, but MUST NOT be treated as current architecture or policy

When there is conflict:

- `DESIGN.md` governs architecture and invariants
- ADRs govern durable decision rationale
- narrow design notes govern subsystem detail, so long as they do not conflict with higher-level design
- `PLAN.md` governs execution sequencing
- `STATUS.md` governs current state and continuity
- `TODO.md` governs immediate execution detail
- `CHANGELOG.md` governs curated notable changes

---

## 13. Maintenance Rules

### 13.1 Keep documents pruned
Documentation should be actively maintained, not merely accumulated.

- obsolete status notes should be removed
- stale TODO items should be rewritten or deleted
- superseded design rationale should be marked and linked forward
- duplicated content should be collapsed into references

### 13.2 Prefer references over repetition
If information already has a canonical home, reference it rather than restating it.

### 13.3 Avoid silent drift
If implementation no longer matches a canonical document, either:

- update the implementation, or
- update the document

but do not leave the mismatch unacknowledged.

---

## 14. Placement Heuristic

When deciding where something belongs, ask:

- **Is this what the system is supposed to be?** → `DESIGN.md`
- **Why did we choose this?** → ADR
- **How should this subsystem work?** → `notes/design/`
- **How should we execute this?** → `PLAN.md`
- **What is true right now?** → `STATUS.md`
- **What do we do next?** → `TODO.md`
- **What changed for users/operators?** → `CHANGELOG.md`
- **What changed in implementation detail, and why?** → git commit

If the answer is “more than one,” the information is probably too broad and should be split.
