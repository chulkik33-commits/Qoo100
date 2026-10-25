# Shopee Taiwan source verification — 2026-10-25

## Current decision
No live source is connected. Normalization workflow has passed; that only validates previously observed rows.
Shopee TW official service terms section 3.1 restrict automated monitoring/copying without prior written permission; public product visibility alone is not bulk-export permission:
https://help.shopee.tw/portal/4/article/77267-

## Evaluated paths
1. Seller Open Platform: merchant/shop-authorized product/order API, not a competitor-wide marketplace catalogue. Not fit for seller discovery.
2. Affiliate Open API: regional Shopee Affiliate APIs in other markets provide `productOfferV2` and `shopOfferV2` keyword search with authorization. Taiwan availability, account eligibility, permitted use, cost and listing coverage **not verified**. Do not use the API until confirmed for Taiwan.
3. Authorized CSV / export feeds: the existing source adapter supports CSV supplied under an appropriate license; no recurring marketplace feed is configured.
4. Public web search: helps confirm individual listing pages, cannot honestly establish exhaustive coverage or permission for unattended crawling.

## Remaining go/no-go checks for affiliate feed
- Taiwan program actually enables Affiliate Open API for the intended account.
- Documented API endpoint, authorization and permission for the intended market research.
- Product search results include stable shop/item identifiers and desired price/sales fields.
- Offer coverage: whether it only contains commission-eligible offers rather than all market listings.
- No paid plan/automatic fee; read quota and terms.
- Test keyword: JUNGSAEMMOOL, 鄭瑄茉. Compare unique shop count and page exhaustion.

## No false positives
GitHub Actions successful = processing environment works; 0 newly scraped shops, no market-wide completeness.
Source connection considered successful ONLY after observed live TW records have source URL + capture time and supported permission evidence.
