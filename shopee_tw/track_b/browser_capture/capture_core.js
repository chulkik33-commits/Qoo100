(function (root) {
  "use strict";
  const PRODUCT = /-i\.(\d+)\.(\d+)(?:[/?#]|$)/;
  const BRAND = /jung\s*saem\s*mool|jungsaemmool|鄭[瑄宣][茉沫]/i;
  const SOLD = /(?:已售出|已售)\s*([\d,.]+\s*[萬千Kk+]?)/;
  const PRICE = /(?:NT\s*)?\$\s*([\d,]+)/;

  function normalizeCards(cards, pageUrl, capturedAt, pageError) {
    const seen = new Set();
    const records = [];
    let unrelated = 0;
    for (const card of cards) {
      const match = String(card.url || "").match(PRODUCT);
      if (!match) continue;
      const title = String(card.label || "").replace(/^View product:\s*/i, "").trim() ||
        String(card.text || "").split("\n").map(x => x.trim()).find(x => BRAND.test(x)) || "";
      if (!BRAND.test(title.normalize("NFKC"))) { unrelated++; continue; }
      const key = match[1] + ":" + match[2];
      if (seen.has(key)) continue;
      seen.add(key);
      const raw = String(card.text || "");
      const price = raw.match(PRICE);
      const sold = raw.match(SOLD);
      records.push({
        brand: "JUNGSAEMMOOL", query: "jungsaemmool", shop_name: "", shop_url: "",
        shop_id: match[1], item_id: match[2], product_name: title,
        product_url: String(card.url).split("?")[0],
        price_twd: price ? price[1].replaceAll(",", "") : "",
        sold_display: sold ? sold[0].trim() : "", sold_period: "unknown",
        source_url: pageUrl, collected_at: capturedAt
      });
    }
    const url = new URL(pageUrl);
    const page = Number(url.searchParams.get("page") || 0);
    const status = pageError ? "page_error" : records.length ? "captured_visible_cards" : "no_matching_cards";
    return {
      captured_at: capturedAt,
      scope: "Only product links rendered in the user-opened page at capture time; no network fetch or automatic page navigation.",
      records,
      coverage: {url: pageUrl, page, status, matching_cards: records.length,
        unrelated_cards: unrelated, search_results_exhausted: false,
        marketplace_coverage: "unknown", page_error_text: pageError || ""}
    };
  }
  root.TrackBCapture = {normalizeCards};
  if (typeof module !== "undefined" && module.exports) module.exports = {normalizeCards};
})(globalThis);
