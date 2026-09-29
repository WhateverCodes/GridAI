from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import json
import joblib
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
DATA = BASE / 'data'
MODELS = BASE / 'models'

meta = json.loads((DATA / 'metadata.json').read_text(encoding='utf-8'))
TARGETS = list(meta['targets'])
MODELS_OBJ = {k: joblib.load(MODELS / f'{k}_xgboost.pkl') for k in TARGETS}
HISTORY = {}
for k in TARGETS:
    h = pd.read_csv(DATA / f'{k}_history.csv', parse_dates=['timestamp'])
    h['timestamp'] = pd.to_datetime(h['timestamp'], utc=True)
    HISTORY[k] = h.set_index('timestamp')['value'].astype(float).sort_index()

app = FastAPI(title='GridAI Forecast API', version='2.2')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

QUARTER_MINUTES = {0, 15, 30, 45}


def features(ts: pd.Timestamp, hist: pd.Series):
    def val(delta):
        t = ts - delta
        return float(hist.loc[t]) if t in hist.index else np.nan

    prior = hist.loc[:ts - pd.Timedelta(minutes=15)]
    vals = {
        'lag_15min': val(pd.Timedelta(minutes=15)),
        'lag_1hour': val(pd.Timedelta(hours=1)),
        'lag_1day': val(pd.Timedelta(days=1)),
        'lag_1week': val(pd.Timedelta(days=7)),
        'rolling_mean_1hour': float(prior.tail(4).mean()),
        'rolling_mean_1day': float(prior.tail(96).mean()),
        'rolling_std_1day': float(prior.tail(96).std()),
    }
    lt = ts.tz_convert('Europe/Berlin')
    vals.update({
        'hour': lt.hour,
        'minute': lt.minute,
        'day_of_week': lt.dayofweek,
        'month': lt.month,
        'day_of_year': lt.dayofyear,
        'is_weekend': int(lt.dayofweek >= 5),
    })
    return vals


def parse_timestamp(value: str):
    requested = pd.Timestamp(value)
    if requested.tzinfo is None:
        raise HTTPException(400, 'Forecast time must include the browser local timezone offset.')
    local = requested
    utc = requested.tz_convert('UTC')
    if utc.minute not in QUARTER_MINUTES or utc.second != 0 or utc.microsecond != 0:
        raise HTTPException(400, 'Forecast time must be exactly on :00, :15, :30 or :45.')
    return local, utc


def _feature_row(ts: pd.Timestamp, values: dict, recent_values):
    def get(delta):
        return values.get(ts - delta)

    last_4 = list(recent_values)[-4:]
    last_96 = list(recent_values)[-96:]
    if len(last_4) < 4 or len(last_96) < 96:
        raise HTTPException(500, 'Insufficient history to construct forecast features.')

    mean_1h = float(np.mean(last_4))
    mean_1d = float(np.mean(last_96))
    std_1d = float(np.std(last_96, ddof=1))

    lt = ts.tz_convert('Europe/Berlin')
    row = {
        'lag_15min': get(pd.Timedelta(minutes=15)),
        'lag_1hour': get(pd.Timedelta(hours=1)),
        'lag_1day': get(pd.Timedelta(days=1)),
        'lag_1week': get(pd.Timedelta(days=7)),
        'rolling_mean_1hour': mean_1h,
        'rolling_mean_1day': mean_1d,
        'rolling_std_1day': std_1d,
        'hour': lt.hour,
        'minute': lt.minute,
        'day_of_week': lt.dayofweek,
        'month': lt.month,
        'day_of_year': lt.dayofyear,
        'is_weekend': int(lt.dayofweek >= 5),
    }
    if any(v is None or pd.isna(v) for v in row.values()):
        raise HTTPException(500, 'Insufficient history to construct forecast features.')
    return row


def _model_predict(model, row):
    # Use the booster directly for low-overhead single-step recursive inference.
    values = np.asarray([[row[name] for name in meta['features']]], dtype=np.float32)
    pred = model.get_booster().inplace_predict(values)[0]
    return max(0.0, float(pred))


def forecast(key: str, first_prediction: str, steps: int):
    if key not in TARGETS:
        raise HTTPException(404, 'Unknown target')

    requested_local, target_utc = parse_timestamp(first_prediction)
    base = HISTORY[key]
    latest = base.index.max()
    earliest = base.index.min() + pd.Timedelta(days=7)
    if target_utc < earliest:
        raise HTTPException(400, f'Forecast timestamp must be on or after {earliest.isoformat()} (UTC).')

    model = MODELS_OBJ[key]

    # For historical timestamps, use the real observations directly. For future
    # timestamps, recursively bridge from the latest real observation. The loop
    # uses direct timestamp lookups and rolling buffers rather than repeatedly
    # slicing a growing pandas Series, which keeps long-date forecasts fast.
    values = {pd.Timestamp(ts): float(v) for ts, v in base.items()}
    origin = target_utc - pd.Timedelta(minutes=15)

    if origin > latest:
        seed_start = latest - pd.Timedelta(minutes=95 * 15)
        seed = [values[t] for t in pd.date_range(seed_start, latest, freq='15min') if t in values]
        if len(seed) < 96:
            raise HTTPException(500, 'Insufficient contiguous history for rolling features.')
        from collections import deque
        recent = deque(seed, maxlen=96)
        cur = latest
        while cur < origin:
            nxt = cur + pd.Timedelta(minutes=15)
            row = _feature_row(nxt, values, recent)
            pred = _model_predict(model, row)
            values[nxt] = pred
            recent.append(pred)
            cur = nxt
    else:
        from collections import deque
        seed_end = origin
        seed_start = seed_end - pd.Timedelta(minutes=95 * 15)
        seed = [values[t] for t in pd.date_range(seed_start, seed_end, freq='15min') if t in values]
        if len(seed) < 96:
            raise HTTPException(500, 'Insufficient contiguous history for rolling features at the requested time.')
        recent = deque(seed, maxlen=96)

    rows = []
    cur = target_utc
    for _ in range(steps):
        row = _feature_row(cur, values, recent)
        pred = _model_predict(model, row)
        values[cur] = pred
        recent.append(pred)
        rows.append({'timestamp': cur.isoformat(), 'predicted': pred})
        cur += pd.Timedelta(minutes=15)

    model_origin = target_utc - pd.Timedelta(minutes=15)
    return requested_local, target_utc, model_origin, rows


@app.get('/')
def root():
    return {'project': 'GridAI', 'status': 'online', 'version': '2.2'}


@app.get('/api/health')
def health():
    return {'status': 'ok', 'latest': {k: meta['targets'][k]['latest_observed'] for k in TARGETS}}


@app.get('/api/summary')
def summary():
    return {
        'targets': meta['targets'],
        'latest_available': max(meta['targets'][k]['latest_observed'] for k in TARGETS),
    }


@app.get('/api/forecast/{target}')
def get_forecast(
    target: str,
    origin: str = Query(..., description='First prediction timestamp. Offset-aware ISO timestamp on a quarter hour.'),
    steps: int = Query(1, ge=1, le=672),
):
    requested_local, first_prediction, model_origin, rows = forecast(target, origin, steps)
    return {
        'target': target,
        'requested_prediction': requested_local.isoformat(),
        'first_prediction': first_prediction.isoformat(),
        'model_origin': model_origin.isoformat(),
        'horizon_steps': steps,
        'horizon_minutes': steps * 15,
        'unit': 'MW',
        'model': meta['targets'][target].get('model', 'Forecast-safe XGBoost'),
        'rows': rows,
    }
