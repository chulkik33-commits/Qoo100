import asyncio, csv, json, math, re, html as htmlmod
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parent
BRANDS=ROOT/"resell_brand_universe_top3.csv"
OUT=ROOT/"output_top3_census"
RAW=OUT/"raw"
OUT.mkdir(parents=True,exist_ok=True); RAW.mkdir(parents=True,exist_ok=True)

PAGE_SIZE=40
SEARCH_CONCURRENCY=12
DETAIL_CONCURRENCY=20
RETRIES=3

ALIASES={
 "MEDIHEAL":["メディヒール","mediheal","메디힐"],
 "JSM":["ジョンセンムル","jungsaemmool","jung saem mool","정샘물"],
 "TORRIDEN":["トリデン","torriden","토리든"],
}

def clean(s): return re.sub(r"\s+"," ",(s or "")).strip()
def nint(v):
    try:return int(float(v))
    except:return None
def money(s):
    m=re.search(r"([0-9][0-9,]*)",s or "")
    return int(m.group(1).replace(",","")) if m else None
def strip_tags(s): return clean(htmlmod.unescape(re.sub(r"<[^>]+>"," ",s or "")))

def parse_search_count_html(txt):
    soup=BeautifulSoup(txt,"html.parser")
    ship={}
    for a in soup.select("a.local[data-nation_code]"):
        code=a.get("data-nation_code") or "ALL"
        n=a.select_one(".num")
        if n:
            m=re.search(r"([0-9][0-9,]*)",n.get_text(" ",strip=True))
            if m and code not in ship: ship[code]=int(m.group(1).replace(",",""))
    return ship

def parse_append_html(txt):
    soup=BeautifulSoup(txt,"html.parser")
    out=[]
    nodes=soup.select("li[data_gd_no]")
    for i,li in enumerate(nodes,1):
        gd=li.get("data_gd_no")
        a=li.select_one("a[gd_no]") or li.select_one("a[href*='goodscode']")
        name=li.select_one("h3.tt")
        sold=li.select_one(".sld")
        rvw=li.select_one(".rvw")
        prc=li.select_one(".prc")
        dele=li.select_one(".prc del")
        cur=li.select_one(".prc strong")
        ship=li.select_one(".shp_ntn")
        brand=li.select_one(".brand") or li.select_one(".txt_brand")
        out.append({
            "page_rank":i,
            "goods_code":gd,
            "product_url":a.get("href") if a else None,
            "product_name":clean(name.get_text(" ",strip=True)) if name else None,
            "sold_text":clean(sold.get_text(" ",strip=True)) if sold else None,
            "review_text":clean(rvw.get_text(" ",strip=True)) if rvw else None,
            "list_price_text":clean(dele.get_text(" ",strip=True)) if dele else None,
            "current_price_text":clean(cur.get_text(" ",strip=True)) if cur else (clean(prc.get_text(" ",strip=True)) if prc else None),
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

def brand_relevance(r):
    bid=r["brand_id"]
    text=" ".join([r.get("product_name") or "",r.get("brand_text") or ""]).lower()
    aliases=ALIASES.get(bid,[])
    hit=any(a.lower() in text for a in aliases)
    # Search result came from the brand keyword; retain rows without visible brand text as UNKNOWN instead of dropping.
    if hit:return "MATCH"
    multi=bool(re.search(r"福袋|lucky\s*box|ブランド.*選べる|選べる.*ブランド",text,re.I))
    return "MIXED_OR_NOISE" if multi else "UNCONFIRMED"

def sold_lower_bound(s):
    s=clean(s).replace("個販売","").replace("販売","").strip()
    if not s:return None
    s=s.rstrip("+")
    try:return int(s.replace(",",""))
    except:return None

def save_csv(path,rows):
    if not rows:return
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields:fields.append(k)
    with open(path,"w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader();w.writerows(rows)

def canonical_key(name,bid):
    s=(name or "").lower()
    for a in ALIASES.get(bid,[]):s=s.replace(a.lower()," ")
    s=re.sub(r"【[^】]*】|\[[^\]]*\]|\([^)]*\)"," ",s)
    s=re.sub(r"公式|正規品|送料無料|韓国コスメ|メガ割|限定|new|即納"," ",s,flags=re.I)
    s=re.sub(r"[^0-9a-zぁ-んァ-ン一-龥가-힣]+"," ",s)
    toks=[t for t in s.split() if len(t)>1]
    # keep capacity/count tokens to avoid collapsing sets/refills too aggressively
    return " ".join(toks[:18])

async def retry_get(req,url,timeout=30000):
    last=None
    for i in range(RETRIES):
        try:
            resp=await req.get(url,timeout=timeout,headers={"Referer":"https://www.qoo10.jp/"})
            if resp.status==200:return resp
            last=RuntimeError(f"HTTP {resp.status}")
        except Exception as e:last=e
        await asyncio.sleep(0.5*(i+1))
    raise last or RuntimeError("request failed")

async def main():
    with open(BRANDS,encoding="utf-8-sig") as f:brands=list(csv.DictReader(f))
    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    runraw=RAW/run_id;runraw.mkdir(parents=True,exist_ok=True)

    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=["--no-sandbox"])
        ctx=await browser.new_context(locale="ja-JP",timezone_id="Asia/Tokyo",viewport={"width":430,"height":1200})
        page=await ctx.new_page()

        counts={}
        for b in brands:
            kw=b["keyword_jp"]
            url=f"https://www.qoo10.jp/s/{quote(kw)}?keyword={quote(kw)}"
            await page.goto(url,wait_until="domcontentloaded",timeout=60000);await page.wait_for_timeout(1800)
            html=await page.content(); (runraw/f"{b['brand_id']}_count.html").write_text(html,encoding="utf-8")
            ship=parse_search_count_html(html)
            total=ship.get("ALL")
            counts[b["brand_id"]]={
                "search_total_count":total,
                "search_domestic_jp_count":ship.get("JP"),
                "search_korea_count":ship.get("KR"),
                "search_other_count":(total-(ship.get("JP") or 0)-(ship.get("KR") or 0)) if total is not None else None,
            }
            print("COUNT",b["brand_id"],counts[b["brand_id"]])

        search_rows=[]
        sem=asyncio.Semaphore(SEARCH_CONCURRENCY)
        async def fetch_page(b,page_no):
            async with sem:
                kw=b["keyword_jp"]
                u=("https://www.qoo10.jp/gmkt.inc/Mobile/Search/MobileTotalSearchAppend.aspx?"
                   f"search_type=SRP&page_no={page_no}&page_size={PAGE_SIZE}&sort_type=11&partial=on&affiliate_group=0"
                   f"&qx_delivery_search_yn=N&eticket_search_yn=N&research_yn=Y&catalogue_yn=Y&plus_type=KW"
                   f"&keyword={quote(kw)}&min_price=0&max_price=0&free_shipping_search_yn=N")
                try:
                    resp=await retry_get(ctx.request,u,30000)
                    txt=await resp.text()
                    rows=parse_append_html(txt)
                    for r in rows:
                        r.update({"brand_id":b["brand_id"],"brand_name_ko":b["brand_name_ko"],"selection_axis":b.get("selection_axis"),"domestic_index":b.get("domestic_index"),"search_page":page_no,"page_size":PAGE_SIZE,"global_rank":(page_no-1)*PAGE_SIZE+(r["page_rank"] or 0),"recent_sales_ui_lower_bound":sold_lower_bound(r.get("sold_text"))})
                        r["brand_relevance_status"]=brand_relevance(r)
                    return rows
                except Exception as e:
                    print("PAGE_ERR",b["brand_id"],page_no,type(e).__name__,str(e)[:100]);return []

        for b in brands:
            total=counts[b["brand_id"]].get("search_total_count") or 0
            pages=max(1,math.ceil(total/PAGE_SIZE))
            print("PAGES",b["brand_id"],pages)
            for start in range(1,pages+1,50):
                tasks=[fetch_page(b,n) for n in range(start,min(pages+1,start+50))]
                parts=await asyncio.gather(*tasks)
                for part in parts:search_rows.extend(part)
                print("SEARCH_PROGRESS",b["brand_id"],min(pages,start+49),"/",pages)

        # exact listing dedupe only: same brand + same goods_code
        raw_search_count=len(search_rows)
        dedup={}
        duplicates=0
        for r in search_rows:
            key=(r["brand_id"],r.get("goods_code"))
            if key in dedup:duplicates+=1
            else:dedup[key]=r
        unique=list(dedup.values())
        save_csv(OUT/"01_search_all_raw.csv",search_rows)
        save_csv(OUT/"02_search_unique_goods.csv",unique)

        # Detailed fetch for all unique listings with product URL.
        dsem=asyncio.Semaphore(DETAIL_CONCURRENCY)
        async def fetch_detail(r):
            if not r.get("product_url"):
                return {**r,"detail_status":None,"cumulative_sales_count":None,"detail_review_count":None,"shop_name":None,"is_flagship":None,"seller_id":None}
            async with dsem:
                try:
                    resp=await retry_get(ctx.request,r["product_url"],30000)
                    txt=await resp.text()
                    total,rv,shop,official,sid=detail_parse(txt)
                    return {**r,"detail_status":resp.status,"cumulative_sales_count":total,"detail_review_count":rv,"shop_name":shop,"is_flagship":1 if official else 0,"seller_id":sid,"full_price_jpy":money(r.get("list_price_text")),"current_price_jpy":money(r.get("current_price_text"))}
                except Exception as e:
                    return {**r,"detail_status":None,"cumulative_sales_count":None,"detail_review_count":None,"shop_name":None,"is_flagship":None,"seller_id":None,"detail_error":type(e).__name__}

        detailed=[]
        for start in range(0,len(unique),300):
            part=await asyncio.gather(*[fetch_detail(r) for r in unique[start:start+300]])
            detailed.extend(part);print("DETAIL_PROGRESS",len(detailed),"/",len(unique))
        await browser.close()

    save_csv(OUT/"03_detail_all_unique.csv",detailed)

    # Brand summary
    brand_summary=[]
    bybrand=defaultdict(list)
    for r in detailed:bybrand[r["brand_id"]].append(r)
    for b in brands:
        bid=b["brand_id"];rs=bybrand.get(bid,[])
        valid=[r for r in rs if r.get("cumulative_sales_count") is not None and r.get("is_flagship") is not None]
        total_sales=sum(r["cumulative_sales_count"] for r in valid)
        flag_sales=sum(r["cumulative_sales_count"] for r in valid if r["is_flagship"]==1)
        res_sales=total_sales-flag_sales
        match=sum(r.get("brand_relevance_status")=="MATCH" for r in rs)
        noise=sum(r.get("brand_relevance_status")=="MIXED_OR_NOISE" for r in rs)
        unconf=sum(r.get("brand_relevance_status")=="UNCONFIRMED" for r in rs)
        mc=counts[bid]
        brand_summary.append({
            "brand_id":bid,"brand_name_ko":b["brand_name_ko"],
            "search_total_count":mc.get("search_total_count"),"search_domestic_jp_count":mc.get("search_domestic_jp_count"),"search_korea_count":mc.get("search_korea_count"),"search_other_count":mc.get("search_other_count"),
            "raw_search_rows":sum(1 for r in search_rows if r["brand_id"]==bid),
            "unique_goods_code_count":len(rs),
            "detail_valid_count":len(valid),
            "detail_coverage_pct":round(100*len(valid)/len(rs),2) if rs else 0,
            "brand_match_count":match,"unconfirmed_count":unconf,"mixed_or_noise_count":noise,
            "observed_cumulative_sales_count":total_sales,
            "flagship_sales_count":flag_sales,
            "reseller_sales_count":res_sales,
            "flagship_sales_share_pct":round(100*flag_sales/total_sales,2) if total_sales else None,
            "reseller_sales_share_pct":round(100*res_sales/total_sales,2) if total_sales else None,
            "sales_count_basis":"Qoo10 detail internal total_sell_amt interpreted as cumulative sold-item count",
            "dedupe_basis":"brand_id + goods_code only; different goods_code listings are never deduplicated",
        })
    save_csv(OUT/"04_brand_census_summary.csv",brand_summary)

    # Top reseller 10 per brand, cumulative sales first.
    reseller_rows=[]
    strategy_rows=[]
    for bid,rs in bybrand.items():
        sellers=defaultdict(list)
        for r in rs:
            if r.get("is_flagship")==0 and r.get("cumulative_sales_count") is not None:
                sellers[r.get("shop_name") or r.get("seller_id") or "(unknown)"].append(r)
        ranked=[]
        for seller,rr in sellers.items():
            total=sum(x.get("cumulative_sales_count") or 0 for x in rr)
            rev=sum(x.get("detail_review_count") or 0 for x in rr)
            top=sorted(rr,key=lambda x:x.get("cumulative_sales_count") or 0,reverse=True)
            top3=sum((x.get("cumulative_sales_count") or 0) for x in top[:3])
            prices=[x.get("current_price_jpy") for x in rr if x.get("current_price_jpy")]
            ranked.append({
                "brand_id":bid,"seller_name":seller,"observed_sales_count":total,"listing_count":len(rr),
                "review_count_sum":rev,"avg_sales_per_listing":round(total/len(rr),2) if rr else 0,
                "avg_current_price_jpy":round(sum(prices)/len(prices),2) if prices else None,
                "top3_sku_sales_concentration_pct":round(100*top3/total,2) if total else None,
                "top_product_1":top[0].get("product_name") if len(top)>0 else None,"top_product_1_sales_count":top[0].get("cumulative_sales_count") if len(top)>0 else None,
                "top_product_2":top[1].get("product_name") if len(top)>1 else None,"top_product_2_sales_count":top[1].get("cumulative_sales_count") if len(top)>1 else None,
                "top_product_3":top[2].get("product_name") if len(top)>2 else None,"top_product_3_sales_count":top[2].get("cumulative_sales_count") if len(top)>2 else None,
            })
        ranked.sort(key=lambda x:x["observed_sales_count"],reverse=True)
        for i,r in enumerate(ranked[:10],1):
            r["reseller_rank"]=i
            reseller_rows.append(r)
    save_csv(OUT/"05_top10_resellers.csv",reseller_rows)

    # Conservative SKU index using normalized canonical keys; report both found vs unverified.
    sku_groups=defaultdict(list)
    for r in detailed:
        if r.get("cumulative_sales_count") is None:continue
        key=canonical_key(r.get("product_name") or "",r["brand_id"])
        if key:sku_groups[(r["brand_id"],key)].append(r)
    sku_rows=[]
    for (bid,key),rr in sku_groups.items():
        total=sum(x["cumulative_sales_count"] for x in rr)
        flag=[x for x in rr if x.get("is_flagship")==1]
        res=[x for x in rr if x.get("is_flagship")==0]
        fs=sum(x["cumulative_sales_count"] for x in flag)
        rs=sum(x["cumulative_sales_count"] for x in res)
        rep=max(rr,key=lambda x:x["cumulative_sales_count"])
        status="BOTH_FOUND" if flag and res else ("FLAGSHIP_ONLY" if flag else "RESELLER_ONLY_UNVERIFIED")
        sku_rows.append({
            "brand_id":bid,"canonical_key":key,"canonical_product_name":rep.get("product_name"),
            "listing_count":len(rr),"flagship_listing_count":len(flag),"reseller_listing_count":len(res),
            "official_presence_status":status,"observed_cumulative_sales_count":total,
            "flagship_sales_count":fs if flag else None,"reseller_sales_count":rs,
            "reseller_sales_share_pct":round(100*rs/total,2) if total and flag and res else None,
            "representative_goods_code":rep.get("goods_code"),"representative_seller":rep.get("shop_name"),
            "mapping_rule":"strict normalized-title key; RESELLER_ONLY_UNVERIFIED never treated as 100% reseller share"
        })
    sku_rows.sort(key=lambda x:x["observed_cumulative_sales_count"],reverse=True)
    save_csv(OUT/"06_sku_census_index.csv",sku_rows)
    verified=[x for x in sku_rows if x["official_presence_status"]=="BOTH_FOUND"]
    save_csv(OUT/"07_sku_verified_both_found.csv",verified)

    meta={
        "run_id":run_id,"brands":[b["brand_id"] for b in brands],"page_size":PAGE_SIZE,
        "raw_search_rows":raw_search_count,"duplicate_rows_same_goods_code":duplicates,
        "unique_goods_code_rows":len(unique),"detail_rows":len(detailed),
        "search_method":"Qoo10 MobileTotalSearchAppend.aspx true pagination discovered from browser network requests",
        "dedupe_rule":"same brand_id + same goods_code only",
        "sales_basis":"Qoo10 detail internal total_sell_amt interpreted as cumulative sold-item count",
        "top_reseller_rule":"exclude flagship; rank by summed cumulative_sales_count across observed unique listings"
    }
    (OUT/"00_run_meta.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(meta,ensure_ascii=False))

if __name__=="__main__":asyncio.run(main())
