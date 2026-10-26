"""Check real saved evidence and separation of missing observation times."""
import importlib.util
import json
import tempfile
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("track_b_import", root / "track_b/import_observations.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
probe = root / "track_b/evidence/observed_20261026.json"

with tempfile.TemporaryDirectory() as directory:
    zip_path = Path(directory) / "offline.zip"
    record = dict(json.loads(probe.read_text())["records"][0], collected_at="")
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("observations.json", json.dumps([record]))
    report = module.run(probe, zip_path, Path(directory) / "output")
    assert report["raw_rows"] == report["unique_listing_keys"] == 26
    assert report["unique_shop_keys"] == 17
    assert report["incomplete_rows"] == 1
    assert report["unverified_search_lead_shops"] == 5
    assert report["page_coverage"] == "first_search_page_partial"
    assert not report["search_results_exhausted"]
    assert "missing_collected_at" in (Path(directory) / "output/incomplete_observations.csv").read_text()
    captures = Path(directory) / "captures"
    captures.mkdir()
    (captures / "capture_error.json").write_text(json.dumps({"records": [], "coverage": {
        "page": 1, "status": "page_error", "matching_cards": 0}}))
    (captures / "capture_page1.json").write_text(json.dumps({"records": json.loads(probe.read_text())["records"],
        "coverage": {"page": 0, "status": "captured_visible_cards", "matching_cards": 26}}))
    report2 = module.run(None, None, Path(directory) / "captured_output", captures)
    assert report2["input_capture_files"] == 2
    assert report2["unique_listing_keys"] == 26
    assert [r["status"] for r in report2["capture_pages"]] == ["page_error", "captured_visible_cards"]
print("Track B saved observation import passed")
