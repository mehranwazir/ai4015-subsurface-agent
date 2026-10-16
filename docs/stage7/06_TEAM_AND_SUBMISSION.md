# Team responsibilities and submission checks

The group head requested a technical data/model role. These are **proposed responsibilities**, not claims of completed individual work or authorship. Exact roll numbers and the final filename are recorded in the local handoff outside this public repository.

## Clear technical ownership

| Member | Main responsibility | Concrete work to perform and explain |
|---|---|---|
| **Mehran Hamayoon — head** | **Data and numerical model** | Reproduce download/prepare/baseline; verify missing-value/cohort/split rules; explain train-only imputation and RF; inspect per-well results; prepare numerical tables/plots and an honest failure analysis. Coordinate final submission. |
| **Abdul Basit** | **Agent and deterministic tool integration** | Review provider/loop/contracts; trace a native call end to end; check alias/unit handling, state and budgets; make/document a genuine interface or robustness improvement. |
| **Talha Araiz** | **Evaluation and reliability experiments** | Review independent case scoring and tests; reproduce replay; add independently specified cases/fault checks; define ablation configuration and report failures/denominators. |

Mehran's scope uses the existing working classical model; it does not require LLM fine-tuning or building the orchestration framework. It still produces a substantive technical contribution. All members remain responsible for understanding the complete system.

## Literature split: ten core papers

| Reader | Papers | Link to technical role |
|---|---|---|
| Mehran — 3 | **P01, P05, P08** | Base data/model workflow, subsurface tools and geological data consistency. |
| Abdul — 3 | **P02, P03, P04** | Well-log agents, orchestration decisions and schema/QC architecture. |
| Talha — 4 | **P06, P07, P09, P13** | Review, retrieval/feedback and ablation evaluation. |

Reading counts are not a formula for equal effort. Help one another when a paper is inaccessible or needs domain expertise. Cross-review a partner's facts before combining the submission. P10–P12 are alternatives if the group decides a core paper is unsuitable after reading.

## First useful tasks and genuine commits

- **Mehran:** run the numerical workflow, reconcile the cohort/split counts, and write an original data/model analysis explaining the weaker well 7 SW result. A real contribution may be a reviewed data audit, improved diagnostic or numerical result interpretation; running a command alone need not be presented as authorship of the source code.
- **Abdul:** reproduce the real tool trace and examine a missing/ambiguous-unit path. Make a reviewed improvement or document the exact control behavior based on code and execution.
- **Talha:** reproduce the offline tests/replay, define new cases with independent expected outcomes, and commit meaningful coverage or evaluation documentation.
- Commit actual work from each member's own configured identity/account. Do not change author names on existing assistant-created work, create empty credit commits, or fabricate older contribution history.

## Understanding checks for the viva

Each person should explain: the selected base and Q1 category; the seven inputs/three outputs; why holding out wells matters; why filtering labels affects the evaluation population; how the LLM chooses actions while Python calculates; what the verifier proves; why our RMSE is not a LogACF comparison; what six smoke passes do/don't establish; and how each gap will be measured independently.

## Remaining submission work

- [ ] All ten selected papers fully read sufficiently for critical analysis; unresolved tables/units/relevance resolved.
- [ ] Student-written critical summaries, complete synthesized comparison table and three-gap table.
- [ ] Base reference and ranking proof saved with exact source/category/year.
- [ ] Student-written proposal covers every Section 5 item, with clear implemented/planned distinction.
- [ ] Diagrams show roles, tools, data, state, flow, all three gap locations and baseline difference.
- [ ] Numerical evidence copied accurately from saved files and discussed in original words.
- [ ] Each member's real contribution/reproduction recorded, with meaningful member history.
- [ ] Supervisor can read repository; invite partners if they need push access.
- [ ] One PDF contains A first, B second, first-page group details, 11–12 pt consistent layout and IEEE references.
- [ ] Correct final filename, all citations/links/figures checked, no placeholders remain.
- [ ] Group head adds PDF and repository link to the same Classroom submission, then verifies final submission state before the supplied deadline.

No final assessed PDF or Classroom upload is produced by this evidence pack. The head should send the group's own drafts for factual/rubric review and provide any additional Classroom instructions.
