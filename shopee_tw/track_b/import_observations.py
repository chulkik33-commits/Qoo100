"""Import observed browser records, keeping incomplete offline exports separate.

This command reads local evidence only. It makes no marketplace requests.
"""
import argparse
import csv
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shopee_tw" / "collector"))
from normalize import FIELDS

IDS = re.compile(r"-i\.(\d+)\.(\d+)(?:[/?#]|$)")


def read_probe(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data.get("records", [])
    coverage = data.get("coverage", {})
    # Version 0.1 recorded no row on a product-detail page. Preserve the URL
    # identifiers as an incomplete lead; no title, price or sold count is inferred.
    if not rows and coverage.get("status") in ("no_matching_cards", "detail_identifier_only"):
        url = coverage.get("url", "")
        match = IDS.search(url)
        if match:
            rows = [dict(shop_id=match[1], item_id=match[2], product_url=url.split("?")[0],
                         source_url=url, collected_at=data.get("captured_at", ""),
                         _reason="detail_url_identifier_only")]
            coverage = dict(coverage, status="detail_identifier_only", matching_cards=0)
    return rows, coverage


def read_offline_zip(path):
    with zipfile.ZipFile(path) as archive:
        matches = [name for name in archive.namelist() if name.rsplit("/", 1)[-1] == "observations.json"]
        if len(matches) != 1:
            raise ValueError("Expected one observations.json in diagnostic ZIP")
        payload = json.loads(archive.read(matches[0]))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return payload.get("observations", payload.get("records", []))
    raise ValueError("Invalid observations.json")


def row_from(record):
    row = {field: str(record.get(field) or "").strip() for field in FIELDS}
    row["brand"] = row["brand"] or "JUNGSAEMMOOL"
    row["query"] = row["query"] or "jungsaemmool"
    row["sold_period"] = row["sold_period"] or "unknown"
    match = IDS.search(row["product_url"])
    if match:
        if row["shop_id"] and row["shop_id"] != match[1]:
            raise ValueError("shop_id does not match product URL")
        if row["item_id"] and row["item_id"] != match[2]:
            raise ValueError("item_id does not match product URL")
        row["shop_id"], row["item_id"] = match.groups()
    return row


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def run(probe, offline_zip, out, capture_dir=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    records, source_coverage = read_probe(probe) if probe else ([], {})
    capture_pages = []
    if capture_dir:
        files = sorted(Path(capture_dir).glob("capture_*.json"))
        if not files:
            raise ValueError("No capture_*.json files in capture directory")
        for file in files:
            rows, coverage = read_probe(file)
            records.extend(rows)
            capture_pages.append(dict(coverage, evidence_file=file.name))
    records += read_offline_zip(offline_zip) if offline_zip else []
    possible_sold_suffix_loss = [f"{r.get('shop_id')}:{r.get('item_id')}" for r in records
                                 if re.search(r"[\d][萬千Kk]$", str(r.get("sold_display", "")))]
    accepted, incomplete = [], []
    for record in records:
        row = row_from(record)
        missing = [name for name in ("shop_id", "item_id", "product_url", "source_url", "collected_at") if not row[name]]
        reason = record.get("_reason") or ("missing_" + ",".join(missing) if missing else "")
        if reason:
            incomplete.append(dict(row, reason=reason))
        else:
            accepted.append(row)
    write_csv(out / "observations.csv", accepted, FIELDS)
    write_csv(out / "incomplete_observations.csv", incomplete, FIELDS + ["reason"])
    # Indexed links expand the investigation queue, not the observed seller count.
    lead_file = Path(__file__).parent / "evidence/search_index_leads_20261026.json"
    leads = json.loads(lead_file.read_text(encoding="utf-8"))["records"] if lead_file.exists() else []
    write_csv(out / "unverified_search_leads.csv", leads,
              ["shop_id", "item_id", "indexed_url"])
    subprocess.run([sys.executable, str(ROOT / "shopee_tw/collector/normalize.py"),
                    "--input", str(out / "observations.csv"), "--out", str(out)], check=True)
    report_path = out / "coverage_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report.update(track="B", brand="JUNGSAEMMOOL", input_probe=bool(probe),
                  input_offline_zip=bool(offline_zip), incomplete_rows=len(incomplete),
                  input_capture_files=len(capture_pages), capture_pages=capture_pages,
                  possible_sold_suffix_loss=possible_sold_suffix_loss,
                  unverified_search_lead_shops=len(set(r["shop_id"] for r in leads)),
                  collection_status="partial_observation" if accepted else "no_valid_observation",
                  search_results_exhausted=False, marketplace_coverage="unknown",
                  page_coverage="captured_pages_partial" if capture_pages else
                                ("first_search_page_partial" if probe else "unknown"),
                  source_coverage=source_coverage,
                  observation_time_note="Probe collected_at records structuring time, not exact DOM capture time."
                                        if probe else "No probe supplied.",
                  note="Local import of prior observations; this execution did not fetch Shopee pages. "
                       "Incomplete rows are excluded from verified observations.")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "RUN_STATUS.md").write_text(
        "# TRACK B import\n\n"
        f"Status: {report['collection_status']}; listings: {report['unique_listing_keys']}; "
        f"shops: {report['unique_shop_keys']}; incomplete rows: {len(incomplete)}.\n\n"
        "Partial observation only; no live collection in this run and no full seller inventory.\n",
        encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", type=Path, help="Browser observation JSON export")
    parser.add_argument("--offline-zip", type=Path, help="Optional diagnostic ZIP")
    parser.add_argument("--capture-dir", type=Path, help="Folder of user-triggered browser capture JSON files")
    parser.add_argument("--out", type=Path, default=ROOT / "shopee_tw/output/track_b_import")
    args = parser.parse_args()
    print(json.dumps(run(args.probe, args.offline_zip, args.out, args.capture_dir), ensure_ascii=False, indent=2))
