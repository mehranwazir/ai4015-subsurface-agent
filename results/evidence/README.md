# Executed evidence snapshots

These files copy actual runs from ignored `results/runs/` so reviewers can inspect the initial execution after cloning. They are factual engineering evidence, not assessed proposal prose. Public-source derived predictions remain subject to the data notice in `NOTICE.md`.

- `gemini-e2e-001/`: real provider failure (HTTP 404), retained as failed.
- `gemini-e2e-002/`: real successful prediction/verification/plot run, 1,220 rows.
- `eval-3f3d592c-*/`: all six selected real developer smoke runs, including deliberately injected missing-artifact recovery.
- `replay.json`: all six structured outputs matched without a model call.
- `model_manifest.json`: manifest for the actual locally trained model. Model binary is recreated by the baseline command and is ignored by Git.
- `request_accounting.json`: per-run request counts derived from the original batch's cumulative counters. Original records are unchanged; code has since been fixed.
- `tests_sandbox_temp_failure.xml`: unsuccessful fixture setup in the default sandbox temp directory. The successful final 19-test result is `../tests.xml`.
- `index.json`: SHA256 inventory of these snapshot files, excluding the index itself.

No raw provider conversation, authentication header, API key, or hidden reasoning is saved. Event traces contain tool names, structured arguments and observable tool outputs. Token figures come from returned usage metadata and do not establish invoice cost.

The traces' recorded tool outputs can be replayed after recreating pinned data/model artifacts. Prediction CSV bytes are preserved; plot bytes can vary with rendering versions and are not the replay equality oracle. See `docs/EXPERIMENT_PROTOCOL.md` and `docs/STAGE6_STATUS.md` for comparison limits and unexecuted work.
