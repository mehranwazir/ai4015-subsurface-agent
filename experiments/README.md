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

Outputs go to `results/experiments/<name>/`. Development rounds `dev1` (B0, B2, full) and `dev2` (full, after the fixes in devlog entry 7) are recorded there. The final E1-E6 runs are described below.

## Final evaluation (E1-E6)

The final runs use the frozen system on `benchmark/test.json` only, with three repeats for every LLM system (B0 is deterministic and runs once). Ablations use `--scope own-gap`: each runs only on the cases of the gap whose component it removes (no_g1 on the 34 G1 cases, no_g2 on the 16 fault cases, no_g3 on the 22 prediction cases). This scope was chosen before any test run, to fit the API budget.

| Experiment | Systems | What it shows |
|---|---|---|
| E1 Baseline | `b0`; numerical baseline in `results/baseline_metrics.json` | Non-agentic pipeline on the same cases; Random Forest vs training-mean RMSE |
| E2 Base paper | `b2` | LogACF-style planner/executor/reviewer, reproduced by us on the same data and cases |
| E3 Proposed system | `full` | Complete system with G1, G2 and G3 |
| E4 Gap-wise | `full`, `b2`, `b0` on G1 / G2 / G3 cases | One comparison per gap, testing the Phase 1 hypotheses |
| E5 Ablation | `no_g1`, `no_g2`, `no_g3` vs `full` on the same cases | Contribution of each component |
| E6 Efficiency and reliability | all | Latency (pacing excluded), requests, tokens, tool calls, provider failures |

The three commands can run in parallel, each with its own credentials file (`.env`, `.env.keyB`, `.env.keyC`; all ignored by Git). Rerunning a command resumes where it stopped.

```powershell
python -m subsurface_agent experiment --name final --cases experiments/benchmark/test.json --systems b0 full --repeats 3
python -m subsurface_agent experiment --name final --cases experiments/benchmark/test.json --systems b2 no_g3 --repeats 3 --scope own-gap --env-file .env.keyB
python -m subsurface_agent experiment --name final --cases experiments/benchmark/test.json --systems no_g1 no_g2 --repeats 3 --scope own-gap --env-file .env.keyC
python -m subsurface_agent summarize --name final --cases experiments/benchmark/test.json
```

`summarize` must be run once at the end with all systems; partial summaries written when a single command finishes are overwritten.

### How the reported final run was executed

Each API project's free tier allows 500 requests per day, so the systems were split across three credentials files and run in parallel under the same experiment name. Interrupted processes were simply rerun until all 566 runs were complete (devlog entry 8):

```powershell
python -m subsurface_agent experiment --name final --cases experiments/benchmark/test.json --systems b0 full b2 --repeats 3
python -m subsurface_agent experiment --name final --cases experiments/benchmark/test.json --systems b2 no_g3 full --repeats 3 --scope own-gap --env-file .env.keyB
python -m subsurface_agent experiment --name final --cases experiments/benchmark/test.json --systems no_g1 no_g2 --repeats 3 --scope own-gap --env-file .env.keyC
python -m subsurface_agent summarize --name final --cases experiments/benchmark/test.json
python experiments/analyze.py
```

`--scope own-gap` affects only the ablation systems; `b0`, `b2` and `full` always run on all 50 cases. The saved records of all 566 runs are in `logs/evidence/final/`; `summarize --runs-dir logs/evidence/final` re-scores them without any API calls, and `analyze.py` writes the tables (`results/final/tables/`), figures (`results/final/figures/`) and `docs/FAILURE_ANALYSIS.md`.
