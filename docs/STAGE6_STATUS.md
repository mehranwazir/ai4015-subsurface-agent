# Stage 6: implemented baseline and submission readiness

**Recorded:** 16 October 2026. **Project:** AI4015, G3-03. **Scope approved by the user:** a small well-log system inspired by LogACF, with local Git history and real Gemini integration. This is factual engineering documentation, not assessed proposal prose.

The selected workflow now runs. The technical evidence needed to support the group's Phase 1 writing is available. Deliverables A and B have not been written for submission, and nothing has been published to GitHub or submitted to Classroom.

**Subsequent Stage 7 update:** The group head approved the [evidence pack and writing outline](stage7/README.md), provided team details and a GitHub destination, and requested publication. This file records the earlier Stage 6 execution state; use the Stage 7 handoff for later preparation/publication status.

## 1. What exists

| Component | Implemented behavior | Evidence |
|---|---|---|
| Public-data pipeline | Pinned SPWLA organizer archive, checksum checks, exact CSV members, missing-value handling, stable identity, whole-well splits | `src/subsurface_agent/data.py`, `results/data_manifest.json` |
| Deterministic numerical baseline | Train-only imputation, frozen Random Forest and training-mean comparator, keyed scoring and saved plots | `src/subsurface_agent/baseline.py`, `results/baseline_metrics.json` |
| Real model integration | Gemini REST native function calls; configured model `gemini-3.5-flash-lite` | `src/subsurface_agent/providers.py`, `results/evidence/gemini-e2e-002/` |
| Scientific tool interfaces | Inspect schema/interval, convert feet/meters, predict, verify, plot; structured finish states | `contracts.py`, `tools.py` |
| Execution state | Dataset/model versions, slice/prediction IDs, verification state, bounded turns/calls/errors, JSONL trace | `agent.py`, saved `result.json` and `events.jsonl` |
| Initial evaluation | 16 specified developer cases; six actually executed against Gemini | `evaluation/cases.json`, `results/agent_evaluation.json` |
| Software verification | 19 executed offline tests, including corruption, recovery, identity-safe scoring, per-run accounting, replay | `tests/`, `results/tests.xml` |
| Reproduction instructions | Dependencies, Windows commands, data provenance, API setup and limitations | `README.md`, `requirements-lock.txt`, `EXPERIMENT_PROTOCOL.md` |
| Architecture | Implemented flow and locations of planned G1/G2/G3 mechanisms | `ARCHITECTURE.md` |
| Version control | Meaningful local commits | Local `.git`; no remote configured |

There is one planner and six allowlisted tools. No LangGraph service, vector database, multi-agent fleet, GPU training, or frontend was needed for this baseline. The custom bounded loop exposes the small amount of state and control required here.

## 2. Data observations and corrections established by execution

Source: [SPWLA PDDA 2021 organizer repository](https://github.com/pddasig/Machine-Learning-Competition-2021), commit `0ffc94f702feab81f6eb1f4d453e19754a557305`. The archive checksum is in `results/data_manifest.json`.

| Quantity | Observed value |
|---|---:|
| Original training rows | 318,967 |
| Original training well IDs | 9: 0 through 8 |
| Original competition test rows | 11,275 |
| Original competition test well IDs | 100, 101, 103, 104 |
| Rows with all three finite target labels | 42,309 |
| Complete-label rows outside the declared [0,1] target range | 90 |
| Eligible supervised rows | 42,219 |
| Train rows: wells 0,2,4,6,8 | 33,692 |
| Validation rows: wells 1,5 | 4,405 |
| Test rows: wells 3,7 | 4,122 |

We exclude the 90 invalid-label rows rather than clipping their labels. The complete cohort also requires at least four of seven usable input curves. Missing-label rows remain inspectable in the feature-only table; they are outside supervised training/scoring. Target-label filtering conditions the evaluation population and must be disclosed.

Inputs are GR, CALI, DEN, NEU, RDEP, RMED, DTC. Outputs are PHIF, SW, VSH in fraction units. Depth is feet according to the pinned organizer tutorial. The tutorial's DTC unit wording appears inconsistent; no DTC conversion is performed. No identity, depth, or target label is a predictor input.

The organizer's reference test-label CSV has only target columns and lacks identity keys. We therefore use a custom held-out split of the labeled training wells. **We have not obtained an official competition test score.** An exact-feature-vector check found zero duplicate vectors across our train/test cohorts (`results/overlap_check.json`); this does not establish cross-field or spatial independence.

## 3. Actual numerical results

Protocol: 80 trees, max depth 10, minimum leaf size 3, random seed 42, one CPU worker. Median imputation and missingness indicators are fitted only on training wells. Hyperparameters were fixed before scoring; no search or test-based selection was performed. The initial fitting time was about 9.67 seconds on this CPU environment.

**Pooled test results: 4,122 rows across wells 3 and 7.**

| Target | Mean predictor RMSE | Random Forest RMSE | Random Forest MAE | Random Forest R² |
|---|---:|---:|---:|---:|
| PHIF | 0.071320 | 0.021597 | 0.013402 | 0.876463 |
| SW | 0.357893 | 0.070118 | 0.031695 | 0.902511 |
| VSH | 0.231938 | 0.063989 | 0.050770 | 0.914726 |
| Arithmetic mean of property RMSEs | **0.220384** | **0.051901** | — | — |

This mean is the average of three separately computed RMSEs. It is not a single pooled root mean squared error across all target cells. Giving each well equal weight produces Random Forest mean RMSE **0.049894**. The full JSON records each aggregation explicitly.

The weaker result must remain visible: **well 7 SW R² = 0.259237**, with SW RMSE **0.092671**. Pooled scores hide this difference. Only two held-out well IDs from one field are evaluated; no confidence interval or independent-field claim is justified.

The agent uses exactly this frozen prediction model. No agent-driven prediction accuracy improvement has been demonstrated. LogACF used another protocol; our numbers must not be described as beating its reported score.

Figures: [well 3](../results/figures/test_well_3.png), [well 7](../results/figures/test_well_7.png). Keyed prediction CSVs and full metrics are in `results/`.

## 4. Actual agent execution

The complete real query was: predict PHIF/SW/VSH for well 3 from 10,600 to 11,000 ft, verify the artifact, and make a plot.

Observed sequence: `inspect_dataset → inspect_interval → predict_properties → verify_predictions → plot_logs → finish`.

- 1,220 prediction rows; input coverage 1.0 for that interval.
- Six tool calls, zero tool errors, six provider requests.
- 78.512 seconds recorded agent-loop latency; data/model initialization precedes this timer.
- 11,237 reported prompt tokens and 236 reported output tokens.
- Prediction CSV, plot, structured result and event trace retained in `results/evidence/gemini-e2e-002/`.
- All six structured tool outputs matched on replay; `results/evidence/replay.json` records `llm_called: false`.

The verifier checks schema, sample/well/depth identity, finite values, declared bounds, and frozen-model recomputation. Maximum CSV/recomputation difference was approximately 1.11e-16. It does not use target labels and does not establish geological correctness or calibrated uncertainty.

### Six real developer smoke cases

| Case | Observed disposition | Calls | Latency (s) | Deterministic case checks |
|---|---|---:|---:|---|
| Predict with feet | answer | 5 | 52.578 | Passed |
| Equivalent interval in meters | answer | 5 | 67.444 | Passed |
| Unknown well 999 | abstain | 2 | 62.968 | Passed |
| Unsupported permeability target | clarify | 2 | 14.535 | Passed |
| Deliberately missing prediction artifact | answer after regeneration | 7 | 73.850 | Passed |
| Gamma-ray/RHOB aliases, inspection only | answer | 3 | 71.756 | Passed |

Result: **6/6 selected cases passed once each**; mean latency 57.188 seconds and median 65.206 seconds. The six runs reported 39,722 prompt tokens and 893 output tokens in total. API retries may consume resources not represented in successful-response token metadata. No invoice was queried; cost is unknown, not zero.

These are manually authored development prompts, some with behavioral hints. Ten other defined cases remain unexecuted against Gemini. Six passes are not a statistically validated reliability rate, an independent held-out benchmark, or evidence that all three research contributions work. The repair case injects a missing CSV deliberately; it is not a naturally occurring field failure.

### Failures and accounting retained honestly

- An initial real request using `gemini-2.5-flash-lite` returned HTTP 404 for this account. Its failed trace is preserved. An availability diagnostic for another model encountered high demand. The working model was selected after inspecting current service availability.
- Review found that the batch's original `provider_requests` values were cumulative over the reused provider. Raw records are unchanged. `results/evidence/request_accounting.json` derives the correct per-run deltas: **5, 7, 3, 2, 7, 3**, including retries. Source code now reports each run's own request count, with a regression test. Tool-call counts and pass/fail results were unaffected.
- A test rerun could not create fixtures in the sandbox's default Windows temporary directory: 9 tests ran successfully and 10 had setup errors. That XML is preserved in `results/evidence/tests_sandbox_temp_failure.xml`. Rerunning all tests with a fresh workspace temporary folder yielded **19 passed** in 0.99 seconds; the final XML is `results/tests.xml`.

Replay validates recorded actions under the pinned data/model, not a new stochastic plan. A different training environment may produce a different model checksum; strict replay rejects mismatched versions.

## 5. Implemented mechanisms versus semester research

| Theme from the audit | Present now | Still to evaluate |
|---|---|---|
| G1: schema and unit grounding | Real schema/alias registry, feet/meters, typed arguments, explicit identity | Controlled schema perturbations; comparison with ungrounded variants; unseen paraphrases |
| G2: execution checking and recovery | Identity/range/recomputation checks and missing-artifact regeneration | More fault types, adaptive repair comparisons, no-verifier/no-repair ablations |
| G3: evidence-based acceptance | Explicit answer/clarify/abstain, minimum input-coverage rules | Selective-risk/coverage evaluation, calibrated uncertainty, adversarial acceptance cases |

There is no measured novelty claim, full LogACF reproduction, NMR model, production forecast, economics workflow, role/memory ablation, calibrated confidence score, or complete semester experiment here. These limits do not prevent demonstrating an initial working Phase 1 foundation.

## 6. What is ready for A, B, and Classroom

The complete requirement extraction, rubric and literature corrections remain in the parent file [AI4015_Phase1_Corrected_Audit_and_Action_Guide.md](../../AI4015_Phase1_Corrected_Audit_and_Action_Guide.md). That file is research guidance; the original stage files remain historical and should not override its corrections.

| Assessment part | Marks | Current readiness | Remaining work |
|---|---:|---|---|
| A: literature review and gaps | 45 | Audited references, source links, base-paper decision and evidence-backed gap planning available | Group reads the selected full texts, resolves flagged access/ranking details, writes 150–250-word critical summaries for at least ten eligible papers, cross-paper table and three-gap synthesis |
| B: project proposal | 30 | Confirmed data, actual baseline, implementable architecture, initial evidence available | Group writes its problem/agentic justification, coherent proposed architecture, per-gap questions/hypotheses/metrics/ablations, realistic semester milestones, named work division and publication direction |
| C1: working baseline | 12 | Local data/model/tool/LLM workflow runs with actual saved results | Group reproduces and understands it; supervisor judges whether demonstration satisfies the rubric |
| C2: GitHub repository | 8 | Clean local repository, README, dependencies, meaningful local commits | Publish repository, give supervisor access, obtain each member's real contributions/commits; do not invent history |
| D: writing and submission | 5 | Requirements checklist available | Original writing, IEEE references, correct PDF format/name/order, head/member details, final checks and Classroom submission |

**I am ready now to provide Stage 7 evidence-organization and draft-review support if you approve it.** Stage 6 no longer blocks that work. The assignment's prohibition on AI-generated submission writing means I will support your group's own A/B drafts, not write a ready-to-submit literature review or proposal. A completion time for the final PDF depends on your writing and the outstanding group/repository details; no submission-ready PDF exists yet.

### Final submission mechanics

1. Create **one PDF with A first, then B**. Do not submit this technical status file or the audit as the assessed writing.
2. First page: G3-03, chosen project title, all member names and roll numbers.
3. Use 11–12 pt consistent formatting and IEEE references. Include base-paper ranking proof, comparison table, gap table and architecture diagram as required.
4. Filename: **`Phase1_G3-03_<GroupHeadRollNo>.pdf`**.
5. The group head adds that PDF and an **accessible GitHub repository link** to the same Phase 1 Google Classroom submission.
6. Deadline supplied by the user: **17 October 2026, 11:59 pm Pakistan time**. Check Classroom for any additional instructions; no Classroom page has been inspected here.
7. Confirm the upload/link and final submission state. Nothing has been submitted in this session.

Before final preparation, supply the group head and all names/roll numbers, genuine work allocation, any additional Classroom instructions, and the group's drafts. GitHub publishing can follow when you authorize it; currently the repository is local as requested.

## 7. Local usage and credentials

Run commands from `D:\Agentic AI\Project\subsurface-agent`; follow the README for download, prepare, baseline, agent, evaluation and replay. An editable package and virtual environment are already available on this computer. Existing dependency packages were reused; a fresh isolated install and the configured remote CI have not been executed.

The Gemini credential is stored only in ignored `.env` for this local integration, and is excluded from source and recorded traces. Because it was posted in chat, rotate it in the provider console and replace the local value. Do not add the key or `.env` to GitHub.
