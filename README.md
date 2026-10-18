# GridAI — seven-target forecasting

Load, wind, solar, hydro, fossil, nuclear and aggregate imports, with six methods compared for each target. The executed notebook, fitted artifacts, test predictions and evaluation reports are included.

## Run the dashboard

Use Python 3.13 (the training environment). From this folder:

```sh
python -m pip install -r requirements.txt
python -m uvicorn backend.app:app --port 8000
```

Open http://127.0.0.1:8000. The backend serves the dashboard. The Forecast Explorer starts at the current quarter-hour; changing targets preserves your selected date and time. Seven targets are available in all generated panels.

## Reproduce

Open `notebooks.ipynb` and run all cells to inspect data, definitions, model comparisons, charts, coverage and exports. The supplied notebook loads executed artifacts by default. Set `RETRAIN = True` in section 6 to retrain, or run:

```sh
python -m ml.pipeline
python validate_project.py
```

After retraining, rerun the notebook and restart the API. Fixed seed 42 and the exact installed versions are recorded in `backend/data/metadata.json`. The original notebook is preserved in `archive/`; its paths, scores and old export are historical and are not consumed by the application.

## Method and target definitions

Each target uses a chronological 70/15/15 split of eligible rows. All six candidates share the same rows and causal lag/calendar features: persistence, daily seasonal persistence, Ridge, Extra Trees, direct XGBoost and delta XGBoost. Validation MAE selects deployment; all candidates' test MAE/RMSE are exported. The selected artifact is not refitted on validation or test data. Comparisons across targets involve different dates and scales.

Fossil sums lignite, coal-derived gas, gas, hard coal and oil actual generation; every component must be observed. Nuclear uses its actual aggregated column with no long-gap imputation. Imports uses `generation_import_Import_sum`; country flows are not summed again. Wind combines onshore/offshore, and hydro combines run-of-river, reservoir and pumped generation, excluding consumption. Definitions are explicit in `ml/pipeline.py`.

Reindexing to a UTC quarter-hour grid and requiring a complete preceding week prevents gaps being bridged by positional lags. No target values are imputed. Delta bundles reconstruct absolute MW before evaluation, saved predictions and inference. The backend shares those functions with training.

## Results

- **Electricity Load:** Delta XGBoost, test MAE 263.88 MW, RMSE 377.20 MW; +49.40% MAE improvement versus persistence.
- **Wind Generation:** Ridge Regression, test MAE 192.11 MW, RMSE 292.87 MW; +31.37% MAE improvement versus persistence.
- **Solar Generation:** Delta XGBoost, test MAE 152.18 MW, RMSE 303.43 MW; +73.97% MAE improvement versus persistence.
- **Hydro Generation:** Delta XGBoost, test MAE 229.99 MW, RMSE 365.67 MW; +16.75% MAE improvement versus persistence.
- **Fossil Generation:** Ridge Regression, test MAE 163.12 MW, RMSE 254.41 MW; +33.85% MAE improvement versus persistence.
- **Nuclear Generation (historical):** 15-minute Persistence, test MAE 4.65 MW, RMSE 14.46 MW; +0.00% MAE improvement versus persistence.
- **Electricity Imports:** Extra Trees, test MAE 663.90 MW, RMSE 997.14 MW; -7.80% MAE improvement versus persistence.

## Files to inspect

- `notebooks.ipynb`: executed analysis and explanations.
- `backend/data/model_comparison.csv`: all 42 model/target evaluations.
- `backend/data/*_test_predictions.csv`: absolute-MW predictions for every test row and method.
- `backend/data/metadata.json`: source hash, exact definitions, coverage, split dates, selection, scores and validation permutation importance.
- `backend/data/recursive_backtest.csv`: up to three daily recursive tests per target, clearly separate from full one-step evaluation.
- `backend/data/validation_report.json`: integration check results.
- `backend/models/*_selected.joblib`: deployed bundles, including feature order and prediction transform. The six candidates per target are also saved.

## Scope and limitations

This is an educational historical forecasting project. The source data stops in August 2026 overall; nuclear stops in April 2023 while complete fossil coverage excludes periods with a missing component. Future first-prediction dates have no upper cutoff. The backend recursively bridges from the last source observation to the selected date; earlier times still require enough actual history to construct features. Horizons up to one week are generated recursively and are not evaluated by the displayed one-step MAE/RMSE.

The daily recursive report is a small three-origin diagnostic, not a comprehensive long-horizon benchmark. Future weather, outages and plant schedules are excluded. The original dataset's provenance, license and MW units require verification from its data provider; a data dictionary was not supplied. No synthetic training observations or fabricated performance numbers are used.

Permutation importance uses up to 1,000 validation rows, three repeats and seed 42; positive MAE increases are normalized for dashboard bars, while raw increases remain in metadata. Correlated features limit interpretation.


## Documented data-quality exclusion

The known corrupt load record at 2026-06-25 16:30 UTC (4,315,702.57803 MW), identified in the original notebook, is excluded from modeling. The preceding-week eligibility rule also excludes rows whose features would depend on it. The raw CSV is preserved. Averaging the neighboring observations was considered but not used because the following observation would be future information. This known-record exclusion is documented explicitly; it is not a threshold tuned to improve test scores.

Legacy .pkl files copied from the original ZIP are retained for reference. The rebuilt backend loads only *_selected.joblib bundles; legacy files are unused.


## Current-quarter overview snapshot

The overview uses the browser clock rounded down to a quarter-hour: 18 October 2026 at 17:49 displays 17:45. Refreshing in the same period reuses that snapshot; entering a new quarter triggers a new prediction automatically. The backend recursively extends historical model predictions to that timestamp and caches the latest week for incremental updates. The card shows the real source-data cutoff and labels extrapolation; it does not represent a live measurement. Nuclear remains a historical persistence extrapolation. The first request per target after server restart may take longer while generating the intervening steps. The Forecast Explorer also supports arbitrary future origins using the same recursive extension. Run python validate_snapshot.py to check all seven snapshot targets.


## Forecast request consistency

Changing any forecast input clears the previous chart and metrics. Failed requests leave an empty result, and responses from superseded requests are ignored. The returned target and first timestamp are checked before rendering. Target/model columns use a consistent grid and right-aligned model names.


## Direct long-range Solar

The short-term delta model can accumulate unrealistic values when recursively extended for months. Solar now uses a separate direct calendar model if its first prediction is more than one day beyond source observations, or if a future-origin request spans more than one day. Historical origins still use causal observed history. There is no upper date cutoff.

Three methods were compared: a monthly quarter-hour seasonal profile, Calendar Extra Trees, and Calendar XGBoost. They use only target calendar information (Berlin hour, minute, month, annual sine/cosine, year), with no target feedback. Each model is fitted on the original training window and selected by validation MAE. At each validation/test window start, calibration is fixed using only the preceding 28 days of observed Solar. This is a direct long-range evaluation across the full held-out window, not one-step walk-forward.

Validation selected Calendar Extra Trees: test MAE **2719.10 MW**, RMSE **5467.38 MW**. These scores are intentionally separate from the short-term Solar scores. The dashboard displays the actual method's metrics. The three long-range comparisons are expanded under Solar in Model Performance.

Deployment calibration uses observations at/before the source cutoff. Predictions are nonnegative and bounded by the maximum Solar observed before that cutoff. Month/quarter bins with at least 99.5% exact zeros in training are masked to zero. This produces a seasonal average pattern, without future clouds or capacity growth; it is not a weather forecast. Results far beyond the source period remain uncertain.

`python -m ml.pipeline` now also trains this Solar extension. To retrain it alone, run `python -m ml.solar_long_range`. Inspect `backend/data/solar_long_range_comparison.csv`, `solar_long_range_test_predictions.csv`, and `solar_long_range_report.json`. Run `python validate_solar_long_range.py`, `python validate_snapshot.py`, and `node tests/frontend_forecasts.cjs` for the relevant checks.


## Restored notebook progression

The current `notebooks.ipynb` begins with 61 relevant original cells, followed by the current seven-target analysis. Part A restores raw CSV inspection, row/column counts, head/tail, dtypes, dataset start/end, duplicate/sort checks, timestamp continuity, raw timestamp samples, missing counts and percentages for every measurement, missingness categories, the load anomaly investigation, exploratory plots, correlations, continuous segments, missing-period tables, calendar/lag/rolling feature preparation, chronological splitting and persistence evaluation.

Paths and a few outdated operations were adapted to the final decisions: retain high-missing target columns, exclude the known corrupt load observation without future interpolation, use German local time for calendar profiles, and build features on a complete time grid. Repeated rebuild attempts and obsolete model exports remain in the unchanged original archive. The seven-target-only notebook from before this restoration is also preserved in `archive/seven_target_notebook_before_progress_restore.ipynb`.

Fossil, Nuclear and Imports each now include separate cells for source-column missingness, target dates/statistics, feature eligibility, chronological split shapes/dates, optional target-specific retraining, artifact loading, validation/test predictions, delta reconstruction, explicit MAE/RMSE calculations, persistence comparisons and residual analysis. The final section independently recalculates all 42 short-term test comparisons and the three separate long-range Solar comparisons.

The expanded notebook contains 154 cells, including 90 executed code cells with no execution errors. The 18 validation/test score sets recomputed for Fossil/Nuclear/Imports match the saved artifacts. See `backend/data/notebook_progress_restore.json` and the three `*_notebook_recomputed_metrics.csv` files.
