# Shopee Taiwan market-data collector

This directory is independent of the Qoo10 collector.

## Scope
- First brand: JUNGSAEMMOOL / 鄭瑄茉 / 정샘물
- Seller discovery first, then seller-product mapping
- Raw facts only; no brand grades or SKU recommendations
- Zero paid services, no proxy/captcha bypass or undocumented Shopee endpoints

## What works now
CSV ingestion, validation, source evidence log, shop deduplication, snapshot preservation, and GitHub Actions manual runs.

## Not yet working
Automatic enumeration of all Shopee TW search-result pages. The source adapter requires a permitted, documented source of marketplace listing data. Do not confuse GitHub Actions success with complete marketplace collection.

## Run
1. Put sourced rows into `shopee_tw/input/observations.csv` (see schema).
2. Trigger the workflow `Shopee TW - validate collected observations`.
3. Download artifact `shopee-tw-validated`; inspect coverage_report.json.
4. Extend `collector/source_adapter.py` only after confirming permitted access.

The source URL, collection timestamp and listing/shop identifiers must be kept. Missing fields stay blank. Never represent stock quantity as sold quantity.
