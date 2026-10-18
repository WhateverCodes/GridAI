"""Check current-quarter extrapolation, cache reuse and rollover for all targets."""
import pandas as pd
from backend.app import TARGETS, snapshot, SNAPSHOT_STATE

def main():
    now = pd.Timestamp.now(tz='UTC').floor('15min')
    for key in TARGETS:
        previous = snapshot(key,(now-pd.Timedelta(minutes=15)).isoformat())
        current = snapshot(key,now.isoformat())
        assert previous['rows'][0]['timestamp'] == (now-pd.Timedelta(minutes=15)).isoformat()
        assert current['rows'][0]['timestamp'] == now.isoformat()
        assert snapshot(key,now.isoformat()) == current
        if current['forecast_method'] != 'direct_calendar':
            assert SNAPSHOT_STATE[key]['history'].index[-1] == now
            assert len(SNAPSHOT_STATE[key]['history']) == 672
        assert current['rows'][0]['predicted'] >= 0
        assert current['source_latest'] < current['rows'][0]['timestamp']
        print(key, 'PASS: current quarter, rollover, cache and source disclosure',flush=True)

if __name__ == '__main__': main()
