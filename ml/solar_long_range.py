"""Direct calendar forecasts for Solar: no recursive delta accumulation."""
from pathlib import Path
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor
from xgboost import XGBRegressor
from ml.pipeline import ROOT,read_raw,target_series,metrics

def calendar(index):
    local=pd.DatetimeIndex(index).tz_convert('Europe/Berlin')
    angle=2*np.pi*(local.dayofyear-1)/365.25
    return pd.DataFrame(dict(hour=local.hour,minute=local.minute,month=local.month,
        sin_day_of_year=np.sin(angle),cos_day_of_year=np.cos(angle),year=local.year),index=index)

def raw_predict(bundle,index):
    features=calendar(index)
    if bundle['kind']=='profile':
        result=np.array([bundle['profile'].get((int(m),int(h)*4+int(n)//15),0.)
                         for m,h,n in zip(features.month,features.hour,features.minute)])
    else:
        result=bundle['estimator'].predict(features)
    # Only training month/quarter bins with at least 99.5% exact zeros are masked.
    slots=features.hour*4+features.minute//15
    night=np.array([(int(m),int(q)) in bundle['night_bins'] for m,q in zip(features.month,slots)])
    return np.where(night,0,np.maximum(0,np.asarray(result,dtype=float)))

def calibration(bundle,observed,cutoff):
    past=observed.loc[cutoff-pd.Timedelta(days=28):cutoff].dropna()
    if len(past)<96: return dict(scale=1.,ceiling=float(observed.loc[:cutoff].max()))
    estimates=raw_predict(bundle,past.index)
    scale=float(past.mean()/max(1.,float(estimates.mean())))
    return dict(scale=scale,ceiling=float(observed.loc[:cutoff].max()))

def predict_calendar(bundle,index,calibration_state):
    return np.clip(raw_predict(bundle,index)*calibration_state['scale'],0,calibration_state['ceiling'])

def train():
    meta=json.loads((ROOT/'backend/data/metadata.json').read_text())
    series=target_series(read_raw(),'solar')
    eligible=series.loc[series.shift(1).rolling(672,min_periods=672).count().eq(672)].dropna()
    splits=meta['targets']['solar']['splits']
    parts={k:eligible.loc[v['start']:v['end']] for k,v in splits.items()}
    training=parts['train']; features=calendar(training.index)
    grouped=pd.DataFrame(dict(month=features.month,slot=features.hour*4+features.minute//15,
                              value=training.to_numpy()))
    zero_rate=grouped.assign(zero=grouped.value.eq(0)).groupby(['month','slot']).zero.mean()
    night_bins=set(zero_rate[zero_rate>=.995].index)
    profile=grouped.groupby(['month','slot']).value.mean().to_dict()
    candidates={
        'profile':('Calendar Seasonal Profile',None),
        'extra_trees':('Calendar Extra Trees',ExtraTreesRegressor(n_estimators=64,max_depth=16,
                       min_samples_leaf=20,random_state=42,n_jobs=2)),
        'xgboost':('Calendar XGBoost',XGBRegressor(n_estimators=240,max_depth=6,learning_rate=.05,
                    subsample=.85,colsample_bytree=.9,tree_method='hist',n_jobs=4,random_state=42)),
    }
    comparisons=[];bundles={};predictions={}
    for kind,(name,estimator) in candidates.items():
        print('Training',name,flush=True)
        if estimator is not None: estimator.fit(features,training.to_numpy())
        bundle=dict(kind=kind,estimator=estimator,night_bins=night_bins,profile=profile,
                    name=name+' (direct long-range Solar)')
        row=dict(kind=kind,model=name)
        for split in ['validation','test']:
            actual=parts[split]
            cutoff=actual.index[0]-pd.Timedelta(minutes=15)
            scale=calibration(bundle,series,cutoff)
            predicted=predict_calendar(bundle,actual.index,scale)
            row.update({f'{split}_{k}':v for k,v in metrics(actual,predicted).items()})
            if split=='test': predictions[kind]=predicted
        comparisons.append(row);bundles[kind]=bundle
    best=min(comparisons,key=lambda row:row['validation_mae'])
    chosen=bundles[best['kind']]
    # Deployment calibration uses observations at/before the packaged source cutoff only.
    cutoff=pd.Timestamp(meta['targets']['solar']['latest_observed'])
    chosen['calibration']=calibration(chosen,series,cutoff)
    joblib.dump(chosen,ROOT/'backend/models/solar_long_range.joblib',compress=3)
    report=dict(model=chosen['name'],selected_kind=best['kind'],test_mae=best['test_mae'],
        test_rmse=best['test_rmse'],comparison=comparisons,source_latest=cutoff.isoformat(),
        calibration=chosen['calibration'],
        use_when='First prediction more than one day after source data, or requested horizon longer than one day.',
        evaluation='Direct calendar predictions over the complete held-out test window, with calibration fixed before that window. Model selected on validation MAE.',
        limitation='Calendar-average Solar pattern without future weather. Scale uses preceding 28 observed days; output is bounded by maximum observed Solar at source cutoff. Future capacity growth is not extrapolated.',
        splits=splits)
    meta['targets']['solar']['long_range']=report
    (ROOT/'backend/data/metadata.json').write_text(json.dumps(meta,indent=2,allow_nan=False),encoding='utf-8')
    pd.DataFrame(comparisons).to_csv(ROOT/'backend/data/solar_long_range_comparison.csv',index=False)
    out=pd.DataFrame(dict(timestamp=parts['test'].index,actual=parts['test'].to_numpy(),**predictions))
    out.to_csv(ROOT/'backend/data/solar_long_range_test_predictions.csv',index=False)
    (ROOT/'backend/data/solar_long_range_report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2),flush=True)
    return report

if __name__=='__main__': train()
