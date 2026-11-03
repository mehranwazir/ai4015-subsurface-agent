# Development log

Each entry records a failure or limitation we observed, the change made, and its measured effect. Traces for the cited runs are kept under `logs/evidence/`.

## Entry 1: 3 November 2026. Planner assumes an unstated depth unit (G1)

**Observed.** During a fresh-clone verification of the Phase 1 system, a live request with no depth unit, *"Predict porosity for well 3 between 10600 and 11000."*, was sent to `gemini-3.5-flash-lite`. In all three runs the planner called `inspect_interval` with `unit: "ft"` without being told, ran the prediction and answered "successfully completed". The third run hit the free-tier rate limit (HTTP 429) after making the same assumption.

- The Phase 1 system prompt already said "never guess unspecified units".
- The 17 October fix made `unit` a required argument.

Neither helped, because the planner supplies the field itself. A request that stated "ft" behaved correctly. This contradicts the Phase 1 design statement that an unresolved unit leads to clarification.

**Change.** We added switchable system configurations (`src/subsurface_agent/config.py`) and the G1 request-grounding component (`src/subsurface_agent/gaps/grounding.py`):

1. Facts are extracted deterministically from the user's request text: well numbers, depth values, and unit words or symbols.
2. Every `inspect_interval` call is checked against those facts:
   - a well, unit or depth bound that the user did not state is rejected with `UNGROUNDED_WELL`, `UNGROUNDED_UNIT` or `UNGROUNDED_DEPTH`;
   - a missing unit or well is non-recoverable and requires clarification;
   - a value that differs from the stated one is recoverable.
3. The planner prompt gets an authoritative dataset registry (wells, depth ranges, curves, aliases, units) plus a grounding checklist.

With `--config no_g1`, the component is switched off for ablation. Traces recorded before configurations existed replay with the `phase1` configuration.

**Effect (live, same model, 3 November 2026).**

| Request | Before (Phase 1 behaviour) | After (`full`) |
|---|---|---|
| No unit stated | 3/3 assumed ft (2 answered, 1 rate-limited) | **2/2 clarify**, asking whether the depths are in feet or meters; 2 tool calls, about 2.8 s |
| "…10600 to 11000 ft" | answer, 5 calls, 6.6 s | answer, 5 calls, 6.7 s |
| "…3230.88 and 3352.8 meters" | not rerun | answer, 5 calls, 7.3 s |

In both "after" runs, the registry and checklist context led the planner to clarify before calling `inspect_interval`, so the deterministic check did not need to fire. The check is the safeguard for cases where the prompt context is not followed. Offline tests use a scripted planner that always assumes ft, and confirm that the check turns that run into a clarification while `no_g1` lets it answer.

**Limitations.**
- These are a few development runs, not the benchmark result. The G1 effect will be measured on the frozen test set with repeated runs (E4/E5).
- Rule-based extraction can miss unusual phrasings such as "10.6k ft". Such cases would be rejected as ungrounded, which costs a false clarification rather than a silent error.

**Evidence:** `logs/evidence/devlog-001/` (`before-*` from the verification clone, `devlog001-after-*` with G1).

## Entry 2: 3 November 2026. G1 extended to targets, curves and well depth range; clarification no longer requires data inspection

**Observed.** The Phase 1 design defines G1 over well, curve, target, interval and unit, but entry 1 only covered well, interval and unit. Two live checks with G1 switched off (`no_g1`) showed what was still unprotected:

- *"Predict PHIF, SW and VSH for well 3 from 11000 to 11800 ft"*. Well 3 has data only to 11,371.4 ft. The interval tool silently returned the shorter interval, and the planner answered "successfully predicted … from 11000 to 11800 ft".
- *"Predict porosity and permeability …"*. The planner clarified correctly in this run, but only the prompt prevented an answer that silently drops permeability. No code enforced it.

**Change.** In `gaps/grounding.py`, with G1 on:

1. Requested quantities are extracted from the request. A prediction is blocked when the request asks only for unsupported quantities (permeability, production, economics, lithology, retraining, test labels). An `answer` is blocked whenever an unsupported part would be dropped (`UNSUPPORTED_TARGET`).
2. Curves passed to `inspect_interval` must be named in the request (aliases included) or omitted (`UNGROUNDED_CURVE`).
3. An interval extending beyond the well's recorded depths is rejected instead of being shortened silently (`INTERVAL_OUT_OF_RANGE`).
4. The checklist in the prompt now covers targets and curves.

**Regression found and fixed.** The first live run of the permeability request with G1 on **failed**. Because the registry already listed the supported targets, the planner tried to `finish` with clarify immediately. The Phase 1 rule "call `inspect_dataset` before any other tool" rejected that call three times and the run used up its error budget. `finish` with clarify or abstain is now allowed without data access; an `answer` still requires prior inspection (`NO_EVIDENCE`).

**Effect (live, `gemini-3.5-flash-lite`).**

| Request | G1 off (`no_g1`) | G1 on, before fix | G1 on, after fix |
|---|---|---|---|
| 11,000–11,800 ft (beyond well end) | answer on shortened interval (silent error) | abstain: "exceeds well 3 maximum depth of 11371.4 ft", 3 calls | — |
| Porosity and permeability | clarify, 2 calls, 2.6 s | failed (budget exhausted) | **clarify, 1 call, 1.4 s (2/2)** |
| Gamma ray and RHOB, inspect only | — | — | answer, 3 calls, 3.6 s |

**Evidence:** `logs/evidence/devlog-002/`.


## Entry 3: 3 November 2026. G2 made switchable; seven controlled artifact faults; bounded repair; offline oracle

**Observed.** Phase 1 tested only one fault, a missing prediction file. In that run the planner was told the file had been omitted, because the tool output contained `simulation_omitted_artifact`. Verification was also always on, so its benefit could not be measured, and nothing limited how many times the planner could regenerate a file.

**Change.**

1. `gaps/verification.py` holds the G2 verifier and a repair limit:
   - the verifier checks schema, sample/well/depth identity, finite values, [0,1] bounds and frozen-model recomputation;
   - after 2 regenerations of one slice, `REPAIR_LIMIT` forces the planner to stop.
2. `faults.py` injects one fault into the first prediction file of a run. There are seven faults:
   - `missing_file`
   - `corrupt_values` (plausible values within [0,1], detectable only by recomputation)
   - `drop_rows`
   - `duplicate_rows`
   - `wrong_well`
   - `nan_values`
   - `stale_artifact` (correct values attached to another interval)

   There is also one benign control, `shuffle_rows`, which a correct verifier must accept.
3. Faults are hidden from the planner. Only the `phase1` configuration keeps the old field, so recorded traces still replay.
4. Every run now stores an offline `oracle` record:
   - the injected fault;
   - whether it was applied;
   - the validity of every final artifact.

   The oracle is used for scoring silent-error acceptance and is never returned to the planner.
5. With `no_g2`, the verify step accepts artifacts unchecked, and answers and plots are not gated on verification.

**Effect (live, `gemini-3.5-flash-lite`, request "Predict PHIF, SW and VSH for well 3 from 10600 to 11000 ft and verify the result").**

| Fault | G2 off (`no_g2`) | G2 on (`full`) |
|---|---|---|
| `corrupt_values` | answer claiming "verified", final file invalid (`RECOMPUTE_MISMATCH`) | detected, regenerated, re-verified: answer with valid file, 7 calls, 9.3 s |
| `stale_artifact` | answer, final file invalid (`ARTIFACT_IDENTITY`) | detected, regenerated, re-verified: answer with valid file, 7 calls, 10.1 s |
| `shuffle_rows` (benign) | — | accepted, no false alarm, 5 calls, 7.2 s |

With G2 off, both faulty runs ended in confident answers on invalid artifacts. These are exactly the silent errors Gap 2 targets. With G2 on, recovery cost 2 extra tool calls and about 2–3 s.

**Offline tests:**
- every fault is detected and repaired with G2 on, and `shuffle_rows` is accepted;
- every harmful fault is accepted silently with G2 off, and the oracle records it;
- repair is bounded.

**Evidence:** `logs/evidence/devlog-003/`.


## Entry 4: 3 November 2026. G3 evidence-based acceptance calibrated on the validation wells

**Observed.**
- Phase 1 refused only when an interval had fewer than 10 usable rows or less than 60% input coverage.
- Any interval that passed those rules was answered, however uncertain the model was. The Phase 1 report itself notes these were "demonstration rules, not calibrated confidence thresholds".
- On the validation wells, 16.1% of 100-ft windows have a mean property RMSE above 0.05 when the system always answers.

**Change.** `gaps/acceptance.py` adds the G3 component.

1. **Evidence.** Each prediction carries:
   - input coverage;
   - **model uncertainty:** the spread of the 80 trees' predictions, averaged over PHIF/SW/VSH and the interval;
   - the share of rows with inputs outside the training wells' 0.5–99.5% range.
2. **Calibration** (`python -m subsurface_agent calibrate-g3`, written to `models/g3_policy.json`). Run on the **validation wells 1 and 5 only**, over 56 sliding 100-ft windows (25-ft step).
   - Requirements declared before calibration: an acceptable window has mean property RMSE ≤ 0.05, and at most 5% of accepted windows may exceed it.
   - The largest-coverage uncertainty limit meeting this is **0.0254**.
3. **Gate.** `finish` with `answer` is refused (`LOW_EVIDENCE`) when an interval's uncertainty exceeds the limit. The planner must abstain.
4. **Switch.** `no_g3` removes the evidence and the gate, so the system answers whenever its tools succeed.

The policy records the model SHA-256 and is rejected if the model changes.

**Calibration result (validation wells only; test wells untouched).**

| Policy | Windows answered | Answered windows with RMSE > 0.05 |
|---|---|---|
| Always answer (`no_g3`) | 100% | 16.1% |
| G3 (`full`) | 64.3% | 2.8% |

**Negative finding.** Model uncertainty tracks window error (Spearman 0.53). The out-of-range share does not (Spearman ≈ 0.01 for 100-ft windows, −0.08 for 200-ft windows). It is therefore reported with each prediction but **not** used to decide.

**Effect (live, `gemini-3.5-flash-lite`).** Intervals were chosen by uncertainty alone; no reference labels were used.

| Request | G3 off (`no_g3`) | G3 on (`full`) |
|---|---|---|
| Well 3, 10,600–11,000 ft (uncertainty 0.0240) | — | answer, 5 calls, 7.0 s |
| Well 3, 10,200–10,500 ft (uncertainty 0.0363) | answer, 5 calls | **abstain**, citing "uncertainty 0.0363 exceeds the calibrated limit 0.0254", 6 calls, 8.3 s |
| Well 7, 14,400–14,600 ft (uncertainty 0.0282) | — | **abstain**, 6 calls, 7.9 s |

In both abstaining runs, the prediction output already showed `decision: "abstain"`, but the planner still called `finish` with `answer` first. The deterministic gate refused it (`LOW_EVIDENCE`), and the planner then abstained. Without the gate, the evidence alone would not have changed the outcome.

Whether these refusals avoid real errors, and what they cost in false refusals, is measured on the frozen test set in E4/E5. No test-well labels were used here.

**Evidence:** `logs/evidence/devlog-004/`; policy `models/g3_policy.json`.


## Entry 5: 3 November 2026. Comparison systems B0 (fixed pipeline) and B2 (LogACF-style roles)

**Need.** Experiments E1 and E2 compare the proposed system against a simpler non-agentic baseline and against the base paper's approach on the same data, tools and metrics. Phase 1 defined both, but neither existed in code.

**Change.**

- **B0** (`baselines/fixed_pipeline.py`, `--config b0`): a conventional script with no LLM.
  - It parses the first well number and two depths with the same text rules as G1.
  - It defaults to feet when no unit is given.
  - It always runs inspect → predict → report. Tool errors are reported as a refusal.
  - It cannot ask questions, verify files or repair them.
- **B2** (`baselines/logacf_style.py`, `--config b2`): an adaptation of LogACF's role-based design.
  - A **Planner** (LLM) reads the request and the shared dataset knowledge and submits one complete plan.
  - An **Executor** (code) runs it with the same allowlisted tools.
  - A **Reviewer** (LLM) reads the execution log and a descriptive preview of the prediction file (rows, wells, depth range, missing values, value ranges). It then approves, requests one regeneration, or clarifies/abstains.
  - It uses the same model and data as the proposed system, but none of the G1/G2/G3 components: checking relies on LLM review. It is an adaptation of the base paper's design, not a reproduction of the authors' code.
- **Shared run format.** Every system now saves the same run record (`agent.finalize_run`), including the offline oracle. All three systems are scored identically and replay without an LLM call.

**Smoke check (live, `gemini-3.5-flash-lite`; not a benchmark result).**

| Request | B0 | B2 |
|---|---|---|
| "…well 3 from 10600 to 11000 ft…" | answer, 0.0 s, no API calls | answer, 2 requests, 3.3 s |
| No unit stated | answer, assumed ft | answer, planner assumed ft |
| `corrupt_values` fault | answer on invalid file | reviewer approved; invalid file |
| `drop_rows` fault | — | reviewer approved, although the execution log showed 1,220 predicted rows and the preview showed fewer; invalid file |

These single runs show the behaviours the experiments will quantify:
- the fixed script cannot recognise ambiguity or faults;
- LLM review can miss inconsistencies that a deterministic check catches every time.

The rates are measured in E1, E2 and E4 on the frozen test set.

**Evidence:** `logs/evidence/devlog-005/`.


## Entry 6: 3 November 2026. Resumable experiment runner, independent scorer, and a latency measurement error

**Need.** E1–E6 require:
- every system to run on the same cases at least three times;
- metrics reported as mean ± standard deviation;
- recorded decoding settings;
- results that survive free-tier quota interruptions.

Phase 1 had only a single-pass smoke evaluator that trusted the requested tool list.

**Change.**

- `providers.py`: explicit decoding settings (temperature 1.0 by default, a per-repeat seed), stored with every run as `generation`. The runner also turns on request pacing (`--min-interval`, default 4.5 s) and waits out HTTP 429 responses (`--rate-limit-waits`, default 10 one-minute waits).
- `experiments.py` (`python -m subsurface_agent experiment` / `summarize`):
  - runs repeats × systems × cases;
  - skips completed runs, so an interrupted batch resumes;
  - keeps provider-failed attempts as `-providerfail-N` and retries them;
  - stops at the first provider failure;
  - runs the deterministic B0 once.
  - Summaries are written to `results/experiments/<name>/` (`runs.csv`, `summary.csv`, `summary.json`), with mean and standard deviation across repeats.
- `scoring.py`: scores each run from trace events, the offline oracle and reference labels. It never uses the system's own success claim. Per run it records:
  - task correctness;
  - argument correctness;
  - unwarranted answers;
  - fault detection, silent errors and repairs;
  - the reference error of the requested interval (what answering would have cost);
  - the error of the file actually reported;
  - latency, requests, tokens and tool calls.

  Task correctness requires all of the following:
  - an allowed disposition;
  - no answer resting on an invalid artifact;
  - no reported answer worse than the 0.05 acceptance requirement;
  - where a case allows answering or abstaining, the choice supported by the interval's reference error.

  Reference labels are read only by the scorer.

**Failure found and fixed: pacing inflated latency.** In the first live smoke experiment (`smoke1`), the full system appeared to take 22.1 s per request. Most of that was the runner's own 4.5 s pause before each Gemini request: the full system makes about 5 requests per run, B2 makes 2. Counting these pauses as system latency would bias E6 against whichever system makes more calls. The provider now accumulates `throttle_seconds`. Each run records it with `active_latency_seconds` (wall time minus throttling), and the scorer uses active latency.

| Smoke experiment (4 cases, 1 repeat) | B2 mean latency | Full mean latency |
|---|---|---|
| `smoke1` (wall clock, pauses included) | 8.09 s | 22.11 s |
| `smoke2` (active latency) | 3.53 s | 7.03 s |

**Smoke result (`smoke2`, validation wells, live).** This is an end-to-end check of the runner and scorer, not an evaluation result. The cases were:
1. a clean request;
2. a request with no unit;
3. a `corrupt_values` fault;
4. an interval whose reference error is 0.0515.

| System | Task success | Unwarranted answers (G1 case) | Silent errors (G2 case) | Answered the 0.0515 interval | Active latency | Requests |
|---|---|---|---|---|---|---|
| B0 | 1/4 | 1/1 | 1/1 | yes | 0.04 s | 0 |
| B2 | 1/4 | 1/1 | 1/1 | yes | 3.53 s | 2.0 |
| Full | 4/4 | 0/1 | 0/1 (repaired) | no (abstained) | 7.03 s | 5.0 |

**Evidence:** `logs/evidence/devlog-006/` (all 24 smoke runs) and `results/experiments/smoke1/`, `results/experiments/smoke2/`.


## Entry 7: 3 November 2026. Benchmark, development round, two fixes, and the system freeze

**Benchmark.** `experiments/build_benchmark.py` generates both benchmarks deterministically. The selection rules are listed in its header.

- **Development set** (`experiments/benchmark/dev.json`): 33 cases on validation wells 1 and 5.
- **Test set** (`experiments/benchmark/test.json`): 50 cases on test wells 3 and 7.
- **Prediction cases** lie on a fixed 100-ft grid over each well's labelled depth range. The test set phrases every interval twice. Phrasings include ft, "feet", metres, curve aliases and plot requests.
- **Fault cases** cover all seven harmful faults plus the benign `shuffle_rows`, once in dev and twice in test.
- **Twelve requests must not be answered:** missing unit, vague well, unknown well, out-of-range interval, permeability, production forecasting, test-label tuning.
- **No wording contains behavioural hints.** `tests/test_benchmark.py` checks that, plus the well split and the case format.
- **G1 reading check.** An offline check confirmed that G1 reads every fully specified request in both sets correctly: 0 of 59 wrongly blocked.

**Development round 1 (`dev1`, live, one repeat).**

| Metric (dev, 33 cases) | B0 | B2 | Full |
|---|---|---|---|
| Task success | 0.545 | 0.727 | 0.909 |
| G1 unwarranted answers | 0.417 | 0.167 | 0.000 |
| G2 detection / silent errors | 0.000 / 1.000 | 0.143 / 0.857 | 1.000 / 0.000 |
| G3 coverage / selective error / false refusals | 1.000 / 0.077 / 0.000 | 1.000 / 0.077 / 0.000 | 0.692 / 0.000 / 0.250 |
| Mean requests / active latency | 0 / 0.03 s | 1.73 / 2.90 s | 4.42 / 6.88 s |

**Observed failures and changes (all decided on development data only).**

1. **The planner ignored G3 evidence.** In 6 of 6 full-system G3 refusals, the prediction output already said `decision: "abstain"`. The planner still verified (sometimes plotted), attempted `finish` with `answer`, was refused by the gate (`LOW_EVIDENCE`), and only then abstained. That is one wasted request per refusal.
   - **Change:** with G3 on, the prompt gains an evidence rule. If `evidence.decision` is `abstain`, the planner must not verify further, plot or answer, and must abstain and report the uncertainty.
   - **Effect** (`dev2`, full system, same 33 cases): wasted answer attempts went from 6/6 to **0/6**. Mean requests fell from 4.42 to **3.88** and active latency from 6.88 s to **6.05 s**. Task success was unchanged (0.909).
2. **G3 false refusals on well 5.** All three full-system failures in both rounds were abstentions on well-5 intervals whose reference error (0.029–0.048) met the 0.05 requirement. Their uncertainty (0.029–0.033) exceeded the limit 0.0254. On the validation windows, all 9 windows above 0.05 RMSE are on well 5, and the risk–coverage trade-off is:

   | Uncertainty limit | Coverage | Risk among answered | Good windows refused |
   |---|---|---|---|
   | 0.0254 (calibrated) | 0.62 | 0.000 | 0.26 |
   | 0.028 | 0.73 | 0.098 | 0.21 |
   | 0.030 | 0.82 | 0.109 | 0.13 |
   | no gate | 1.00 | 0.161 | 0.00 |

   - **Decision:** every looser limit admits bad answers and breaks the requirement declared before calibration (at most 5% risk). The limit is therefore **unchanged**. These refusals are the measured cost of G3, not a defect.
   - The full curve is now stored in `models/g3_policy.json` (`tradeoff`) for reporting.
3. **Scorer: repair was conflated with G3.** In `dev1`, two fault cases were repaired correctly by G2, and G3 then abstained on the uncertain interval. The scorer counted these as failed repairs. A repair is now a valid final artifact after a harmful fault, whatever the final disposition. Full-system G2 repair rate on `dev1`: 0.714 → **1.000**.
4. **Benchmark: G3 could mask G2.** With the evidence rule, fault cases on uncertain intervals ended in early abstention before verification (`dev2` G2 detection 0.714, no silent errors). Fault cases now use only grid intervals that G3 would accept, computed from input curves and the frozen model with no reference values. G2 is therefore measured in isolation. The test set had not been run when this rule was set.
   - **Confirmation run (`dev3`).** The run of the five moved development fault cases (`experiments/benchmark/dev_faults_check.json`) was first interrupted by the API project's limits:
     - HTTP 429 `RESOURCE_EXHAUSTED` after 501 requests on 3 November;
     - then HTTP 403 stating that the free tier was unavailable for the project.

     After billing was enabled (same model and settings), the run completed:
     - 4/4 harmful faults were detected and repaired, with 0 silent errors;
     - the benign `shuffle_rows` case was accepted with no false alarm;
     - mean 6.6 requests and 9.69 s active latency per run (each repair adds a regeneration and a re-verification).

**Freeze.** After these changes the system is frozen for the final evaluation. The frozen parts are:
- agent prompt and tools;
- G1/G2/G3 components and the G3 policy;
- B0 and B2;
- scorer;
- benchmark files.

The test benchmark has not been run by any system. Any later change must be logged here with its reason, and would require rerunning the affected test experiments.

**Evidence:** `logs/evidence/devlog-007/` (all 137 `dev1`/`dev2`/`dev3` runs); `results/experiments/dev1/`, `results/experiments/dev2/`, `results/experiments/dev3/`.
