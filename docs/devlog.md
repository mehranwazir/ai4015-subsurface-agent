# Development log

Each entry records a failure or limitation we observed, the change made, and its measured effect. Traces for the cited runs are kept under `results/evidence/`.

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

**Evidence:** `results/evidence/devlog-001/` (`before-*` from the verification clone, `devlog001-after-*` with G1).
