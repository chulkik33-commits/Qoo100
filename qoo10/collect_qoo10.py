import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

KEYWORDS = ["ジョンセンムル", "jungsaemmool"]
OUT = Path("qoo10/output_collect")
OUT.mkdir(parents=True, exist_ok=True)


def nint(text):
    if text is None:
        return None
    m = re.search(r"([0-9][0-9,]*)", text)
    return int(m.group(1).replace(",", "")) if m else None


def parse_market_snapshot(page, keyword):
    url = f"https://www.qoo10.jp/s/{quote(keyword)}?keyword={quote(keyword)}"
    resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3500)

    snapshot = page.evaluate("""
    () => {
      const clean = s => (s || '').replace(/\\s+/g, ' ').trim();
      const localTabs = [...document.querySelectorAll('a.local[data-nation_code]')];
      const ship = {};
      for (const a of localTabs) {
        const code = a.getAttribute('data-nation_code') || 'ALL';
        const num = a.querySelector('.num');
        if (!(code in ship)) ship[code] = clean(num ? num.textContent : '');
      }

      const related = [...document.querySelectorAll('#search_keyword_list a')]
        .map(a => clean(a.textContent)).filter(Boolean);

      const cats = [];
      for (const a of document.querySelectorAll('a[href*="gdlc_cd="]')) {
        const sp = a.querySelector('span');
        if (!sp || !/\\([0-9,]+\\)/.test(sp.textContent || '')) continue;
        const name = clean([...a.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(' '));
        if (!name) continue;
        cats.push({name, count_text: clean(sp.textContent)});
      }
      const seen = new Set();
      const categories = cats.filter(x => !seen.has(x.name) && seen.add(x.name));

      const brand = document.querySelector('#search_result_item_list .txt_brand[href*="Brand.aspx"], #plus_item_list .txt_brand[href*="Brand.aspx"]');
      return {
        title: document.title,
        final_url: location.href,
        shipping_counts_text: ship,
        related_words: [...new Set(related)],
        categories,
        brand_name: brand ? clean(brand.textContent) : null,
        brand_url: brand ? brand.href : null,
        review_sort_available: !!document.querySelector('a[val="MOST_REVIEWED"]')
      };
    }
    """)
    snapshot["http_status"] = resp.status if resp else None
    snapshot["keyword"] = keyword
    snapshot["total_count"] = nint(snapshot["shipping_counts_text"].get("ALL"))
    snapshot["japan_count"] = nint(snapshot["shipping_counts_text"].get("JP"))
    snapshot["korea_count"] = nint(snapshot["shipping_counts_text"].get("KR"))
    for c in snapshot["categories"]:
        c["count"] = nint(c.pop("count_text", ""))
    return snapshot


def sort_review_and_extract_top10(page):
    review_link = page.locator('a[val="MOST_REVIEWED"]').first
    if review_link.count() == 0:
        raise RuntimeError("review sort link not found")

    # Qoo10 keeps the sort choices under a custom dropdown whose overlay can
    # intercept a normal Playwright click. Trigger the site's own click handler
    # directly in the DOM instead.
    review_link.evaluate("el => el.click()")
    page.wait_for_timeout(5500)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass

    sort_value = page.locator('input[name="sortType"]').first.get_attribute("value") if page.locator('input[name="sortType"]').count() else None

    products = page.evaluate("""
    () => {
      const clean = s => (s || '').replace(/\\s+/g, ' ').trim();
      const rows = [...document.querySelectorAll('#search_result_item_list tr[list_type="search_new_list_type"]')].slice(0, 10);
      return rows.map((r, i) => {
        const goods = r.querySelector('.sbj a[data-type="goods_url"]');
        const rev = r.querySelector('.review_total_count');
        const shop = r.querySelector('a.lnk_sh');
        const priceStrong = r.querySelector('.td_prc .prc strong');
        const priceCell = r.querySelector('.td_prc');
        const shipNation = r.querySelector('.td_ship .shp_ntn');
        const brand = r.querySelector('.txt_brand');
        return {
          rank: i + 1,
          goods_code: r.getAttribute('goodscode'),
          brand: brand ? clean(brand.textContent) : null,
          product_name: goods ? clean(goods.textContent) : null,
          product_url: goods ? goods.href : null,
          price: priceStrong ? clean(priceStrong.textContent) : (priceCell ? clean(priceCell.textContent) : null),
          price_full_text: priceCell ? clean(priceCell.textContent) : null,
          review_count_text: rev ? clean(rev.textContent) : null,
          shop_name: shop ? clean([...shop.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(' ')) || clean(shop.textContent).replace(/^Power seller\\s*/,'') : null,
          shop_url: shop ? shop.href : null,
          shipping_country: shipNation ? clean(shipNation.textContent) : null
        };
      });
    }
    """)
    for p in products:
        p["review_count"] = nint(p.pop("review_count_text", None))
    return sort_value, products


def enrich_shop_counts(context, products):
    cache = {}
    shop_page = context.new_page()
    for p in products:
        url = p.get("shop_url")
        if not url:
            p["shop_product_count"] = None
            continue
        if url in cache:
            p["shop_product_count"] = cache[url]
            continue
        try:
            shop_page.goto(url, wait_until="domcontentloaded", timeout=60000)
            shop_page.wait_for_timeout(1800)
            body = shop_page.locator("body").inner_text(timeout=10000)
            m = re.search(r"([0-9][0-9,]*)\s*販売中の商品", body)
            if not m:
                m = re.search(r"全ての商品\s*\(([0-9][0-9,]*)\)", body)
            count = int(m.group(1).replace(",", "")) if m else None
        except Exception:
            count = None
        cache[url] = count
        p["shop_product_count"] = count
    shop_page.close()


def save_csv(rows, path):
    fields = [
        "keyword", "rank", "goods_code", "brand", "product_name", "price", "review_count",
        "shop_name", "shop_product_count", "shipping_country", "product_url", "shop_url"
    ]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    collected = {
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "github_actions_playwright_chromium",
        "keywords": []
    }
    csv_rows = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            viewport={"width": 1440, "height": 1200},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
        )
        page = context.new_page()

        for keyword in KEYWORDS:
            snap = parse_market_snapshot(page, keyword)
            sort_value, products = sort_review_and_extract_top10(page)
            enrich_shop_counts(context, products)
            snap["sort_value_after_click"] = sort_value
            snap["top10_by_reviews"] = products
            collected["keywords"].append(snap)
            for x in products:
                csv_rows.append({"keyword": keyword, **x})

        browser.close()

    (OUT / "qoo10_collection.json").write_text(json.dumps(collected, ensure_ascii=False, indent=2), encoding="utf-8")
    save_csv(csv_rows, OUT / "qoo10_top10_reviews.csv")

    market_rows = []
    for k in collected["keywords"]:
        market_rows.append({
            "keyword": k["keyword"],
            "total_count": k["total_count"],
            "japan_count": k["japan_count"],
            "korea_count": k["korea_count"],
            "brand_name": k["brand_name"],
            "brand_url": k["brand_url"],
            "related_words": " | ".join(k["related_words"]),
            "categories": " | ".join(f"{c['name']}:{c['count']}" for c in k["categories"]),
            "sort_value_after_click": k["sort_value_after_click"],
        })
    with open(OUT / "qoo10_market_summary.csv", "w", newline="", encoding="utf-8-sig") as f:
        fields = list(market_rows[0].keys())
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(market_rows)

    print(json.dumps(collected, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
