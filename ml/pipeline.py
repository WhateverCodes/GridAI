"""Shared, causal training and inference definitions for GridAI."""
from pathlib import Path
import hashlib
import json
import platform
import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[1]
TITLES = dict(load='Electricity Load', wind='Wind Generation', solar='Solar Generation',
              hydro='Hydro Generation', fossil='Fossil Generation',
              nuclear='Nuclear Generation (historical)', imports='Electricity Imports')
SOURCES = {
    'load': ['load_Actual Load'],
    'wind': ['generation_Wind Onshore_Actual Aggregated', 'generation_Wind Offshore_Actual Aggregated'],
    'solar': ['generation_Solar_Actual Aggregated'],
    'hydro': ['generation_Hydro Run-of-river and poundage_Actual Aggregated',
              'generation_Hydro Water Reservoir_Actual Aggregated', 'generation_Hydro Pumped Storage_Actual Aggregated'],
    'fossil': [f'generation_Fossil {fuel}_Actual Aggregated' for fuel in
               ['Brown coal/Lignite', 'Coal-derived gas', 'Gas', 'Hard coal', 'Oil']],
    'nuclear': ['generation_Nuclear_Actual Aggregated'],
    'imports': ['generation_import_Import_sum'],
}
FEATURES = ['lag_15min', 'lag_1hour', 'lag_1day', 'lag_1week',
            'rolling_mean_1hour', 'rolling_mean_1day', 'rolling_std_1day',
            'hour', 'minute', 'day_of_week', 'month', 'day_of_year', 'is_weekend']
LAGS = {'lag_15min': 1, 'lag_1hour': 4, 'lag_1day': 96, 'lag_1week': 672}


def read_raw(path=None):
    path = Path(path or ROOT / 'data/power_consumption_germany.csv')
    frame = pd.read_csv(path)
    frame = frame.rename(columns={'Unnamed: 0': 'timestamp'})
    frame['timestamp'] = pd.to_datetime(frame.timestamp, utc=True)
    if frame.timestamp.duplicated().any():
        raise ValueError('Duplicate timestamps require review, not silent aggregation.')
    frame = frame.set_index('timestamp').sort_index()
    if ((frame.index.minute % 15 != 0) | (frame.index.second != 0)).any():
        raise ValueError('Non-quarter-hour source timestamp')
    return frame.reindex(pd.date_range(frame.index.min(), frame.index.max(), freq='15min'))


def target_series(raw, key):
    # Missing any component means missing total; never silently assume zero.
    values = raw[SOURCES[key]].apply(pd.to_numeric, errors='coerce')
    result = values.sum(axis=1, min_count=len(SOURCES[key])).where(
        values.notna().all(axis=1) & values.ge(0).all(axis=1)).rename('value')
    # Known corrupt source reading, already investigated in the original notebook.
    # Exclude rather than interpolate using a future observation.
    bad_time = pd.Timestamp('2026-06-25 16:30:00',tz='UTC')
    if key == 'load' and bad_time in result.index and result.loc[bad_time] > 1_000_000:
        result.loc[bad_time] = np.nan
    return result


def feature_frame(series):
    x = pd.DataFrame({name: series.shift(n) for name, n in LAGS.items()})
    prior = series.shift(1)
    x['rolling_mean_1hour'] = prior.rolling(4, min_periods=4).mean()
    x['rolling_mean_1day'] = prior.rolling(96, min_periods=96).mean()
    x['rolling_std_1day'] = prior.rolling(96, min_periods=96).std()
    local = series.index.tz_convert('Europe/Berlin')
    for name, vals in [('hour', local.hour), ('minute', local.minute),
                       ('day_of_week', local.dayofweek), ('month', local.month),
                       ('day_of_year', local.dayofyear), ('is_weekend', (local.dayofweek >= 5).astype(int))]:
        x[name] = vals
    return x[FEATURES]


def feature_row(ts, values, recent):
    local = ts.tz_convert('Europe/Berlin')
    x = {name: values.get(ts - pd.Timedelta(minutes=15*n), np.nan) for name,n in LAGS.items()}
    recent = np.asarray(recent, dtype=float)
    x.update(rolling_mean_1hour=recent[-4:].mean(), rolling_mean_1day=recent[-96:].mean(),
             rolling_std_1day=recent[-96:].std(ddof=1), hour=local.hour, minute=local.minute,
             day_of_week=local.dayofweek, month=local.month, day_of_year=local.dayofyear,
             is_weekend=int(local.dayofweek >= 5))
    return pd.DataFrame([x], columns=FEATURES)


def predict(bundle, x):
    kind = bundle['kind']
    if kind == 'persistence':
        result = x.lag_15min.to_numpy()
    elif kind == 'seasonal':
        result = x.lag_1day.to_numpy()
    else:
        model = bundle['estimator']
        if kind in ('direct', 'delta'):
            result = model.get_booster().inplace_predict(x.to_numpy(dtype=np.float32))
        else:
            result = model.predict(x)
        if kind == 'delta':
            result = result + x.lag_15min.to_numpy()
    return np.maximum(0, np.asarray(result, dtype=float))


def recursive(bundle, series, first, steps):
    from collections import deque
    # Exclude every observation at or after the first prediction time.
    history = series.loc[:first-pd.Timedelta(minutes=15)]
    needed = history.reindex(pd.date_range(first-pd.Timedelta(days=7), periods=672, freq='15min'))
    if needed.isna().any():
        raise ValueError('A complete observed week is required at the forecast origin.')
    values = needed.to_dict()
    recent = deque(needed.iloc[-96:].to_numpy(), maxlen=96)
    rows = []
    for ts in pd.date_range(first, periods=steps, freq='15min'):
        row = feature_row(ts, values, recent)
        pred = float(predict(bundle, row)[0])
        values[ts] = pred
        recent.append(pred)
        rows.append({'timestamp': ts.isoformat(), 'predicted': pred})
    return rows


def metrics(actual, predicted):
    return dict(mae=float(mean_absolute_error(actual, predicted)),
                rmse=float(np.sqrt(mean_squared_error(actual, predicted))))


def permutation_explanation(bundle, validation):
    """Validation-only diagnostic, including the delta reconstruction transform."""
    sample = validation.sample(min(1000,len(validation)),random_state=42)
    x=sample[FEATURES].copy(); y=sample.value
    baseline=metrics(y,predict(bundle,x))['mae']
    rng=np.random.default_rng(42)
    increases=[]
    for feature in FEATURES:
        errors=[]
        for repeat in range(3):
            changed=x.copy()
            changed[feature]=rng.permutation(changed[feature].to_numpy())
            errors.append(metrics(y,predict(bundle,changed))['mae']-baseline)
        increases.append(float(np.mean(errors)))
    total=sum(max(0,v) for v in increases)
    return sorted([dict(feature=f,importance=max(0,v)/total if total else 0.,delta_mae_mw=v)
                   for f,v in zip(FEATURES,increases)],key=lambda r:-r['importance'])


def train_target(raw, key, root=ROOT):
    series = target_series(raw, key)
    x_all = feature_frame(series)
    # Require contiguous observed week. Reindexing prevents lags crossing missing intervals.
    valid_week = series.shift(1).rolling(672, min_periods=672).count().eq(672)
    table = x_all.join(series).loc[valid_week].dropna()
    if len(table) < 3000:
        raise ValueError(f'{key}: insufficient complete observations')
    n = len(table); a = int(.70*n); b = int(.85*n)
    slices = {'train': table.iloc[:a], 'validation': table.iloc[a:b], 'test': table.iloc[b:]}
    train, val, test = [slices[s] for s in ['train','validation','test']]
    def xgb():
        return XGBRegressor(n_estimators=180, max_depth=5, learning_rate=.06,
                            subsample=.85, colsample_bytree=.9, tree_method='hist',
                            objective='reg:squarederror', random_state=42, n_jobs=4)
    candidates = {
        'persistence': ('15-minute Persistence', None),
        'seasonal': ('Daily Seasonal Persistence', None),
        'ridge': ('Ridge Regression', make_pipeline(StandardScaler(), Ridge(alpha=10))),
        'extra_trees': ('Extra Trees', ExtraTreesRegressor(n_estimators=48, max_depth=16,
                         min_samples_leaf=5, max_features=.8, random_state=42, n_jobs=2)),
        'direct': ('Direct XGBoost', xgb()),
        'delta': ('Delta XGBoost', xgb()),
    }
    bundles = {}; comparison = []
    for kind, (label, estimator) in candidates.items():
        print(f'{key}: {label}', flush=True)
        if estimator is not None:
            y = train.value - train.lag_15min if kind == 'delta' else train.value
            estimator.fit(train[FEATURES], y)
        bundle = dict(kind=kind, estimator=estimator, features=FEATURES, prediction_unit='MW',
                      output_transform='add_lag_15min' if kind == 'delta' else 'identity')
        bundles[kind] = bundle
        row = dict(kind=kind, model=label)
        for split in ['validation','test']:
            part = slices[split]
            row.update({f'{split}_{k}': v for k,v in metrics(part.value, predict(bundle,part[FEATURES])).items()})
        comparison.append(row)
        joblib.dump(bundle, root / f'backend/models/{key}_{kind}.joblib', compress=3)
    best = min(comparison, key=lambda r:r['validation_mae'])
    chosen = bundles[best['kind']]
    joblib.dump(chosen, root / f'backend/models/{key}_selected.joblib', compress=3)
    baseline = comparison[0]['test_mae']
    for row in comparison:
        row['improvement_pct'] = 100*(baseline-row['test_mae'])/baseline if baseline else None
    importance = permutation_explanation(chosen,val)
    latest = series.last_valid_index()
    complete = series.notna().astype(int)
    ends = complete.rolling(673, min_periods=673).sum().eq(673)
    if not ends.any():
        raise ValueError('No contiguous deployment history')
    history_end = ends[ends].index[-1]
    history = series.loc[history_end-pd.Timedelta(days=14):history_end]
    # Keep the last contiguous block only.
    missing = history[history.isna()]
    if len(missing): history = history.loc[missing.index[-1]+pd.Timedelta(minutes=15):]
    history.rename_axis('timestamp').reset_index().to_csv(root / f'backend/data/{key}_history.csv',index=False)
    predictions = pd.DataFrame({'timestamp': test.index, 'actual':test.value.to_numpy()})
    for kind,bundle in bundles.items(): predictions[kind] = predict(bundle,test[FEATURES])
    predictions.to_csv(root / f'backend/data/{key}_test_predictions.csv',index=False)
    # Small, explicitly labeled recursive backtest on up to three complete test days.
    recursive_scores = []
    for start in np.linspace(0, max(0,len(test)-96), 3, dtype=int):
        first = test.index[start]
        actual = series.reindex(pd.date_range(first, periods=96, freq='15min'))
        if actual.isna().any(): continue
        for kind in [best['kind'], 'persistence']:
            rows = recursive(bundles[kind],series,first,96)
            recursive_scores.append(dict(origin=first.isoformat(),kind=kind,steps=96,
                                    **metrics(actual,[r['predicted'] for r in rows])))
    info = dict(title=TITLES[key],unit='MW',model=best['model'],selected_kind=best['kind'],
                test_mae=best['test_mae'],test_rmse=best['test_rmse'],
                persistence_mae=comparison[0]['test_mae'],persistence_rmse=comparison[0]['test_rmse'],
                improvement_pct=best['improvement_pct'],latest_observed=history_end.isoformat(),
                first_prediction_min=(history.index.min()+pd.Timedelta(days=7)).isoformat(),
                first_prediction_max=(history_end+pd.Timedelta(minutes=15)).isoformat(),
                feature_importance=importance, comparison=comparison, recursive_backtest=recursive_scores,
                source_columns=SOURCES[key],observed_count=int(series.notna().sum()),
                missing_pct=float(100*series.isna().mean()),eligible_count=n,
                first_observed=series.first_valid_index().isoformat(),last_observed=latest.isoformat(),
                splits={s:dict(rows=len(p),start=p.index.min().isoformat(),end=p.index.max().isoformat())
                        for s,p in slices.items()},
                limitation='Historical only; no imputation after the last reported nuclear observation.' if key=='nuclear'
                else 'Coverage requires every source component; no missing target values are imputed.')
    return info


def train_all(path=None):
    for folder in ['backend/models','backend/data']: (ROOT/folder).mkdir(parents=True,exist_ok=True)
    raw = read_raw(path)
    metadata = dict(version='GridAI 3.0',features=FEATURES,targets={},
                    evaluation='One-step walk-forward with observed prior values; 70/15/15 chronological per target.',
                    selection='Lowest validation MAE. Test scores never choose the deployed model.',
                    environment=dict(python=platform.python_version(),pandas=pd.__version__,numpy=np.__version__,
                                     sklearn=sklearn.__version__,xgboost=xgboost.__version__))
    metadata['quality_exclusions'] = [dict(target='load',timestamp='2026-06-25T16:30:00+00:00',
        original_value_mw=4315702.57803,
        action='Known corrupt reading excluded if above 1,000,000 MW; affected feature windows excluded; no interpolation.')]
    source = Path(path or ROOT/'data/power_consumption_germany.csv')
    metadata['source_sha256'] = hashlib.file_digest(source.open('rb'),'sha256').hexdigest()
    for key in SOURCES:
        metadata['targets'][key] = train_target(raw,key)
        (ROOT/'backend/data/metadata.json').write_text(json.dumps(metadata,indent=2,allow_nan=False),encoding='utf-8')
    pd.DataFrame([dict(target=k,**r) for k,d in metadata['targets'].items() for r in d['comparison']]).to_csv(
        ROOT/'backend/data/model_comparison.csv',index=False)
    from ml.solar_long_range import train as train_solar_long_range
    metadata['targets']['solar']['long_range'] = train_solar_long_range()
    return metadata


if __name__ == '__main__':
    train_all()
