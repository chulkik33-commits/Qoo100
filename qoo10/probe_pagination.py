import asyncio, json, re
from pathlib import Path
from urllib.parse import quote
from playwright.async_api import async_playwright

OUT=Path("qoo10/pagination_probe");OUT.mkdir(parents=True,exist_ok=True)

async def main():
    kw="メディヒール"
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=["--no-sandbox"])
        ctx=await browser.new_context(locale="ja-JP",timezone_id="Asia/Tokyo",viewport={"width":430,"height":1200})
        page=await ctx.new_page()
        reqs=[]
        page.on("request",lambda req:reqs.append(req.url) if any(x in req.url.lower() for x in ["search","dynamic","goods","ajax"]) else None)
        url=f"https://m.qoo10.jp/gmkt.inc/Mobile/Search/Default.aspx?keyword={quote(kw)}"
        await page.goto(url,wait_until="domcontentloaded",timeout=60000)
        await page.wait_for_timeout(3000)
        snapshots=[]
        for i in range(12):
            codes=await page.evaluate("""() => [...document.querySelectorAll('[data_gd_no]')].map(x=>x.getAttribute('data_gd_no')).filter(Boolean)""")
            snapshots.append({"step":i,"count":len(set(codes)),"last":codes[-10:]})
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2200)
        html=await page.content()
        (OUT/"page.html").write_text(html,encoding="utf-8")
        links=await page.evaluate("""() => [...document.querySelectorAll('a')].map(a=>({text:(a.innerText||'').trim(),href:a.href})).filter(x=>/次|next|もっと|page|ページ/i.test(x.text)||/[?&](page|curPage|page_no)=/i.test(x.href)).slice(0,100)""")
        (OUT/"result.json").write_text(json.dumps({"final_url":page.url,"snapshots":snapshots,"links":links,"requests":list(dict.fromkeys(reqs))},ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({"snapshots":snapshots,"links":links[:20],"requests":list(dict.fromkeys(reqs))[-80:]},ensure_ascii=False,indent=2))
        await browser.close()

if __name__=="__main__":asyncio.run(main())
