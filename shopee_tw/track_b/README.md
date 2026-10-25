# TRACK B — JUNGSAEMMOOL / 鄭瑄茉 / 정샘물

Reviewed 2026-10-25 (Korea). Affiliate API excluded.

## Result
No verified free source permitting commercial ingestion was found among the reviewed candidates. **Live connection and seller enumeration are not complete.** No marketplace requests are made. No paid service, free trial, proxy, CAPTCHA solver or undocumented endpoint is used.

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
python shopee_tw/track_b/run.py
```

Actions: `Shopee TW - TRACK B permissioned sources`, manually or on relevant pushes. Public-repository runners only, 3-minute limit, no external API credentials, no schedule. A green workflow reports successful validation, **not successful data collection**. The job summary and JSON state `blocked_no_verified_free_commercial_source`.

## Outputs
`shopee_tw/output/track_b/`: empty verified observations/listings/seller CSVs with the existing schema; coverage report; source review; unverified historical seed CSV. The existing 30-row historical seed lacks original source URLs and collection timestamps and is never merged into verified records. It does not establish current inventory or seller completeness.

Target fields remain: brand, query, shop_name, shop_url, shop_id, item_id, product_name, product_url, price_twd, sold_display, sold_period, source_url, collected_at. Blank sales is unknown, never zero; reviews/stock are not sales. Historical timestamps must never be replaced with execution time. Execution timestamp and data observation timestamp are separate.

## Remaining connection requirements
A candidate must have provider identity, exact feed/download URL, explicit zero-price commercial storage/reuse permission, documented automated access permission and limits, Taiwan scope, field documentation and evidence of rights to supply the data. Confirm whether public GitHub artifacts are permitted; otherwise do not publish provider data. Freeze license/terms evidence and source version/hash. Then implement and test a source-specific adapter mapping to the existing schema, preserving provider observation time separately from fetch time and declaring missing fields and sampled coverage. Do not enable a source just by toggling its status: the runner intentionally refuses approved-but-unimplemented sources.

Seller coverage, each seller's complete inventory, numeric IDs, price and observed sales remain uncollected. No brand evaluation or SKU recommendation is performed.
