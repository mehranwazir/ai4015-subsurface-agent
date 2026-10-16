# Assignment requirements and rubric map

Source: the supplied five-page AI4015 Phase 1 assignment, Sections 1–8, plus the separately supplied Section 9 rubric image. The original local files and their hashes are preserved in the parent project's audit folder. This is a requirement checklist, not a prediction of marks.

## Mandatory paper eligibility

- [ ] At least ten **2025 or 2026** papers, each directly relevant to the chosen project direction.
- [ ] Research articles in peer-reviewed journals/conferences, with identifiable methods and enough data/evaluation detail for critical analysis.
- [ ] Do not count editorials, opinions, chapters, news, blogs or ordinary webpages.
- [ ] Older foundational papers are additional references. Preprints count only with supervisor approval.
- [ ] Select one base from the reviewed set, published in a **Q1 Scopus/JCR journal or CORE A*/A conference**, and retain ranking proof.
- [ ] Explain the base's selection, problem/method/data/results, author-stated and student-identified limits, and the proposed comparison/extension.

The Q1/A*/A condition applies to the base paper, not automatically to all ten papers. Public availability and a DOI do not establish peer review. A public repository does not establish reproducibility without inspecting dependencies/data/licenses and attempting the relevant work.

## Deliverable A: literature review and gaps

- [ ] Write approximately **150–250 words per paper in the group's own words**, covering problem, method, data/environment, quantitative results/metrics, limitations and project relevance.
- [ ] Distinguish the authors' limitations from the group's critique. Consider data, methodology, evaluation, generalization, missing baselines and future work.
- [ ] One synthesized comparison table includes **every reviewed paper** and marks the base.
- [ ] Required comparison columns: number; title; year/venue; dataset/benchmark; method/agent architecture; evaluation metrics; key results; limitations/research gap.
- [ ] Identify at least three strong gaps and select the three strongest. Each must be specific, supported by named-paper evidence, relevant to the project/base, and measurable within the semester.
- [ ] Required gap-table columns: gap; supporting evidence/papers; proposed approach; measurement.
- [ ] Do not copy sentences/abstracts or submit AI-generated prose. Numerical facts still require citations and context.

## Deliverable B: proposal coverage

Complete every item in [the writing outline](04_PROPOSAL_WRITING_OUTLINE.md): title/seed, problem/motivation, base/three gaps, target product, agentic justification, development and research goals/success criteria, confirmed source/environment, architecture, diagram, baseline, a question/hypothesis per gap, evaluation/ablations/system measures, milestones/risks/fallback, individual work division and potential publication direction.

A deferred dataset selection normally causes revision. Our dataset is now actually downloaded and processed. Planned research mechanisms must be distinguished from current implementation and observed results.

## Deliverable C: repository foundation

- [x] Documented current architecture and proposed extension locations.
- [x] Working data pipeline, baseline and initial numerical results.
- [x] Real model/provider integration and initial scientific tool interfaces.
- [x] Defined state/context and structured contracts.
- [x] Initial evaluation cases and executed software tests.
- [x] At least one complete real end-to-end workflow.
- [x] Clean project structure, dependencies and run instructions.
- [ ] Confirm published repository is readable by the supervisor; public access or explicit private access is sufficient.
- [ ] Meaningful contributions/commits from **all members**, with genuine authorship. The initial history does not by itself demonstrate that all three contributed.
- [ ] Each member can reproduce/explain the complete system, not only their own component.

## Exact marks and evidence needed

| Criterion | Marks | What excellent work must demonstrate | Available support / remaining work |
|---|---:|---|---|
| A1 Paper selection | 8 | At least ten directly relevant recent papers from reputable peer-reviewed venues | Candidate records available; students must read and justify the final choices. |
| A2 Base paper | 7 | Eligible ranking proof, clear selection, thorough method/results/limits | Base/ranking notes available; save source proof and write the critique. |
| A3 Critical summaries | 12 | Original critical analysis covering all six elements for every paper | Evidence notes are not summaries; student writing remains. |
| A4 Comparison table | 8 | Complete, accurate synthesis, clear differences, marked base | Factual notes and bibliography available; group synthesizes its table. |
| A5 Research gaps | 10 | Three specific, supported, relevant, testable gaps with measurement | Experiment candidates available; group evaluates evidence and writes synthesis. |
| B1 Problem/motivation/agentic justification | 6 | Clear users/problem and a convincing need for adaptive tool behavior | Explain concrete cases and compare against the fixed pipeline. |
| B2 Architecture/diagram | 8 | Agents, tools, data, state, flow; gaps and baseline marked | Diagrams supplied as engineering references; group validates its final design. |
| B3 Data/baseline/evaluation | 10 | Confirmed source, defined baseline, per-gap question/hypothesis, concrete metrics/ablations | Actual source/results ready; final comparative experiments are planned. |
| B4 Feasibility/milestones/work division | 6 | Realistic plan, risks/fallback, clear roles, credible publication direction | Proposed team tasks supplied; confirm course timetable and responsibilities. |
| C1 Working baseline | 12 | End-to-end run, working data/model/tools, initial results | Real saved evidence available; demonstrate/reproduce it. |
| C2 GitHub repository | 8 | Clean accessible repository, README and meaningful member history | Initial local history exists; check publication/access and add real member work. |
| D1 Writing/submission | 5 | Clear original writing, consistent format, correct IEEE references and all submission rules | Final student PDF and Classroom checks remain. |
| **Total** | **100** | **A 45 + B 30 + C 20 + D 5** | Marks within bands remain the supervisor's judgment. |

The supplied rubric's excellent/adequate/weak bands are **90–100% / 50–80% / 0–40%**. It does not define intermediate bands or a formula for scoring a checklist. Do not convert the table into an estimated grade.

## Submission mechanics

- [ ] Group head submits once through the Phase 1 Google Classroom assignment.
- [ ] One PDF: **A first, then B**.
- [ ] Add the GitHub repository URL as a link in the **same submission**.
- [ ] Filename: `Phase1_G3-03_<GroupHeadRollNo>.pdf`.
- [ ] First page: project code, project title, all member names and roll numbers.
- [ ] Clear consistent layout, **11–12 pt font**, IEEE references.
- [ ] Check the exact Classroom deadline and any extra instructions; the supplied deadline is 17 October 2026, 23:59 PKT.

The supplied assignment does not specify a total page limit, mandatory two-column format, separate ZIP, slides/video, a required framework, API spending, or GPU training. Do not add these as course requirements.
