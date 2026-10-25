"""Check real no-source behavior without fabricating marketplace observations."""
import importlib.util
import json
import tempfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('track_b', Path(__file__).resolve().parents[1]/'track_b/run.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
with tempfile.TemporaryDirectory() as d:
    r=m.run(d)
    assert r['raw_rows']==r['unique_listing_keys']==r['unique_shop_keys']==0
    assert r['collection_status'].startswith('blocked_')
    assert r['collected_at'] is None
    assert not r['historical_seeds_in_verified_data']
    assert r['historical_seed_rows']>0
    assert not r['search_results_exhausted']
    assert json.loads((Path(d)/'source_review.json').read_text())['sources']
print('Track B no-source separation checks passed')
