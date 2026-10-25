"""Track B: review-gated feed ingestion. No marketplace crawling or Affiliate API."""
import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'shopee_tw' / 'collector'))
from normalize import FIELDS


def run(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    review = json.loads((Path(__file__).parent / 'sources.json').read_text())
    # There is deliberately no remote fetch implementation while no source has
    # passed review. Changing a JSON status must never silently enable networking.
    if any(s['status'] == 'approved' for s in review['sources']):
        raise ValueError('Approved source requires a source-specific adapter and permission tests before activation')
    with (out / 'observations.csv').open('w', encoding='utf-8-sig', newline='') as f:
        csv.DictWriter(f, fieldnames=FIELDS).writeheader()
    subprocess.run([sys.executable, str(ROOT/'shopee_tw/collector/normalize.py'),
                    '--input', str(out/'observations.csv'), '--out', str(out)], check=True)
    legacy = ROOT/'shopee_tw/input/historical_sellers_20261025.csv'
    with legacy.open(encoding='utf-8-sig', newline='') as f:
        seeds = list(csv.DictReader(f))
    # Retain incomplete legacy evidence separately; never mark it freshly observed.
    with (out/'unverified_historical_seeds.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS+['verification_status'])
        w.writeheader()
        w.writerows(dict(r, verification_status='unverified_historical_missing_provenance') for r in seeds)
    report = json.loads((out/'coverage_report.json').read_text())
    report.update(track='B', brand='JUNGSAEMMOOL',
        collection_status='blocked_no_verified_free_commercial_source',
        new_verified_sellers=0, new_verified_listings=0,
        historical_seed_rows=len(seeds), historical_seeds_in_verified_data=False,
        source_review_date=review['reviewed_at'], source_decisions=review['sources'],
        missing_fields=FIELDS, marketplace_coverage='unknown',
        collected_at=None, executed_at=datetime.now(timezone.utc).isoformat(),
        note='Infrastructure execution only; no marketplace data collected. Historical seed provenance and observation times are missing.',
        input_sha256=hashlib.sha256(legacy.read_bytes()).hexdigest())
    (out/'coverage_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (out/'source_review.json').write_text(json.dumps(review, ensure_ascii=False, indent=2))
    (out/'RUN_STATUS.md').write_text('# TRACK B\n\nBLOCKED: no verified free commercial source.\n\n'
        f'New sellers: 0; new listings: 0; unverified historical seed rows: {len(seeds)}.\n'
        'Workflow success means validation completed, not collection success.\n')
    print(report['collection_status'])
    return report

if __name__ == '__main__':
    run(sys.argv[1] if len(sys.argv)>1 else ROOT/'shopee_tw/output/track_b')
