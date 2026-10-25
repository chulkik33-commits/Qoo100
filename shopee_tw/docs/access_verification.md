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


## Dual-track investigation 2026-10-25

### Track A — affiliate API
- Taiwan affiliate program officially exists and says joining is free:
  https://shopee.tw/m/affiliateprogram
- Singapore Shopee official help states affiliate API supports Shopee/brand/product offer lists, short links, conversion reports:
  https://help.shopee.sg/portal/10/article/191702-API-Access
- A Taiwan independent article describes a separate Affiliate Open API entry at affiliate.shopee.tw, distinct from Seller Open API:
  https://9527.com.tw/journey/shopee-api-waiting/
- This does NOT establish that the user's TW account has API approval or that non-affiliate seller inventories are included. NO endpoint, token or calls configured. Pending explicit approval and usable documentation.

### Track B — licensed existing datasets / price comparison
- Rebrowser offers Shopee dataset preview on GitHub including Taiwan and stable itemId/shopId:
  https://github.com/rebrowser/shopee-dataset
- Its stated free license is **research and non-commercial only**; business use requires paid license. Under a strict zero-cash commercial model this is not an approved source to ingest. Do not run it in this repository.
- FindPrice Taiwan indexes Shopee seller names and listings by brand:
  https://www.findprice.com.tw/b/jungsaemmool
  This demonstrates seller discovery coverage beyond the manually observed 30 names, but does not itself confer permission for unattended bulk capture or exhaustive coverage.
- Shopee official help confirms hottest-selling search sort for products and shops:
  https://help.shopee.tw/portal/4/article/119666
  User-visible results do not constitute an approved bulk automated feed.

### Decision
No approved, zero-cost **commercial-use** source has yet passed all checks. Keep live collection DISABLED, historical import active. Prioritize verifying TW Affiliate API access/scope before changing source_adapter; in parallel contact data publishers for written commercial-use authorization at zero cost, if available. Never claim Actions normalization is live marketplace collection.
