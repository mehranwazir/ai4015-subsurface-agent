# Logs

| Folder | Contents |
|---|---|
| `evidence/` | Retained agent trajectories for the runs reported in the README, the development log and the paper. Each run has `result.json` (disposition, configuration, usage, versions, trace) and `events.jsonl` (one line per tool call or provider event); some also have prediction CSVs and plots. |
| `runs/` | Every new local run (`agent`, `evaluate`, `replay`). Excluded from Git; copy runs that are cited into `evidence/`. |

Any recorded trace can be replayed without calling the LLM:

```powershell
python -m subsurface_agent replay logs/evidence/gemini-e2e-002/result.json
```
