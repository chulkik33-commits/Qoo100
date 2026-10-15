import re, json
from pathlib import Path
from urllib.parse import quote
from playwright.sync_api import sync_playwright

OUT=Path("qoo10/mobile_sales_probe");OUT.mkdir(parents=True,exist_ok=True)
KEYWORDS=["ジョンセンムル"]
GOODS=["1174516091","1015189379","1165289320","1106123843","1179694605"]

def main():
    rows=[]
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True,args=["--no-sandbox"])
        ctx=b.new_context(locale="ja-JP",timezone_id="Asia/Tokyo",viewport={"width":430,"height":1200})
        page=ctx.new_page()
        for kw in KEYWORDS:
            url=f"https://www.qoo10.jp/gmkt.inc/Mobile/Search/DynamicAd.aspx?keyword={quote(kw)}"
            resp=page.goto(url,wait_until="domcontentloaded",timeout=60000);page.wait_for_timeout(4000)
            html=page.content();text=page.locator("body").inner_text()
            (OUT/f"search_{kw}.html").write_text(html,encoding="utf-8")
            items=page.evaluate("""() => [...document.querySelectorAll('#div_mobile_list li[data_gd_no]')].slice(0,20).map(li=>{
              const a=li.querySelector('a[gd_no]'), name=li.querySelector('h3.tt'), sold=li.querySelector('.sld'), rvw=li.querySelector('.rvw'), prc=li.querySelector('.prc'), ship=li.querySelector('.shp_ntn');
              return {goods_code:li.getAttribute('data_gd_no'),href:a?a.href:null,name:name?name.innerText.trim():null,sold:sold?sold.innerText.trim():null,review:rvw?rvw.innerText.trim():null,price:prc?prc.innerText.trim():null,shipping:ship?ship.innerText.trim():null,html:li.outerHTML.slice(0,2500)};
            })""")
            rows.append({"type":"search","keyword":kw,"status":resp.status if resp else None,"items":items})
        for gd in GOODS:
            url=f"https://m.qoo10.jp/gmkt.inc/Mobile/goods/goods.aspx?goodscode={gd}"
            resp=page.goto(url,wait_until="domcontentloaded",timeout=60000);page.wait_for_timeout(5000)
            html=page.content();text=page.locator("body").inner_text()
            (OUT/f"goods_{gd}.html").write_text(html,encoding="utf-8")
            (OUT/f"goods_{gd}.txt").write_text(text,encoding="utf-8")
            candidates=page.evaluate("""() => {
              const c=s=>(s||'').replace(/\s+/g,' ').trim();
              const out=[];
              for(const el of document.querySelectorAll('a,span,div,strong,p,h1,h2,h3')){
                const t=c(el.innerText);
                if(!t || t.length>150) continue;
                if(/shop|ショップ|販売者|seller|公式/i.test(t)) out.push({tag:el.tagName,cls:el.className,id:el.id,text:t,href:el.href||null});
              }
              return out.slice(0,100);
            }""")
            print("\nGOODS",gd,"STATUS",resp.status if resp else None,"TITLE",page.title())
            print(text[:5000])
            metrics=page.evaluate("""() => {
              const html=document.documentElement.innerHTML;
              const m=(k)=>{const r=new RegExp('"'+k+'"\\\\s*:\\\\s*([0-9.]+)');const x=html.match(r);return x?Number(x[1]):null};
              return {total_sell_amt:m('total_sell_amt'),review_cnt:m('review_cnt'),remain_cnt:m('remain_cnt')};
            }""")
            rows.append({"type":"goods","goods_code":gd,"status":resp.status if resp else None,"url":page.url,"candidates":candidates,"metrics":metrics})
        b.close()
    (OUT/"summary.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__":main()
