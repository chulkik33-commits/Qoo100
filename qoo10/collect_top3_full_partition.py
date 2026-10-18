import asyncio, csv, json, math, re, html as htmlmod
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parent
BRANDS=ROOT/"resell_brand_universe_top3.csv"
OUT=ROOT/"output_top3_full_partition"
OUT.mkdir(parents=True,exist_ok=True)

PAGE_SIZE=40
MAX_PAGE=51
SEARCH_CONCURRENCY=10
DETAIL_CONCURRENCY=20
RETRIES=3
MAX_PRICE=1000000
MIN_BUCKET_WIDTH=50

ALIASES={
 "MEDIHEAL":["メディヒール","mediheal","메디힐"],
 "JSM":["ジョンセンムル","jungsaemmool","jung saem mool","정샘물"],
 "TORRIDEN":["トリデン","torriden","토리든"],
}

def clean(s): return re.sub(r"\s+"," ",(s or "")).strip()
def strip_tags(s): return clean(htmlmod.unescape(re.sub(r"<[^>]+>"," ",s or "")))
def money(s):
    m=re.search(r"([0-9][0-9,]*)",s or "")
    return int(m.group(1).replace(",","")) if m else None

def parse_append_html(txt):
    soup=BeautifulSoup(txt,"html.parser")
    out=[]
    for i,li in enumerate(soup.select("li[data_gd_no]"),1):
        gd=li.get("data_gd_no")
        a=li.select_one("a[gd_no]") or li.select_one("a[href*='goodscode']")
        name=li.select_one("h3.tt")
        sold=li.select_one(".sld")
        rvw=li.select_one(".rvw")
        dele=li.select_one(".prc del")
        cur=li.select_one(".prc strong")
        ship=li.select_one(".shp_ntn")
        brand=li.select_one(".brand") or li.select_one(".txt_brand")
        out.append({
            "page_rank":i,"goods_code":gd,
            "product_url":a.get("href") if a else None,
            "product_name":clean(name.get_text(" ",strip=True)) if name else None,
            "sold_text":clean(sold.get_text(" ",strip=True)) if sold else None,
            "review_text":clean(rvw.get_text(" ",strip=True)) if rvw else None,
            "list_price_text":clean(dele.get_text(" ",strip=True)) if dele else None,
            "current_price_text":clean(cur.get_text(" ",strip=True)) if cur else None,
            "shipping_country":clean(ship.get_text(" ",strip=True)) if ship else None,
            "brand_text":clean(brand.get_text(" ",strip=True)) if brand else None,
        })
    return out

def detail_parse(txt):
    def num(key):
        m=re.search(r'"'+re.escape(key)+r'"\s*:\s*([0-9.]+)',txt)
        return int(float(m.group(1))) if m else None
    shop=None
    sm=re.search(r'<a[^>]*id=["\']aMobileShopTitle["\'][^>]*>(.*?)</a>',txt,re.S|re.I)
    if sm: shop=strip_tags(sm.group(1))
    official=bool(re.search(r'<span[^>]*id=["\']span_partial_seller["\'][^>]*>\s*公式ショップ\s*</span>',txt,re.S|re.I))
    sid=None
    em=re.search(r'"enc_seller_cust_no"\s*:\s*"([^"]+)"',txt)
    if em:sid=em.group(1)
    return num("total_sell_amt"),num("review_cnt"),shop,official,sid

async def retry_get(req,url):
    last=None
    for i in range(RETRIES):
        try:
            resp=await req.get(url,timeout=30000,headers={"Referer":"https://www.qoo10.jp/"})
            if resp.status==200:return resp
            last=RuntimeError(f"HTTP {resp.status}")
        except Exception as e:last=e
        await asyncio.sleep(0.6*(i+1))
    raise last or RuntimeError("request failed")

def endpoint(kw,page_no,minp,maxp):
    return ("https://www.qoo10.jp/gmkt.inc/Mobile/Search/MobileTotalSearchAppend.aspx?"
            f"search_type=SRP&page_no={page_no}&page_size={PAGE_SIZE}&sort_type=11&partial=on&affiliate_group=0"
            f"&qx_delivery_search_yn=N&eticket_search_yn=N&research_yn=Y&catalogue_yn=Y&plus_type=KW"
            f"&keyword={quote(kw)}&min_price={minp}&max_price={maxp}&free_shipping_search_yn=N")

async def main():
    with open(BRANDS,encoding="utf-8-sig") as f:brands=list(csv.DictReader(f))
    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    progress={"run_id":run_id,"stage":"init","brands":{},"issues":[]}
    (OUT/"00_progress.json").write_text(json.dumps(progress,ensure_ascii=False,indent=2),encoding="utf-8")

    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=["--no-sandbox"])
        ctx=await browser.new_context(locale="ja-JP",timezone_id="Asia/Tokyo")
        req=ctx.request
        sem=asyncio.Semaphore(SEARCH_CONCURRENCY)

        async def get_page(kw,pageno,lo,hi):
            async with sem:
                try:
                    resp=await retry_get(req,endpoint(kw,pageno,lo,hi))
                    txt=await resp.text()
                    return parse_append_html(txt)
                except Exception as e:
                    progress["issues"].append({"type":"PAGE_FETCH_ERROR","keyword":kw,"page":pageno,"min_price":lo,"max_price":hi,"error":type(e).__name__})
                    return []

        async def bucket_probe(kw,lo,hi):
            # Check page 51 first: if full, bucket is still capped and must split.
            rows=await get_page(kw,MAX_PAGE,lo,hi)
            return len(rows)

        async def collect_bucket(b,lo,hi,depth=0):
            kw=b["keyword_jp"]
            last_count=await bucket_probe(kw,lo,hi)
            if last_count>=PAGE_SIZE and (hi-lo)>MIN_BUCKET_WIDTH:
                mid=(lo+hi)//2
                left=await collect_bucket(b,lo,mid,depth+1)
                right=await collect_bucket(b,mid,hi,depth+1)  # overlap at boundary is intentional; goods_code dedupe removes it.
                return left+right
            if last_count>=PAGE_SIZE and (hi-lo)<=MIN_BUCKET_WIDTH:
                progress["issues"].append({"type":"UNRESOLVED_BUCKET_CAP","brand_id":b["brand_id"],"min_price":lo,"max_price":hi,"page51_count":last_count})
            allrows=[]
            empty_streak=0
            for start in range(1,MAX_PAGE+1,25):
                nums=list(range(start,min(MAX_PAGE+1,start+25)))
                parts=await asyncio.gather(*[get_page(kw,n,lo,hi) for n in nums])
                for n,rows in zip(nums,parts):
                    if rows:
                        empty_streak=0
                        for r in rows:
                            r.update({"brand_id":b["brand_id"],"brand_name_ko":b["brand_name_ko"],"price_bucket_min":lo,"price_bucket_max":hi,"search_page":n})
                            allrows.append(r)
                    else:
                        empty_streak+=1
                if empty_streak>=3:
                    break
            progress["brands"].setdefault(b["brand_id"],{}).setdefault("completed_buckets",0)
            progress["brands"][b["brand_id"]]["completed_buckets"]+=1
            (OUT/"00_progress.json").write_text(json.dumps(progress,ensure_ascii=False,indent=2),encoding="utf-8")
            return allrows

        search_rows=[]
        progress["stage"]="search_partition"
        for b in brands:
            progress["brands"][b["brand_id"]]={"completed_buckets":0}
            rows=await collect_bucket(b,0,MAX_PRICE)
            search_rows.extend(rows)
            progress["brands"][b["brand_id"]]["raw_rows"]=len(rows)
            print("BRAND_SEARCH_DONE",b["brand_id"],len(rows))
        # exact listing dedupe only
        dedup={}
        dups=0
        for r in search_rows:
            key=(r["brand_id"],r.get("goods_code"))
            if not r.get("goods_code"): continue
            if key in dedup: dups+=1
            else: dedup[key]=r
        unique=list(dedup.values())
        save=lambda path,rows: _save_csv(path,rows)
        save(OUT/"01_search_partition_raw.csv",search_rows)
        save(OUT/"02_unique_goods_code.csv",unique)

        progress["stage"]="detail"
        progress["unique_goods_code_count"]=len(unique)
        (OUT/"00_progress.json").write_text(json.dumps(progress,ensure_ascii=False,indent=2),encoding="utf-8")

        dsem=asyncio.Semaphore(DETAIL_CONCURRENCY)
        async def fetch_detail(r):
            u=r.get("product_url")
            if not u:return {**r,"detail_status":None}
            async with dsem:
                try:
                    resp=await retry_get(req,u)
                    txt=await resp.text()
                    sales,rv,shop,official,sid=detail_parse(txt)
                    return {**r,"detail_status":resp.status,"cumulative_sales_count":sales,"detail_review_count":rv,"shop_name":shop,"is_flagship":1 if official else 0,"seller_id":sid,"full_price_jpy":money(r.get("list_price_text")),"current_price_jpy":money(r.get("current_price_text"))}
                except Exception as e:
                    return {**r,"detail_status":None,"cumulative_sales_count":None,"detail_error":type(e).__name__}
        detailed=[]
        for start in range(0,len(unique),300):
            detailed.extend(await asyncio.gather(*[fetch_detail(r) for r in unique[start:start+300]]))
            progress["detail_done"]=len(detailed)
            (OUT/"00_progress.json").write_text(json.dumps(progress,ensure_ascii=False,indent=2),encoding="utf-8")
            print("DETAIL",len(detailed),"/",len(unique))
        await browser.close()

    save(OUT/"03_detail_all_unique.csv",detailed)

    # summaries
    bybrand=defaultdict(list)
    for r in detailed:bybrand[r["brand_id"]].append(r)
    brand_summary=[]; reseller_rows=[]
    for b in brands:
        bid=b["brand_id"]; rs=bybrand.get(bid,[])
        valid=[x for x in rs if x.get("cumulative_sales_count") is not None and x.get("is_flagship") is not None]
        total=sum(x["cumulative_sales_count"] for x in valid)
        fs=sum(x["cumulative_sales_count"] for x in valid if x["is_flagship"]==1)
        rr=total-fs
        brand_summary.append({
            "brand_id":bid,"brand_name_ko":b["brand_name_ko"],"unique_goods_code_count":len(rs),"detail_valid_count":len(valid),
            "observed_cumulative_sales_count":total,"flagship_sales_count":fs,"reseller_sales_count":rr,
            "flagship_sales_share_pct":round(100*fs/total,2) if total else None,"reseller_sales_share_pct":round(100*rr/total,2) if total else None,
            "sales_count_basis":"Qoo10 detail internal total_sell_amt interpreted as cumulative sold-item count",
            "dedupe_basis":"brand_id + goods_code only",
        })
        sellers=defaultdict(list)
        for x in valid:
            if x["is_flagship"]==0:sellers[x.get("shop_name") or x.get("seller_id") or "(unknown)"].append(x)
        ranked=[]
        for seller,items in sellers.items():
            st=sum(x["cumulative_sales_count"] for x in items)
            top=sorted(items,key=lambda z:z["cumulative_sales_count"],reverse=True)
            top3=sum(x["cumulative_sales_count"] for x in top[:3])
            ranked.append({"brand_id":bid,"seller_name":seller,"observed_sales_count":st,"listing_count":len(items),
                           "avg_sales_per_listing":round(st/len(items),2),"top3_sales_concentration_pct":round(100*top3/st,2) if st else None,
                           "top_product_1":top[0].get("product_name") if len(top)>0 else None,"top_product_1_sales_count":top[0].get("cumulative_sales_count") if len(top)>0 else None,
                           "top_product_2":top[1].get("product_name") if len(top)>1 else None,"top_product_2_sales_count":top[1].get("cumulative_sales_count") if len(top)>1 else None,
                           "top_product_3":top[2].get("product_name") if len(top)>2 else None,"top_product_3_sales_count":top[2].get("cumulative_sales_count") if len(top)>2 else None})
        ranked.sort(key=lambda x:x["observed_sales_count"],reverse=True)
        for i,x in enumerate(ranked[:10],1): x["reseller_rank"]=i; reseller_rows.append(x)
    save(OUT/"04_brand_summary.csv",brand_summary)
    save(OUT/"05_top10_resellers.csv",reseller_rows)

    progress["stage"]="completed"
    progress["raw_search_rows"]=len(search_rows); progress["duplicate_rows_same_goods_code"]=dups; progress["unique_goods_code_count"]=len(unique)
    (OUT/"00_progress.json").write_text(json.dumps(progress,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(progress,ensure_ascii=False))

def _save_csv(path,rows):
    if not rows:return
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields:fields.append(k)
    with open(path,"w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader(); w.writerows(rows)

if __name__=="__main__":asyncio.run(main())
