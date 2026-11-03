# Experiments

| Path | Contents |
|---|---|
| `build_benchmark.py` | Deterministic generator for the two benchmarks; its header states the selection rules. |
| `benchmark/dev.json` | **Development benchmark**, 33 cases on validation wells 1 and 5: 13 grid-interval predictions, 8 artifact-fault cases (7 harmful + the benign `shuffle_rows`), 12 requests that must not be answered. Used for development rounds only. |
| `benchmark/test.json` | **Test benchmark**, 50 cases on test wells 3 and 7: 22 predictions (each grid interval phrased twice), 16 fault cases (each fault twice), 12 must-not-answer requests. Used only for the final E1-E6 runs. |
| `benchmark/dev_faults_check.json` | The five development fault cases moved to G3-accepted intervals (devlog entry 7), for a confirmation run. |
| `benchmark/smoke.json` | Four end-to-end runner checks on the validation wells. |
| `phase1_smoke_cases.json` | The 16 manually written Phase 1 development cases, used by `python -m subsurface_agent evaluate`. |

Each case gives the request text, an optional injected fault and the expected outcome. Prediction requests allow `answer` or `abstain`; the scorer decides which was right from the interval's reference error (0.05 mean property RMSE requirement). Requests that are ambiguous, impossible or unsupported must be clarified or refused.

```powershell
python experiments/build_benchmark.py                      # regenerate both benchmarks
python -m subsurface_agent experiment --name dev2 --cases experiments/benchmark/dev.json --systems full --repeats 1
python -m subsurface_agent summarize --name dev2 --cases experiments/benchmark/dev.json
```

Outputs go to `results/experiments/<name>/`. Development rounds `dev1` (B0, B2, full) and `dev2` (full, after the fixes in devlog entry 7) are recorded there. The final E1-E6 configurations are added in the next stage.
