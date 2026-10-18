"""Verify direct Solar's selection, independent-date output and exported scores."""
import json
import joblib
import numpy as np
import pandas as pd
from backend.app import forecast
from ml.pipeline import ROOT,read_raw,target_series,metrics
from ml.solar_long_range import calibration,predict_calendar

def main():
    report=json.loads((ROOT/'backend/data/solar_long_range_report.json').read_text())
    assert report['selected_kind']==min(report['comparison'],key=lambda x:x['validation_mae'])['kind']
    saved=pd.read_csv(ROOT/'backend/data/solar_long_range_test_predictions.csv')
    for row in report['comparison']:
        result=metrics(saved.actual,saved[row['kind']])
        np.testing.assert_allclose([result['mae'],result['rmse']],
                                  [row['test_mae'],row['test_rmse']],rtol=1e-10)
    bundle=joblib.load(ROOT/'backend/models/solar_long_range.joblib')
    series=target_series(read_raw(),'solar')
    dates=pd.to_datetime(saved.timestamp.iloc[:192],utc=True)
    scale=calibration(bundle,series,dates[0]-pd.Timedelta(minutes=15))
    np.testing.assert_allclose(predict_calendar(bundle,dates,scale),
                               saved[report['selected_kind']].iloc[:192],rtol=1e-10,atol=1e-7)
    response=forecast('solar','2026-10-20T03:30:00+05:30',672)
    assert response['forecast_method']=='direct_calendar'
    assert response['test_mae']==report['test_mae']
    expected=pd.date_range('2026-10-19T22:00:00Z',periods=672,freq='15min')
    assert list(pd.to_datetime([r['timestamp'] for r in response['rows']],utc=True))==list(expected)
    predictions=np.array([r['predicted'] for r in response['rows']])
    assert np.isfinite(predictions).all() and (predictions>=0).all()
    assert predictions.max()<=report['calibration']['ceiling']
    assert predictions[0] < report['calibration']['ceiling']*.001
    assert predictions.max()>predictions[0]+1000
    # Extending the horizon cannot change a prior direct prediction.
    one=forecast('solar','2026-10-20T03:30:00+05:30',1)
    np.testing.assert_allclose(one['rows'][0]['predicted'],predictions[0])
    distant=forecast('solar','2035-10-20T03:30:00+05:30',1)
    assert distant['rows'][0]['timestamp']=='2035-10-19T22:00:00+00:00'
    assert 0<=distant['rows'][0]['predicted']<=report['calibration']['ceiling']
    nuclear=forecast('nuclear','2035-10-20T03:30:00+05:30',1)
    assert nuclear['rows'][0]['timestamp']==distant['rows'][0]['timestamp']
    print('PASS: validation selection, exported errors, pre-test calibration, requested dates, bounded Solar, near-zero night, horizon independence and 2035 origins.')

if __name__=='__main__':main()
