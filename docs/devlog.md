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
