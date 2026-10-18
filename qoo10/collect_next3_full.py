import asyncio,csv,json,math,re,random
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import quote
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parent
BRANDS=ROOT/"next_candidate_brands.csv"
OUT=ROOT/"output_next3_full";OUT.mkdir(parents=True,exist_ok=True)
PAGE_SIZE=40;MAX_PAGE=51;MAX_PRICE=1000000;MIN_BUCKET_WIDTH=50
SEARCH_CONC=10;DETAIL_CONC=4;RETRIES=6

def clean(s): return re.sub(r"\s+"," ",(s or "")).strip()
def ntext(el):
    if not el:return None
    m=re.search(r"([0-9][0-9,]*)",clean(el.get_text(" ",strip=True)))
    return int(m.group(1).replace(",","")) if m else None
def parse_search(txt):
    s=BeautifulSoup(txt,"html.parser");out=[]
    for i,li in enumerate(s.select("[data_gd_no]"),1):
        gd=li.get("data_gd_no")
        a=li.select_one("a[href*='goodscode']")
        title=li.select_one(".list_v2_title")
        brand=li.select_one(".common_ui_seller_brand")
        review=li.select_one(".rate_count")
        orig=li.select_one(".price_original_value")
        final=li.select_one(".price_final_value")
        img=li.select_one("img.thumbnail_image")
        out.append({"page_rank":i,"goods_code":gd,"product_url":a.get("href") if a else None,
          "product_name":clean(title.get_text(" ",strip=True)) if title else (img.get("alt") if img else None),
          "brand_text":clean(brand.get_text(" ",strip=True)) if brand else None,
          "review_count_search":ntext(review),"list_price_jpy_search":ntext(orig),"current_price_jpy_search":ntext(final),
          "image_url":img.get("src") if img else None})
    return out
def detail_parse(txt):
    def num(k):
        m=re.search(r'"'+re.escape(k)+r'"\s*:\s*([0-9.]+)',txt);return int(float(m.group(1))) if m else None
    def js(k):
        m=re.search(r'"'+re.escape(k)+r'"\s*:\s*"((?:\\.|[^"])*)"',txt)
        if not m:return None
        try:return json.loads('"'+m.group(1)+'"')
        except:return m.group(1)
    mini=js("minishopURL"); shop=None
    if mini:
        mm=re.search(r"/shop/([^/?#]+)",mini,re.I);shop=mm.group(1) if mm else None
    return {"cumulative_sales_count":num("total_sell_amt"),"detail_review_count":num("review_cnt"),
      "seller_id":js("enc_seller_cust_no"),"seller_shop":shop,"minishop_url":mini,"product_name_detail":js("gd_nm")}

async def main():
    with open(BRANDS,encoding="utf-8-sig") as f:brands=list(csv.DictReader(f))
    progress={"run_id":datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),"stage":"search","brands":{},"issues":[]}
    (OUT/"00_progress.json").write_text(json.dumps(progress,ensure_ascii=False,indent=2),encoding="utf-8")
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True,args=["--no-sandbox"]);c=await b.new_context(locale="ja-JP",timezone_id="Asia/Tokyo")
        sem=asyncio.Semaphore(SEARCH_CONC)
        async def page(kw,n,lo,hi):
            u=("https://www.qoo10.jp/gmkt.inc/Mobile/Search/MobileTotalSearchAppend.aspx?"
               f"search_type=SRP&page_no={n}&page_size={PAGE_SIZE}&sort_type=11&partial=on&affiliate_group=0"
               f"&qx_delivery_search_yn=N&eticket_search_yn=N&research_yn=Y&catalogue_yn=Y&plus_type=KW"
               f"&keyword={quote(kw)}&min_price={lo}&max_price={hi}&free_shipping_search_yn=N")
            async with sem:
                for a in range(RETRIES):
                    try:
                        r=await c.request.get(u,timeout=30000,headers={"Referer":"https://www.qoo10.jp/"})
                        if r.status==200:return parse_search(await r.text())
                    except: pass
                    await asyncio.sleep(.4*(a+1)+random.random()*.2)
            return []
        async def bucket(br,kw,lo,hi):
            last=await page(kw,51,lo,hi)
            if len(last)>=40 and hi-lo>MIN_BUCKET_WIDTH:
                mid=(lo+hi)//2
                return (await bucket(br,kw,lo,mid))+(await bucket(br,kw,mid,hi))
            if len(last)>=40:
                progress["issues"].append({"type":"UNRESOLVED_BUCKET_CAP","brand_id":br["brand_id"],"keyword":kw,"lo":lo,"hi":hi})
            arr=[]
            empty_streak=0
            for st in range(1,52,25):
                nums=list(range(st,min(52,st+25)))
                parts=await asyncio.gather(*[page(kw,n,lo,hi) for n in nums])
                for n,rows in zip(nums,parts):
                    if not rows:empty_streak+=1
                    else:
                        empty_streak=0
                        for r in rows:r.update({"brand_id":br["brand_id"],"brand_name_ko":br["brand_name_ko"],"keyword_used":kw,"price_bucket_min":lo,"price_bucket_max":hi,"search_page":n})
                        arr.extend(rows)
                if empty_streak>=3:break
            return arr
        raw=[]
        for br in brands:
            brrows=[]
            for kw in br["keywords"].split("|"):
                brrows+=await bucket(br,kw,0,MAX_PRICE)
            raw+=brrows
            progress["brands"][br["brand_id"]]={"raw_rows":len(brrows)}
            print("SEARCH_DONE",br["brand_id"],len(brrows))
        ded={}
        for r in raw:
            k=(r["brand_id"],r.get("goods_code"))
            if r.get("goods_code") and k not in ded:ded[k]=r
        uniq=list(ded.values())
        save(OUT/"01_search_raw.csv",raw);save(OUT/"02_unique_goods.csv",uniq)
        progress["stage"]="detail";progress["unique_goods_code_count"]=len(uniq)
        (OUT/"00_progress.json").write_text(json.dumps(progress,ensure_ascii=False,indent=2),encoding="utf-8")
        dsem=asyncio.Semaphore(DETAIL_CONC)
        async def detail(r):
            async with dsem:
                url=r.get("product_url") or f"https://m.qoo10.jp/gmkt.inc/Mobile/goods/goods.aspx?goodscode={r['goods_code']}"
                last={}
                for a in range(1,RETRIES+1):
                    try:
                        q=await c.request.get(url,timeout=30000,headers={"Referer":"https://www.qoo10.jp/","Cache-Control":"no-cache"})
                        txt=await q.text();d=detail_parse(txt)
                        if d["cumulative_sales_count"] is not None and d["seller_id"]:
                            return {**r,**d,"detail_status":"OK","attempt":a}
                        last={"http_status":q.status,"html_len":len(txt)}
                    except Exception as e:last={"detail_error":type(e).__name__}
                    await asyncio.sleep(.7*a+random.random()*.5)
                return {**r,**last,"detail_status":"FAILED","attempt":RETRIES}
        detailed=[]
        for st in range(0,len(uniq),200):
            detailed+=await asyncio.gather(*[detail(x) for x in uniq[st:st+200]])
            print("DETAIL",len(detailed),"/",len(uniq),"OK",sum(x.get("detail_status")=="OK" for x in detailed))
            progress["detail_done"]=len(detailed);progress["detail_ok"]=sum(x.get("detail_status")=="OK" for x in detailed)
            (OUT/"00_progress.json").write_text(json.dumps(progress,ensure_ascii=False,indent=2),encoding="utf-8")
            await asyncio.sleep(1)
        await b.close()
    save(OUT/"03_detail_all.csv",detailed)
    summary=[]
    for br in brands:
        g=[x for x in detailed if x["brand_id"]==br["brand_id"]]
        ok=[x for x in g if x.get("detail_status")=="OK"]
        total=sum(x.get("cumulative_sales_count") or 0 for x in ok)
        sellers=defaultdict(int)
        for x in ok:sellers[x.get("seller_id")]+=x.get("cumulative_sales_count") or 0
        summary.append({"brand_id":br["brand_id"],"brand_name_ko":br["brand_name_ko"],"unique_goods_count":len(g),"detail_ok_count":len(ok),
          "detail_coverage_pct":round(100*len(ok)/len(g),2) if g else 0,"observed_cumulative_sales_count":total,
          "distinct_seller_count":len(sellers),"selection_reason":br["selection_reason"]})
    save(OUT/"04_brand_summary.csv",summary)
    progress["stage"]="completed";progress["issues_count"]=len(progress["issues"])
    (OUT/"00_progress.json").write_text(json.dumps(progress,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(progress,ensure_ascii=False))
def save(path,rows):
    if not rows:return
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields:fields.append(k)
    with open(path,"w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(rows)
if __name__=="__main__":asyncio.run(main())