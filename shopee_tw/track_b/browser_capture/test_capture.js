const assert = require("node:assert/strict");
const fs = require("node:fs");
const {normalizeCards, normalizePage} = require("./capture_core.js");
const evidence = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const pageUrl = "https://shopee.tw/search?keyword=jungsaemmool";
const at = "2026-10-26T12:08:44.956Z";
const result = normalizeCards(evidence.raw_cards, pageUrl, at, "");
assert.equal(result.records.length, 26);
assert.equal(new Set(result.records.map(r => r.shop_id)).size, 17);
assert.equal(result.coverage.unrelated_cards, 2);
assert.equal(result.coverage.status, "captured_visible_cards");
assert(result.records.every(r => /^\d+$/.test(r.shop_id) && /^\d+$/.test(r.item_id)));
assert(result.records.every(r => r.source_url === pageUrl && r.collected_at === at));
assert.equal(normalizeCards([], pageUrl + "&page=1", at, "Shopee page cannot display").coverage.status, "page_error");
const detailUrl = "https://shopee.tw/-JUNG-SAEM-MOOL-Essential-i.1182369951.56003249978?extra=1";
const detail = normalizePage({page_url: detailUrl, cards: evidence.raw_cards,
  detail_title: "JUNG SAEM MOOL Essential Skin Nuder Longwear Cushion | 蝦皮購物",
  price_candidates: ["$ 599"], sold_candidates: ["已售出 1000+"]}, at);
assert.equal(detail.records.length, 1);
assert.equal(detail.records[0].item_id, "56003249978");
assert.equal(detail.records[0].price_twd, "599");
assert.equal(detail.records[0].sold_display, "已售出 1000+");
assert.equal(detail.coverage.status, "captured_product_detail");
const ambiguous = normalizePage({page_url: detailUrl, cards: [], detail_title: "JUNG SAEM MOOL Cushion",
  price_candidates: ["$ 599", "$ 699"], sold_candidates: []}, at);
assert.equal(ambiguous.records[0].price_twd, "");
assert.equal(normalizePage({page_url: detailUrl, cards: [], detail_title: "蝦皮購物"}, at).coverage.status,
  "detail_identifier_only");
console.log("Visible page parser: 26 listings, 17 shops, 2 unrelated; error page recorded.");
