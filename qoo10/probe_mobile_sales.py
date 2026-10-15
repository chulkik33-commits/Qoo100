import re, json
from pathlib import Path
from urllib.parse import quote
from playwright.sync_api import sync_playwright

OUT=Path("qoo10/mobile_sales_probe");OUT.mkdir(parents=True,exist_ok=True)
KEYWORDS=["ジョンセンムル","メディヒール"]

def main():
    rows=[]
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True,args=["--no-sandbox"])
        ctx=b.new_context(locale="ja-JP",timezone_id="Asia/Tokyo",viewport={"width":430,"height":1200})
        page=ctx.new_page()
        for kw in KEYWORDS:
            url=f"https://www.qoo10.jp/gmkt.inc/Mobile/Search/DynamicAd.aspx?keyword={quote(kw)}"
            resp=page.goto(url,wait_until="domcontentloaded",timeout=60000)
            page.wait_for_timeout(5000)
            html=page.content(); text=page.locator("body").inner_text()
            (OUT/f"{kw}.html").write_text(html,encoding="utf-8")
            (OUT/f"{kw}.txt").write_text(text,encoding="utf-8")
            print("KEYWORD",kw,"STATUS",resp.status if resp else None,"TITLE",page.title(),"URL",page.url,"HTML",len(html))
            print(text[:6000])
            sels=page.evaluate("""() => {
              const out=[]; const all=[...document.querySelectorAll('a')];
              for(const a of all){
                const t=(a.innerText||'').replace(/\s+/g,' ').trim();
                if(/個販売/.test(t) || /レビュー/.test(t)){
                  out.push({text:t.slice(0,1000),href:a.href,cls:a.className});
                }
              }
              return out.slice(0,30);
            }""")
            rows.append({"keyword":kw,"status":resp.status if resp else None,"items":sels})
        b.close()
    (OUT/"summary.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__":main()
