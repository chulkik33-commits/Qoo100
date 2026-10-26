# TRACK B — JUNGSAEMMOOL / 鄭瑄茉 / 정샘물

Reviewed 2026-10-25 (Korea). Affiliate API excluded.

## Result
Saved browser observations from 2026-10-26 are imported: 26 product listings and 17 distinct numeric shop IDs from part of search page 1. Shop names and each seller's full inventory are unknown. The per-row time is the time of structuring the captured DOM, not the exact page capture time. One user-saved HTML diagnostic row lacks an observation time and is kept only in local `incomplete_observations.csv`, outside verified counts. Page 2 returned a generic display error in the signed-in browser session. **Live repeatable collection and seller enumeration are incomplete.** This pipeline makes no marketplace requests.

Search indexing yielded 5 additional shop IDs in `evidence/search_index_leads_20261026.json`. They are exported only to `unverified_search_leads.csv`; indexed links have no verified current price, sold count or observation time and are not added to seller_master.

The next technical capture route is the user-triggered Chrome tool in `browser_capture/README_KO.md`. It extracts only rendered cards from the open page and writes local JSON, with no automatic navigation or remote service. `import_observations.py --capture-dir <folder>` combines captures and records each page's status; no page coverage is inferred from missing files. Its extraction function was tested against the 28 actual card payloads saved from the first browser session (26 relevant, 2 unrelated). Installation and Shopee navigation on the user's local Chrome remain untested.

The user-submitted 2026-10-26 13:35:38 UTC search capture in `evidence/captures/` verified the extension works on the local Chrome search page: 16 products across 10 shops, adding 7 item IDs and 2 shop IDs versus the earlier first-page probe. Some cards are loaded lazily, so a page capture is not page completion. The v0.1 extension truncated the plus suffix in one displayed sold value (`1萬+` became `1萬`); the parser is corrected and this prior row is flagged as potentially truncated, without inventing a replacement value.

| Source | Decision | Evidence |
|---|---|---|
| Rebrowser public sample | Excluded: research/non-commercial license | https://github.com/rebrowser/shopee-dataset |
| Feebee | Blocked pending written permission: terms 12.5/12.8 restrict commercial storage and systematic extraction | https://feebee.com.tw/terms/ |
| BigGo | Blocked: inbound Datafeed/API statement is not an outbound data license | https://biggo.com.tw/official/disclaimers |
| zhezhouhongen/shoeep_Dataset | Blocked: separate data license not successfully retrieved; source-code license is insufficient | https://github.com/zhezhouhongen/shoeep_Dataset |
| Taiwan government cosmetic permits | Not seller/product listing data; unsuitable for this objective | https://data.gov.tw/en/datasets/9580 |

Searches included Shopee Taiwan datasets, commercial licenses, Kaggle Taiwan cosmetics, BigGo API/feed terms, Feebee permissions and Taiwan government open data. This is a candidate review, not proof that no qualifying source exists anywhere. Search snippets are discovery leads, not a reusable licensed feed. Robots permissions alone are insufficient.

## Reproduce
From repository root, Python 3.11+, standard library only:

```
python shopee_tw/tests/test_track_b.py
python shopee_tw/tests/test_track_b_import.py
python shopee_tw/track_b/import_observations.py --probe shopee_tw/track_b/evidence/observed_20261026.json
```

Actions: `Shopee TW - TRACK B observations`, manually or on relevant pushes. Public-repository runners only, 3-minute limit, no external API credentials, no schedule. A green workflow means the **saved evidence was reprocessed**, not that a new Shopee page was collected. The job summary and JSON state `partial_observation`.

## Outputs
`shopee_tw/output/track_b/`: observed listings/seller CSVs with the existing schema, incomplete observations CSV, and coverage report. The existing 30-row historical seed lacks original source URLs and collection timestamps and is never merged into verified records. It does not establish current inventory or seller completeness. `run.py` remains the separate no-source review command.

Target fields remain: brand, query, shop_name, shop_url, shop_id, item_id, product_name, product_url, price_twd, sold_display, sold_period, source_url, collected_at. Blank sales is unknown, never zero; reviews/stock are not sales. Historical timestamps must never be replaced with execution time. Execution timestamp and data observation timestamp are separate.

## Remaining connection requirements
A candidate must have provider identity, exact feed/download URL, explicit zero-price commercial storage/reuse permission, documented automated access permission and limits, Taiwan scope, field documentation and evidence of rights to supply the data. Confirm whether public GitHub artifacts are permitted; otherwise do not publish provider data. Freeze license/terms evidence and source version/hash. Then implement and test a source-specific adapter mapping to the existing schema, preserving provider observation time separately from fetch time and declaring missing fields and sampled coverage. Do not enable a source just by toggling its status: the runner intentionally refuses approved-but-unimplemented sources.

Seller coverage, each seller's complete inventory, numeric IDs, price and observed sales remain uncollected. No brand evaluation or SKU recommendation is performed.
