# Initial executed protocol (Phase 1)

## What was fixed before scoring

- Public source commit and archive checksum are pinned in `data.py`.
- Split: train IDs 0/2/4/6/8, validation IDs 1/5, test IDs 3/7.
- Cohort: all three target labels finite and within [0,1]; at least four finite input curves. No clipping.
- Features: GR/CALI/DEN/NEU/RDEP/RMED/DTC. Identity/depth/targets are excluded from model inputs.
- Train-only median imputation and missingness indicators; fixed 80-tree/depth-10/leaf-3 Random Forest, seed 42, one worker.
- Training-mean predictor as comparator.
- No model search, validation-based selection, or test-based improvement loop was performed.

## What the scores mean

`macro_target_rmse` is the arithmetic mean of the three separately computed pooled property RMSEs. It is not the square root of the mean of all property squared errors. `macro_well_rmse` gives each held-out well ID equal weight. Both are reported to expose aggregation differences.

MAE/RMSE are in target fraction units. R² is undefined for constant reference arrays and is recorded as null. Zero out-of-bounds predictions do not prove geological correctness; Random Forest averages bounded training labels.

The cohort is conditional on reference-label quality. It does not represent every depth row in the field. The source has many unlabeled/nonreservoir intervals. The agent can inspect full feature data but predicts only where at least 10 rows and 60% of the requested interval have four usable curves. Those are prespecified demonstration rules, not calibrated uncertainty guarantees.

## Comparison to LogACF

The project adapts a workflow concept rather than reproducing LogACF. The current system has one native-tool LLM planner, prewritten deterministic tools, a frozen classical predictor, another model/provider, and a different well/cohort split. It does not reproduce role/memory ablations, NMR multimodal models, agent-driven model search, author prompts, or original training/test results.

Therefore do not compare our RMSE numerically to the paper's RMSE as an improvement claim. Research comparisons must run the specified baseline variants under the same data, predictor, query suite, model, and execution budgets. These ablations have not been performed in Phase 1.

## Actual evidence versus tests

- `results/baseline_metrics.json`: real public-data training and scoring.
- `results/data_manifest.json`: observed data counts, exclusions, source hashes, units and split IDs.
- `results/evidence/`: selected actual Gemini traces, CSVs, and plots, including an initial provider failure.
- `results/agent_evaluation.json`: only the executed subset of the 16-case convenience smoke suite.
- `results/tests.xml`: software test execution. Tests use tiny synthetic fixtures and a clearly labeled scripted provider; they are not model performance experiments.

The smoke prompts were manually authored to exercise interfaces and include explicit hints. This is development evaluation, not a blinded held-out benchmark, statistical validation, a novelty result, or proof that G1/G2/G3 improve a baseline. Fault-injection cases label the injected fault explicitly.

## Important limits

Only one field and two held-out well IDs are scored. IDs may include related wellbores; no cross-field or statistically independent-well guarantee is established. Labels are interpreted petrophysical estimates. Missingness, label filtering, and field-specific interpretation practices can affect scores. Poorer well/target performance is retained, including SW R² on well 7.

The agent uses feature summaries, typed tools, and deterministic consistency checks. It has no unrestricted Python executor or access to target labels, external search, production forecasting, permeability prediction, or economics. A successful file check cannot establish scientific truth. A refusal rule is not a calibrated probability.

Fresh LLM runs are stochastic and API dependent. Replay checks fixed recorded actions in the same pinned environment without a new LLM call. API invoice costs have not been queried. Failed runs remain failures; no result is invented.
