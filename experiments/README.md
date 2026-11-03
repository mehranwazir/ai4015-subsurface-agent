# Experiments

| Path | Contents |
|---|---|
| `phase1_smoke_cases.json` | The 16 manually written development cases from Phase 1, used by `python -m subsurface_agent evaluate`. These are smoke tests only, not the benchmark. |
| `benchmark/smoke.json` | Four end-to-end runner checks on validation wells 1 and 5: a clean request, a missing unit, a corrupted file, and an interval whose reference error exceeds 0.05. |

Run with `python -m subsurface_agent experiment --name <name> --cases <file> --systems ... --repeats N` and score with `summarize`. Outputs go to `results/experiments/<name>/`; see the README section "Run an experiment".

Phase 2 adds the development and test benchmarks and one configuration per required experiment (E1 baseline, E2 base paper, E3 proposed system, E4 gap-wise, E5 ablation, E6 efficiency and reliability).
