import asyncio, csv, html as htmlmod, json, math, re
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parent
BRANDS=ROOT/"resell_brand_universe.csv"
OUT=ROOT/"output_sales"
RAW=OUT/"raw"
OUT.mkdir(parents=True,exist_ok=True);RAW.mkdir(parents=True,exist_ok=True)
DETAIL_CONCURRENCY=16

GENERIC={"公式","正規品","送料無料","韓国","韓国コスメ","国内発送","即納","限定","new","qoo10","セット","set","本品","レフィル","リフィル","企画","メガ割","再入荷","お得","特価"}

def clean(s): return re.sub(r"\s+"," ",(s or "")).strip()
def nfloat(v):
    try:return float(v)
    except:return None
def nint(v):
    try:return int(float(v))
    except:return None

def sold_display_to_lower_bound(s):
    s=clean(s).replace("個販売","")
    if not s:return None
    if s.endswith("+"):
        try:return int(s[:-1].replace(",",""))
        except:return None
    try:return int(s.replace(",",""))
    except:return None

def strip_tags(s):
    return clean(htmlmod.unescape(re.sub(r"<[^>]+>"," ",s or "")))

def detail_parse(txt):
    m=re.search(r'"total_sell_amt"\s*:\s*([0-9.]+)',txt)
    total=int(float(m.group(1))) if m else None
    rv=re.search(r'"review_cnt"\s*:\s*([0-9.]+)',txt)
    review=int(float(rv.group(1))) if rv else None
    shop=None
    sm=re.search(r'<a[^>]*id=["\']aMobileShopTitle["\'][^>]*>(.*?)</a>',txt,re.S|re.I)
    if sm:shop=strip_tags(sm.group(1))
    official=bool(re.search(r'<span[^>]*id=["\']span_partial_seller["\'][^>]*>\s*公式ショップ\s*</span>',txt,re.S|re.I))
    seller_id=None
    em=re.search(r'"enc_seller_cust_no"\s*:\s*"([^"]+)"',txt)
    if em:seller_id=em.group(1)
    return total,review,shop,official,seller_id

def base_name(s):
    s=clean(s).lower()
    s=re.sub(r"【[^】]*】|\[[^\]]*\]|\([^)]*\)"," ",s)
    s=re.sub(r"[^0-9a-zぁ-んァ-ン一-龥가-힣]+"," ",s)
    return " ".join(t for t in s.split() if t not in GENERIC and len(t)>1)

def variant_signature(s):
    x=(s or "").lower();f=[]
    if re.search(r"レフィル|リフィル|refill",x):f.append("REFILL")
    if re.search(r"セット|set|企画|\+|付き|付属",x):f.append("SET")
    if re.search(r"ミニ|mini",x):f.append("MINI")
    nums=re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*(ml|g)",x)
    f += [a+b for a,b in nums]
    return "|".join(sorted(set(f))) or "BASE"

def similarity(a,b):
    ba,bb=base_name(a),base_name(b)
    if not ba or not bb:return 0
    ta,tb=set(ba.split()),set(bb.split())
    jac=len(ta&tb)/max(1,len(ta|tb))
    return .65*SequenceMatcher(None,ba,bb).ratio()+.35*jac

def percentile(vals,v,log=False):
    xs=[x for x in vals if x is not None]
    if v is None or not xs:return 0
    if log:xs=[math.log1p(max(0,x)) for x in xs];v=math.log1p(max(0,v))
    xs=sorted(xs);below=sum(x<v for x in xs);eq=sum(x==v for x in xs)
    return round(100*(below+.5*eq)/len(xs),2)

def read_brands():
    with open(BRANDS,encoding="utf-8-sig") as f:return [r for r in csv.DictReader(f) if r.get("active","1")=="1"]

def save_csv(path,rows):
    if not rows:return
    with open(path,"w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0].keys()),extrasaction="ignore");w.writeheader();w.writerows(rows)

async def collect_search(page,b):
    kw=b["keyword_jp"]
    url=f"https://www.qoo10.jp/gmkt.inc/Mobile/Search/DynamicAd.aspx?keyword={quote(kw)}&page_no=1&sortType=SORT_RANK_POINT"
    resp=await page.goto(url,wait_until="domcontentloaded",timeout=60000);await page.wait_for_timeout(1800)
    items=await page.evaluate("""() => [...document.querySelectorAll('#div_mobile_list li[data_gd_no]')].map((li,i)=>{
      const a=li.querySelector('a[gd_no]'),name=li.querySelector('h3.tt'),sold=li.querySelector('.sld'),rvw=li.querySelector('.rvw'),prc=li.querySelector('.prc'),ship=li.querySelector('.shp_ntn');
      const del=li.querySelector('.prc del'),cur=li.querySelector('.prc strong');
      return {rank:i+1,goods_code:li.getAttribute('data_gd_no'),product_url:a?a.href:null,product_name:name?name.innerText.trim():null,sold_text:sold?sold.innerText.trim():null,review_text:rvw?rvw.innerText.trim():null,list_price_text:del?del.innerText.trim():null,current_price_text:cur?cur.innerText.trim():null,shipping_country:ship?ship.innerText.trim():null};
    })""")
    return resp.status if resp else None,page.url,items,await page.content()

async def main():
    brands=read_brands();run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ");runraw=RAW/run_id;runraw.mkdir(parents=True,exist_ok=True)
    search_rows=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=["--no-sandbox"])
        ctx=await browser.new_context(locale="ja-JP",timezone_id="Asia/Tokyo",viewport={"width":430,"height":1200})
        page=await ctx.new_page()
        for b in brands:
            try:
                status,url,items,html=await collect_search(page,b)
                (runraw/f"{b['brand_id']}_search.html").write_text(html,encoding="utf-8")
                print("SEARCH",b["brand_id"],status,len(items))
                for x in items:
                    x.update({"snapshot_utc":datetime.now(timezone.utc).isoformat(),"brand_id":b["brand_id"],"brand_name_ko":b["brand_name_ko"],"selection_axis":b.get("selection_axis"),"domestic_index":b.get("domestic_index"),"keyword_jp":b["keyword_jp"],"search_status":status})
                    x["recent_sold_lower_bound"]=sold_display_to_lower_bound(x.get("sold_text"))
                    search_rows.append(x)
            except Exception as e:print("SEARCH_ERROR",b["brand_id"],type(e).__name__,str(e)[:200])

        sem=asyncio.Semaphore(DETAIL_CONCURRENCY)
        async def fetch_detail(r):
            async with sem:
                try:
                    resp=await ctx.request.get(r["product_url"],timeout=30000,headers={"Referer":"https://www.qoo10.jp/"})
                    txt=await resp.text()
                    total,review,shop,official,seller_id=detail_parse(txt)
                    return {**r,"detail_status":resp.status,"cumulative_sales_units":total,"detail_review_count":review,"shop_name":shop,"is_flagship":1 if official else 0,"seller_id":seller_id}
                except Exception as e:
                    return {**r,"detail_status":None,"cumulative_sales_units":None,"detail_review_count":None,"shop_name":None,"is_flagship":None,"seller_id":None,"detail_error":type(e).__name__}
        details=[]
        batch=250
        for i in range(0,len(search_rows),batch):
            part=await asyncio.gather(*[fetch_detail(r) for r in search_rows[i:i+batch]])
            details.extend(part);print("DETAIL",len(details),"/",len(search_rows))
        await browser.close()

    # Dedup exact goods codes across accidental duplicates
    dedup={}
    for r in details:
        key=(r["brand_id"],r["goods_code"])
        old=dedup.get(key)
        if old is None or (r.get("cumulative_sales_units") or 0)>(old.get("cumulative_sales_units") or 0):dedup[key]=r
    details=list(dedup.values())
    save_csv(OUT/"raw_sales_listings.csv",details)

    # Brand actual-sales share
    brand_rows=[]
    by=defaultdict(list)
    for r in details:by[r["brand_id"]].append(r)
    for bid,rs in by.items():
        valid=[r for r in rs if r.get("cumulative_sales_units") is not None and r.get("is_flagship") is not None]
        total=sum(r["cumulative_sales_units"] for r in valid)
        flag=sum(r["cumulative_sales_units"] for r in valid if r["is_flagship"]==1)
        res=total-flag
        sellers=defaultdict(int)
        for r in valid:
            if r["is_flagship"]==0:sellers[r.get("shop_name") or r.get("seller_id") or "(unknown)"]+=r["cumulative_sales_units"]
        ordered=sorted(sellers.values(),reverse=True)
        meta=rs[0]
        brand_rows.append({"brand_id":bid,"brand_name_ko":meta["brand_name_ko"],"selection_axis":meta.get("selection_axis"),"domestic_index":float(meta.get("domestic_index") or 0),"search_listings_observed":len(rs),"detail_valid_listings":len(valid),"detail_coverage_pct":round(100*len(valid)/len(rs),2) if rs else 0,"observed_cumulative_sales_units":total,"flagship_sales_units":flag,"reseller_sales_units":res,"flagship_sales_share_pct":round(100*flag/total,2) if total else None,"reseller_sales_share_pct":round(100*res/total,2) if total else None,"reseller_seller_count":len(sellers),"reseller_top3_sales_concentration_pct":round(100*sum(ordered[:3])/res,2) if res else None,"sales_metric_basis":"QOO10_DETAIL_total_sell_amt","coverage_scope":"Qoo10 mobile brand-search ranked listings page 1"})
    salesvals=[r["observed_cumulative_sales_units"] for r in brand_rows]
    sellercounts=[r["reseller_seller_count"] for r in brand_rows]
    conc=[r["reseller_top3_sales_concentration_pct"] for r in brand_rows if r["reseller_top3_sales_concentration_pct"] is not None]
    for r in brand_rows:
        r["jp_sales_demand_index"]=percentile(salesvals,r["observed_cumulative_sales_units"],log=True)
        share=r["reseller_sales_share_pct"] or 0
        seller_score=percentile(sellercounts,r["reseller_seller_count"])
        c=r["reseller_top3_sales_concentration_pct"]
        conc_score=100-percentile(conc,c) if c is not None and conc else 0
        r["reseller_access_index"]=round(.60*share+.20*seller_score+.20*conc_score,2)
        r["cross_market_brand_index"]=round(.25*r["domestic_index"]+.45*r["jp_sales_demand_index"]+.30*r["reseller_access_index"],2)
    brand_rows.sort(key=lambda x:x["cross_market_brand_index"],reverse=True)
    for i,r in enumerate(brand_rows,1):r["cross_market_rank"]=i
    save_csv(OUT/"brand_sales_share_index.csv",brand_rows)

    # SKU clustering and actual-sales sourcing index
    sku_rows=[]
    for bid,rs in by.items():
        units=[]
        for r in rs:
            if r.get("cumulative_sales_units") is None:continue
            units.append({"name":r.get("product_name") or "","variant":variant_signature(r.get("product_name") or ""),"rows":[r]})
        clusters=[]
        for u in sorted(units,key=lambda x:len(base_name(x["name"])),reverse=True):
            best=None;score=0
            for c in clusters:
                if u["variant"]!=c["variant"]:continue
                sc=similarity(u["name"],c["canonical"])
                if sc>score:score=sc;best=c
            if best is not None and score>=.72:best["rows"]+=u["rows"]
            else:clusters.append({"canonical":u["name"],"variant":u["variant"],"rows":u["rows"][:]})
        for c in clusters:
            rr=c["rows"];total=sum(r["cumulative_sales_units"] for r in rr);res=sum(r["cumulative_sales_units"] for r in rr if r.get("is_flagship")==0);flag=total-res
            shops={r.get("shop_name") or r.get("seller_id") for r in rr if r.get("is_flagship")==0}
            rep=max(rr,key=lambda x:x.get("cumulative_sales_units") or 0)
            sku_rows.append({"brand_id":bid,"brand_name_ko":rep["brand_name_ko"],"canonical_product_name":rep.get("product_name"),"variant_signature":c["variant"],"listing_count":len(rr),"observed_cumulative_sales_units":total,"flagship_sales_units":flag,"reseller_sales_units":res,"reseller_sales_share_pct":round(100*res/total,2) if total else None,"reseller_seller_count":len(shops),"representative_goods_code":rep.get("goods_code"),"representative_shop":rep.get("shop_name"),"representative_full_price_jpy":nint(re.sub(r"[^0-9]","",rep.get("list_price_text") or "")),"sales_metric_basis":"QOO10_DETAIL_total_sell_amt"})
    sv=[x["observed_cumulative_sales_units"] for x in sku_rows];ss=[x["reseller_seller_count"] for x in sku_rows]
    bidx={r["brand_id"]:r["cross_market_brand_index"] for r in brand_rows}
    for x in sku_rows:
        sales_score=percentile(sv,x["observed_cumulative_sales_units"],log=True)
        share=x["reseller_sales_share_pct"] or 0
        seller_score=percentile(ss,x["reseller_seller_count"])
        brand_score=bidx.get(x["brand_id"],0)
        x["pre_cost_sourcing_index"]=round(.50*sales_score+.30*share+.10*seller_score+.10*brand_score,2)
    sku_rows.sort(key=lambda x:x["pre_cost_sourcing_index"],reverse=True)
    for i,x in enumerate(sku_rows,1):x["pre_cost_rank"]=i
    save_csv(OUT/"sku_sales_share_index.csv",sku_rows)
    save_csv(OUT/"candidate20_sales_based.csv",sku_rows[:20])

    meta={"run_id":run_id,"brand_count":len(brands),"search_listing_rows":len(search_rows),"detail_rows":len(details),"brand_rows":len(brand_rows),"sku_rows":len(sku_rows),"basis":"Qoo10 mobile search sold-count discovery + detail page internal total_sell_amt interpreted as cumulative seller-listing sales units","coverage":"ranked mobile brand-search page 1 per brand; not all long-tail search pages"}
    (OUT/"sales_run_meta.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(meta,ensure_ascii=False))

if __name__=="__main__":asyncio.run(main())
