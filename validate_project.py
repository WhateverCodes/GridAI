"""Run meaningful integration checks against the delivered artifacts."""
from pathlib import Path
import json
import joblib
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from ml.pipeline import (ROOT,FEATURES,SOURCES,read_raw,target_series,feature_frame,
                         feature_row,predict,recursive,metrics)
from backend.app import app,HISTORY,MODELS_OBJ


def main():
    meta=json.loads((ROOT/'backend/data/metadata.json').read_text())
    raw=read_raw()
    client=TestClient(app)
    assert client.get('/').status_code == 200
    assert client.get('/api/health').json()['status']=='ok'
    assert set(client.get('/api/summary').json()['targets'])==set(SOURCES)
    report=[]
    for key,d in meta['targets'].items():
        print('Checking',key,flush=True)
        series=target_series(raw,key)
        first=pd.Timestamp(d['first_prediction_max'])
        observed=HISTORY[key]
        bundle=MODELS_OBJ[key]
        # Vectorized training features and online row features must agree.
        batch=feature_frame(observed.reindex(pd.date_range(observed.index.min(),first,freq='15min'))).loc[[first]]
        online=feature_row(first,observed.to_dict(),observed.iloc[-96:])
        np.testing.assert_allclose(batch.to_numpy(),online.to_numpy(),rtol=1e-10,atol=1e-7)
        assert list(online)==FEATURES==bundle['features']
        # Recompute every exported test score from the CSV, not rounded display values.
        saved=pd.read_csv(ROOT/f'backend/data/{key}_test_predictions.csv')
        for candidate in d['comparison']:
            score=metrics(saved.actual,saved[candidate['kind']])
            np.testing.assert_allclose([score['mae'],score['rmse']],
                [candidate['test_mae'],candidate['test_rmse']],rtol=1e-10)
        assert d['selected_kind']==min(d['comparison'],key=lambda r:r['validation_mae'])['kind']
        # Independently reload model and reproduce a sample of the exported predictions.
        ts=pd.to_datetime(saved.timestamp.iloc[:12],utc=True)
        x=feature_frame(series).loc[ts]
        for kind in ['direct','delta',d['selected_kind']]:
            loaded=joblib.load(ROOT/f'backend/models/{key}_{kind}.joblib')
            np.testing.assert_allclose(predict(loaded,x),saved[kind].iloc[:12],rtol=1e-5,atol=.02)
        # Delta bundles always reconstruct absolute MW before clipping.
        delta=joblib.load(ROOT/f'backend/models/{key}_delta.joblib')
        raw_delta=delta['estimator'].predict(x)
        np.testing.assert_allclose(predict(delta,x),np.maximum(0,raw_delta+x.lag_15min),atol=.02)
        # Multi-step request exercises all weekly lag lookups.
        response=client.get(f'/api/forecast/{key}',params={'origin':first.isoformat(),'steps':672})
        assert response.status_code==200,response.text
        values=np.array([r['predicted'] for r in response.json()['rows']])
        assert len(values)==672 and np.isfinite(values).all() and (values>=0).all()
        # Poison all future observed data: historical recursive output must not change.
        origin=pd.Timestamp(d['splits']['test']['start'])
        poisoned=series.copy(); poisoned.loc[origin:]=1e12
        before=recursive(bundle,series,origin,8)
        after=recursive(bundle,poisoned,origin,8)
        assert [r['timestamp'] for r in before]==[r['timestamp'] for r in after]
        np.testing.assert_allclose([r['predicted'] for r in before],
                                   [r['predicted'] for r in after],rtol=1e-12,atol=1e-8)
        assert client.get(f'/api/forecast/{key}',params={'origin':(first+pd.Timedelta(minutes=15)).isoformat()}).status_code==200
        report.append(dict(target=key,status='passed',week_steps=len(values),model=d['model']))
    for invalid in ['nonsense','2023-04-01T00:00:00','2023-04-01T00:01:00Z','NaT']:
        assert client.get('/api/forecast/load',params={'origin':invalid}).status_code==400
    assert client.get('/api/forecast/unknown',params={'origin':'2023-01-01T00:00Z'}).status_code==404
    for steps in [0,673]:
        assert client.get('/api/forecast/load',params={'origin':meta['targets']['load']['first_prediction_max'],'steps':steps}).status_code==422
    (ROOT/'backend/data/validation_report.json').write_text(json.dumps(report,indent=2))
    print(pd.DataFrame(report).to_string(index=False))
    print('PASS: scores, artifact selection, transforms, feature parity, 672-step forecasts, causal recursion and API errors.')


if __name__=='__main__': main()
