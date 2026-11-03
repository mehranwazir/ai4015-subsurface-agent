# Data

Source: [SPWLA PDDA Machine Learning Competition 2021](https://github.com/pddasig/Machine-Learning-Competition-2021), pinned to commit `0ffc94f702feab81f6eb1f4d453e19754a557305` (archive SHA-256 `816d45f6…`). The organizer's noncommercial share-alike terms apply (see `NOTICE.md`), so the data is not stored in Git.

```powershell
python -m subsurface_agent download   # fetches the pinned archive into data/raw/ and checks its checksum
python -m subsurface_agent prepare    # writes data/processed/ and results/data_manifest.json
```

The loader and split code is in `src/subsurface_agent/data.py`.

## Split definition (whole wells, fixed before any scoring)

| Split | Well IDs | Eligible labeled rows | Use |
|---|---|---|---|
| Train | 0, 2, 4, 6, 8 | 33,692 | Fit the Random Forest |
| Validation | 1, 5 | 4,405 | Development and threshold selection |
| Test | 3, 7 | 4,122 | Final evaluation only |

Eligible rows have finite PHIF, SW and VSH values in [0, 1] and at least four of the seven input curves (GR, CALI, DEN, NEU, RDEP, RMED, DTC).

## Files in `data/processed/`

| File | Contents |
|---|---|
| `features.csv` | Every row from all nine wells, with inputs only. This is the only table the agent can read. |
| `train.csv`, `validation.csv`, `test.csv` | Eligible rows with reference labels, used for training and offline scoring only. |
