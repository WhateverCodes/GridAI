"""GridAI API: shared preprocessing and explicit prediction transforms."""
from pathlib import Path
import json
import joblib
import pandas as pd
from threading import RLock
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from ml.pipeline import recursive
from ml.solar_long_range import predict_calendar

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
meta = json.loads((BASE/'data/metadata.json').read_text(encoding='utf-8'))
TARGETS = list(meta['targets'])
MODELS_OBJ = {k:joblib.load(BASE/f'models/{k}_selected.joblib') for k in TARGETS}
SOLAR_LONG_RANGE = joblib.load(BASE/'models/solar_long_range.joblib') if (BASE/'models/solar_long_range.joblib').exists() else None
for bundle in MODELS_OBJ.values():
    if bundle['kind'] == 'extra_trees':
        bundle['estimator'].n_jobs = 1  # Avoid thread startup for each recursive row.
SNAPSHOT_STATE = {}
EXTENSION_STATE = {}
SNAPSHOT_LOCK = RLock()
HISTORY = {}
for k in TARGETS:
    frame = pd.read_csv(BASE/f'data/{k}_history.csv')
    HISTORY[k] = pd.Series(frame.value.to_numpy(),index=pd.to_datetime(frame.timestamp,utc=True))
app = FastAPI(title='GridAI Forecast API',version='3.0')
app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_methods=['GET'],allow_headers=['*'])

@app.get('/api/health')
def health():
    return dict(status='ok',targets=TARGETS)

@app.get('/api/summary')
def summary():
    return dict(targets=meta['targets'],evaluation=meta['evaluation'],selection=meta['selection'],
                latest_available=max(d['latest_observed'] for d in meta['targets'].values()))

def parse_time(value):
    try: ts = pd.Timestamp(value)
    except (ValueError,TypeError): raise HTTPException(400,'Enter a valid date and time.')
    if pd.isna(ts) or ts.tzinfo is None: raise HTTPException(400,'Include a timezone offset.')
    ts = ts.tz_convert('UTC')
    if ts != ts.floor('15min'): raise HTTPException(400,'Choose 00, 15, 30 or 45 minutes.')
    return ts


def history_through(target, end):
    """Bridge to any future origin. Cache only predictions, never future observations."""
    base = HISTORY[target]
    if end <= base.index[-1]:
        return base.loc[:end]
    with SNAPSHOT_LOCK:
        cached = EXTENSION_STATE.get(target)
        if cached is not None and cached.index[-1] <= end:
            base = cached
        first = base.index[-1] + pd.Timedelta(minutes=15)
        if first > end: return base
        steps = int((end-first)/pd.Timedelta(minutes=15))+1
        bundle = MODELS_OBJ[target]
        if bundle['kind'] == 'persistence':
            # Exact closed form, including arbitrarily distant historical nuclear origins.
            pred = float(base.iloc[-1])
            if steps >= 672:
                result = pd.Series(pred,index=pd.date_range(end=end,periods=672,freq='15min'))
            else:
                extra = pd.Series(pred,index=pd.date_range(first,end,freq='15min'))
                result = pd.concat([base,extra]).iloc[-672:]
        else:
            generated = recursive(bundle,base,first,steps)
            tail = generated[-672:]
            extra = pd.Series([row['predicted'] for row in tail],index=pd.to_datetime(
                [row['timestamp'] for row in tail],utc=True))
            result = pd.concat([base,extra]).iloc[-672:]
        EXTENSION_STATE[target] = result
        return result


def forecast(target,origin,steps):
    if target not in TARGETS: raise HTTPException(404,'Unknown target')
    ts = parse_time(origin)
    d = meta['targets'][target]
    if target == 'solar' and SOLAR_LONG_RANGE is not None and ts > pd.Timestamp(d['latest_observed']) and (
            ts > pd.Timestamp(d['latest_observed'])+pd.Timedelta(days=1) or steps > 96):
        times=pd.date_range(ts,periods=steps,freq='15min')
        predictions=predict_calendar(SOLAR_LONG_RANGE,times,SOLAR_LONG_RANGE['calibration'])
        report=d['long_range']
        return dict(target=target,first_prediction=ts.isoformat(),
            model_origin=(ts-pd.Timedelta(minutes=15)).isoformat(),
            horizon_steps=steps,horizon_minutes=steps*15,unit='MW',model=report['model'],
            test_mae=report['test_mae'],test_rmse=report['test_rmse'],evaluation=report['evaluation'],
            forecast_method='direct_calendar',source_latest=d['latest_observed'],
            recursively_extended=False,limitation=report['limitation'],
            rows=[dict(timestamp=t.isoformat(),predicted=float(p)) for t,p in zip(times,predictions)])
    try:
        prior = history_through(target,ts-pd.Timedelta(minutes=15))
        rows = recursive(MODELS_OBJ[target],prior,ts,steps)
    except (ValueError,IndexError) as exc:
        raise HTTPException(400,'Not enough observations before the requested time to build the required history.') from exc
    return dict(target=target,first_prediction=ts.isoformat(),model_origin=(ts-pd.Timedelta(minutes=15)).isoformat(),
                horizon_steps=steps,horizon_minutes=steps*15,unit='MW',model=d['model'],
                test_mae=d['test_mae'],test_rmse=d['test_rmse'],forecast_method='recursive',
                evaluation='15-minute one-step walk-forward evaluation; not the requested multi-step horizon.',
                source_latest=d['latest_observed'],
                recursively_extended=ts > pd.Timestamp(d['latest_observed']),
                limitation='Dates after the source data are recursively extrapolated; no live measurements are connected.',rows=rows)


@app.get('/api/forecast/{target}')
def get_forecast(target:str,origin:str=Query(...),steps:int=Query(1,ge=1,le=672)):
    return forecast(target,origin,steps)


def snapshot(target, at):
    if target not in TARGETS: raise HTTPException(404,'Unknown target')
    ts = parse_time(at)
    cached = SNAPSHOT_STATE.get(target)
    if cached is not None and cached['timestamp'] == ts:
        return cached['response']
    response = forecast(target,ts.isoformat(),1)
    response['bridge_steps'] = max(0,int((ts-pd.Timestamp(response['source_latest']))/pd.Timedelta(minutes=15)))
    if response['forecast_method']=='direct_calendar':
        SNAPSHOT_STATE[target]=dict(timestamp=ts,response=response)
    elif ts > HISTORY[target].index[-1]:
        with SNAPSHOT_LOCK:
            prior = history_through(target,ts-pd.Timedelta(minutes=15))
            result = pd.concat([prior,pd.Series(response['rows'][0]['predicted'],index=pd.DatetimeIndex([ts]))]).iloc[-672:]
            EXTENSION_STATE[target] = result
            SNAPSHOT_STATE[target]=dict(timestamp=ts,history=result,response=response)
    return response


@app.get('/api/snapshot/{target}')
def get_snapshot(target:str,at:str=Query(...)):
    return snapshot(target,at)

# Serve only dashboard assets, never the model or raw-data directories.
@app.get('/')
def dashboard():
    from fastapi.responses import FileResponse
    return FileResponse(ROOT/'index.html')

@app.get('/script.js')
def javascript():
    from fastapi.responses import FileResponse
    return FileResponse(ROOT/'script.js',media_type='application/javascript')

@app.get('/style.css')
def stylesheet():
    from fastapi.responses import FileResponse
    return FileResponse(ROOT/'style.css',media_type='text/css')
