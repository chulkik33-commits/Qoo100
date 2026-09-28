import json
import re
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

KEYWORDS = ["ジョンセンムル", "jungsaemmool"]
OUT = Path("qoo10/output_playwright")
OUT.mkdir(parents=True, exist_ok=True)


def extract_count(text: str):
    patterns = [
        r"([0-9][0-9,]*)\s*件",
        r"([0-9][0-9,]*)\s*商品",
        r"全\s*([0-9][0-9,]*)",
    ]
    vals = []
    for p in patterns:
        for m in re.findall(p, text):
            try:
                vals.append(int(m.replace(",", "")))
            except ValueError:
                pass
    return max(vals) if vals else None


results = []
with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"]
    )
    context = browser.new_context(
        locale="ja-JP",
        timezone_id="Asia/Tokyo",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/153.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1440, "height": 1200},
    )

    for keyword in KEYWORDS:
        page = context.new_page()
        url = f"https://www.qoo10.jp/s/{quote(keyword)}?keyword={quote(keyword)}"
        status = None
        error = None
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
            status = response.status if response else None
            page.wait_for_timeout(5000)
            title = page.title()
            body = page.locator("body").inner_text(timeout=10000)
            html = page.content()
            final_url = page.url

            qoo10_error = (
                "523" in body
                or "Origin is unreachable" in body
                or "Error 523" in body
                or len(body.strip()) < 100
            )

            product_links = page.locator('a[href*="/g/"]').count()
            query_count = extract_count(body)

            result = {
                "keyword": keyword,
                "requested_url": url,
                "final_url": final_url,
                "http_status": status,
                "title": title,
                "body_chars": len(body),
                "html_chars": len(html),
                "qoo10_error_page": qoo10_error,
                "query_count_candidate": query_count,
                "product_link_count": product_links,
                "review_sort_present": "レビューが多い順" in body,
                "shipping_korea_present": "韓国" in body,
                "shipping_japan_present": "日本" in body,
                "related_search_present": "関連検索" in body,
            }

            safe = "jp" if keyword.startswith("ジョ") else "en"
            (OUT / f"{safe}_body.txt").write_text(body, encoding="utf-8")
            (OUT / f"{safe}_page.html").write_text(html, encoding="utf-8")
            page.screenshot(path=str(OUT / f"{safe}_page.png"), full_page=True)
        except Exception as exc:
            error = repr(exc)
            result = {
                "keyword": keyword,
                "requested_url": url,
                "http_status": status,
                "error": error,
            }
        finally:
            page.close()
        results.append(result)

    browser.close()

summary = {"method": "playwright_chromium", "results": results}
(OUT / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(summary, ensure_ascii=False, indent=2))
