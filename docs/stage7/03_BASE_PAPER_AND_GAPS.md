# Base paper, evidence and proposed gap experiments

This is research planning material. It distinguishes paper observations, engineering decisions and hypotheses; it is not assessed proposal prose.

## Base-paper record and ranking proof

**P01:** Gang Luo and Li-Zhi Xiao, *Large language model-based AI agent for well logging data processing and interpretation*, Petroleum Science, 2026, [DOI](https://doi.org/10.1016/j.petsci.2026.05.031).

| Requirement | Evidence / qualification |
|---|---|
| Recent research article | Publisher identifies an original paper, available online 25 May 2026, and states peer-review responsibility. |
| Eligible journal ranking | [KeAi notice, 23 June 2026](https://www.keaipublishing.com/en/journals/petroleum-science/news/petroleum-science-latest-impact-factor-64/): Engineering, Petroleum, **2/22, Q1**. |
| Category/year precision | The same notice reports Energy & Fuels **66/191, Q2** and attributes the information to JCR/Clarivate 2025. Do not call every category Q1 or invent a different ranking year. |
| Evidence type | Primary publisher reproduction of JCR information; authenticated JCR was not accessed. Save the notice or obtain a university JCR export if required by the supervisor. |
| Usable comparison point | Well-log workflow and public SPWLA route match this project. Author-associated source is available for method inspection. |
| Reproduction practicality | A small adaptation runs on CPU. Full author architecture/model-search/multimodal reproduction is not established. |

For ranking proof, retain the source title, publisher, publication/access dates, category, rank, quartile and exact source attribution. A print/save of that page should show its URL and ranking table. No local publisher screenshot or authenticated database export is falsely claimed to exist.

### Explain the adaptation precisely

| Aspect | Paper/author implementation | Current project |
|---|---|---|
| Task connection | Integrated well-log processing and interpretation | Conventional-log property prediction/inspection |
| Agent design | Collaborative roles, memory, planning, execution | One bounded native-tool planner |
| Computation | Scientific scripts/code generation and optimization | Prewritten typed tools; frozen Random Forest |
| Data/evaluation | Public SPWLA plus field case; paper's protocol | Pinned public archive; custom 5/2/2 whole-well split |
| Model/search | Agent-guided model/feature optimization | No agent fitting or test-driven tuning |
| Output | Broader reservoir analysis/report generation | CSV, plot, verified execution trace and disposition |
| Meaning of comparison | Literature-linked method | **LogACF-inspired adaptation**, not exact reproduction |

The pinned [author source](https://github.com/DangDang-LG/LogACF/blob/78e2fd011cb8401a959fc060a2f968078638d992/LogACF.py#L707) contains reference-RMSE candidate selection. This motivates keeping our final scoring labels outside the agent. It is a protocol risk to avoid in our experiment, not a conclusion of misconduct or invalidity of the published study.

## G1: request-to-data grounding

**Evidence:** P02 uses structured tool integration; P04 already offers schema adaptation; P08 studies geological standardization. There is no basis to claim the first schema-aware geoscience agent. Their performance on our controlled well/curve/unit perturbations is unestablished.

| Planning item | Definition |
|---|---|
| Specific uncertainty | How often does a planner choose the correct well, curve, target, interval and unit under aliases/ambiguous metadata? |
| Proposed intervention | Explicit semantic registry/checklist and clarification before numerical execution. |
| RQ1 | Does dataset-aware grounding improve semantic argument accuracy over the same planner with minimal contextual grounding? |
| H1 | Higher correct argument/completion rates and fewer wrong-identity/unit attempts. |
| Cases | Alias/canonical pairs, equivalent ft/m intervals, unknown identifiers, missing units, ambiguous quantities. |
| Metrics | Exact well/curve match, interval tolerance, declared unit correctness, valid-request completion, clarification correctness, tool-error count. |
| Comparison | Same LLM, numerical tools, data/model and budgets; prespecify what registry/context policy is removed. Basic type checks and scientific unit conversion remain valid in all variants. |
| Ablation | Full system minus semantic registry/checklist exposure; retain basic software safeguards. |
| Provisional target | At least 10 percentage points more correct semantic arguments, with clean-case completion loss no greater than 5 points. This is an untested planning target. |
| Current evidence | Selected live alias/ft/m cases passed once; no controlled G1 ablation exists. |

Do not confound grounding with changing the numerical predictor or allowing mathematically incorrect tools. Freeze the exact ablation configuration before collecting final test results.

## G2: observable verification and bounded repair

**Evidence:** P01 already includes correction and physical constraints. P13's reflection ablation changes HS from 75.3% to 61.2%. The project should test which deterministic checks help under named faults; a generic critic is established related work.

| Planning item | Definition |
|---|---|
| Specific uncertainty | Can a tool return an apparently usable artifact with wrong identity/schema/values, and will the agent detect it? |
| Proposed intervention | Key/schema/finite/bounds/recomputation checks, with a bounded repair path. |
| RQ2 | Does evidence-based verification reduce silently accepted incorrect artifacts compared with minimal tool use and an LLM review control? |
| H2 | Fewer accepted bad artifacts and more correct recovery on prespecified recoverable faults, at measurable time/token cost. |
| Cases | Missing/stale file, duplicate keys, changed well/depth, corrupted/nonfinite/out-of-range values, controlled exception. |
| Metrics | Detection precision/recall; accepted incorrect fault cases / all injected fault cases; correct repairs / recoverable faults; clean success; retries/time/tokens. |
| Comparisons | No added review; LLM review; deterministic detection only; detection plus repair. Keep budgets and actual predictor fixed. |
| Ablation | Full minus added verification/repair; optionally split detection from repair. Keep structural safety boundaries. |
| Provisional target | 50% relative reduction in accepted incorrect fault cases, with clean-case completion loss no greater than 5 points. Report absolute counts; if the comparator has zero errors, relative reduction is undefined. |
| Current evidence | One deliberate missing-file recovery passed live; corruption/identity checks passed software tests. Other live fault families and comparative effects are unmeasured. |

A shuffled but correctly keyed CSV is not necessarily wrong: identity-safe scoring should remain correct after row reordering. Include it as a metamorphic correctness test. Fault detection is about semantic mismatches, not file order alone. The verifier never uses final target labels to choose or repair a model.

## G3: acceptance, clarification and abstention

**Evidence:** P01 acknowledges data-quality dependence; P02 includes human review. P03 Table 5 shows that improved workflow decisions can accompany increased weighted false termination. This supports measuring refusal tradeoffs instead of reporting success alone. It does not establish an absence of prior abstention work.

| Planning item | Definition |
|---|---|
| Specific uncertainty | Will the system answer invalid/underspecified tasks, or unnecessarily refuse valid ones? |
| Proposed intervention | Explicit acceptance decisions based on observable input sufficiency, resolved semantics and verified execution. |
| RQ3 | Can this reduce incorrect accepted tasks at comparable coverage? |
| H3 | Lower selective task error at matched coverage while limiting unnecessary refusals. |
| Cases | Missing curves, tiny intervals, unresolved units/wells, unsupported targets, severe input degradation. |
| Metrics | Coverage = accepted / all; selective task error = wrong accepted / accepted; refusal precision/recall; false refusals on valid cases. Report undefined ratios when denominators are zero. |
| Comparison | Transparent rule policy versus an always-answer-after-valid-tool baseline; optional confidence-threshold control. Essential hard errors remain failures, never invented answers. |
| Ablation | Full minus the added selective-acceptance policy. |
| Provisional target | At common achievable coverage, target 25% relative selective-error reduction. A 70% coverage reference is optional only if both policies can attain it; otherwise report the attainable curve. |
| Current evidence | Selected unknown-well/unsupported-target cases had appropriate dispositions; no calibrated risk/coverage result exists. |

Use a separately labeled correctness event for task execution. If also studying scientific prediction error under degradation, define its threshold from validation data before final testing. Input-coverage flags and tree variation are not calibrated probabilities. Do not report Brier/ECE or guaranteed intervals without implementing the required probability/calibration protocol.

## Shared experimental controls

- Keep the current numerical predictor frozen across agent variants; scientific prediction and workflow reliability are separate outcomes.
- Separate development prompts from final scenario/paraphrase families. The existing 16 cases are development cases, six of which were run live.
- A feasible semester target is 40 independent scenarios × three paraphrases, with repeated runs if affordable. This is a proposal, not an assignment minimum or executed experiment.
- Start with B0 fixed structured pipeline, B1 minimal tool agent, a documented base-inspired planning/review control, full system and leave-one-component-out variants. These comparative variants are **not yet implemented/evaluated**.
- Record scenario-level counts and uncertainty; neighboring depth rows/paraphrases are not independent experiments. Do not infer significance from six smoke cases.
- Test reproducibility separately: action replay consistency and fresh stochastic run stability are different quantities.
- Use development/validation evidence for prompt/model/policy selection. The currently inspected test wells are no longer a pristine future model-selection test; if tuning begins, plan a fresh locked outer evaluation using available well groups or another dataset, and disclose the Phase 1 exploratory results.

The possible contribution is a precisely specified public well-log reliability evaluation and evidence about these mechanisms. Novelty and publication suitability remain conditional on further related work and actual results.
