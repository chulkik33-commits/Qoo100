import asyncio, csv, html as htmlmod, json, math, re
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parent
BRANDS=ROOT/"resell_brand_universe_top3.csv"
OUT=ROOT/"output_top3_deep"
RAW=OUT/"raw"
OUT.mkdir(parents=True,exist_ok=True);RAW.mkdir(parents=True,exist_ok=True)
PAGES=5
DETAIL_CONCURRENCY=12

DROP_WORDS={"公式","正規品","送料無料","韓国","韓国コスメ","国内発送","即納","限定","new","qoo10","セット","set","本品","レフィル","リフィル","企画","メガ割","再入荷","お得","特価","選べる","単品","日本限定","プレゼント","gift","best"}

def clean(s): return re.sub(r"\s+"," ",(s or "")).strip()
def strip_tags(s): return clean(htmlmod.unescape(re.sub(r"<[^>]+>"," ",s or "")))
def nint(v):
    try:return int(float(v))
    except:return None
def money(s):
    m=re.search(r"([0-9][0-9,]*)",s or "")
    return int(m.group(1).replace(",","")) if m else None
def sold_lb(s):
    s=clean(s).replace("個販売","")
    if not s:return None
    s=s.rstrip("+")
    try:return int(s.replace(",",""))
    except:return None

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

def normalize_title(s,brand_ko):
    s=clean(s).lower().replace(brand_ko.lower()," ")
    s=re.sub(r"【[^】]*】|\[[^\]]*\]|\([^)]*\)"," ",s)
    s=re.sub(r"[^0-9a-zぁ-んァ-ン一-龥가-힣]+"," ",s)
    toks=[t for t in s.split() if t not in DROP_WORDS and len(t)>1]
    return " ".join(toks)

def capacities(s):
    x=(s or "").lower()
    return sorted(set(a+b for a,b in re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*(ml|g)",x)))

def variant_flags(s):
    x=(s or "").lower();f=set()
    if re.search(r"レフィル|リフィル|refill",x):f.add("REFILL")
    if re.search(r"セット|set|企画|\+|付き|付属|2個|2本|ダブル",x):f.add("SET")
    if re.search(r"ミニ|mini",x):f.add("MINI")
    return f

def sim(a,b,brand):
    aa,bb=normalize_title(a,brand),normalize_title(b,brand)
    if not aa or not bb:return 0
    ta,tb=set(aa.split()),set(bb.split())
    jac=len(ta&tb)/max(1,len(ta|tb))
    seq=SequenceMatcher(None,aa,bb).ratio()
    ca,cb=set(capacities(a)),set(capacities(b))
    cap_penalty=0
    if ca and cb and not (ca&cb): cap_penalty=.18
    fa,fb=variant_flags(a),variant_flags(b)
    set_penalty=.10 if (("SET" in fa) != ("SET" in fb)) else 0
    return max(.62*seq+.38*jac-cap_penalty-set_penalty,0)


def percentile(vals,v,log=False):
    xs=[x for x in vals if x is not None]
    if v is None or not xs:return 0
    if log:
        xs=[math.log1p(max(0,x)) for x in xs]
        v=math.log1p(max(0,v))
    xs=sorted(xs)
    below=sum(x<v for x in xs)
    eq=sum(x==v for x in xs)
    return round(100*(below+0.5*eq)/len(xs),2)

def save_csv(path,rows):
    if not rows:return
    with open(path,"w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0].keys()),extrasaction="ignore");w.writeheader();w.writerows(rows)

def read_brands():
    with open(BRANDS,encoding="utf-8-sig") as f:return list(csv.DictReader(f))


async def collect_market_counts(page,b):
    kw=b["keyword_jp"]
    url=f"https://www.qoo10.jp/s/{quote(kw)}?keyword={quote(kw)}"
    resp=await page.goto(url,wait_until="domcontentloaded",timeout=60000)
    await page.wait_for_timeout(1800)
    data=await page.evaluate("""() => {
      const c=s=>(s||'').replace(/\\s+/g,' ').trim();
      const ship={};
      for(const a of document.querySelectorAll('a.local[data-nation_code]')){
        const code=a.getAttribute('data-nation_code')||'ALL';
        const n=a.querySelector('.num');
        if(!(code in ship)) ship[code]=c(n?n.textContent:'');
      }
      return {ship};
    }""")
    def p(v):
        m=re.search(r"([0-9][0-9,]*)",str(v or ""))
        return int(m.group(1).replace(",","")) if m else None
    allc=p(data["ship"].get("ALL"))
    jpc=p(data["ship"].get("JP"))
    krc=p(data["ship"].get("KR"))
    other=(allc-(jpc or 0)-(krc or 0)) if allc is not None else None
    return {"search_total_count":allc,"search_domestic_jp_count":jpc,"search_korea_count":krc,"search_other_count":other,"search_count_status":resp.status if resp else None}

async def search_page(page,b,pageno):
    kw=b["keyword_jp"]
    url=f"https://www.qoo10.jp/gmkt.inc/Mobile/Search/DynamicAd.aspx?keyword={quote(kw)}&page_no={pageno}&sortType=SORT_RANK_POINT"
    resp=await page.goto(url,wait_until="domcontentloaded",timeout=60000); await page.wait_for_timeout(1600)
    rows=await page.evaluate("""() => [...document.querySelectorAll('#div_mobile_list li[data_gd_no]')].map((li,i)=>{
      const a=li.querySelector('a[gd_no]'),n=li.querySelector('h3.tt'),s=li.querySelector('.sld'),rv=li.querySelector('.rvw'),p=li.querySelector('.prc'),del=li.querySelector('.prc del'),cur=li.querySelector('.prc strong'),ship=li.querySelector('.shp_ntn');
      return {page_rank:i+1,goods_code:li.getAttribute('data_gd_no'),product_url:a?a.href:null,product_name:n?n.innerText.trim():null,sold_text:s?s.innerText.trim():null,review_text:rv?rv.innerText.trim():null,list_price_text:del?del.innerText.trim():null,current_price_text:cur?cur.innerText.trim():null,shipping_country:ship?ship.innerText.trim():null};
    })""")
    return resp.status if resp else None,rows,await page.content()

async def main():
    brands=read_brands();run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    runraw=RAW/run_id;runraw.mkdir(parents=True,exist_ok=True)
    search_rows=[]
    market_counts={}
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=["--no-sandbox"])
        ctx=await browser.new_context(locale="ja-JP",timezone_id="Asia/Tokyo",viewport={"width":430,"height":1200})
        page=await ctx.new_page()
        for b in brands:
            try:
                market_counts[b["brand_id"]]=await collect_market_counts(page,b)
                print("COUNTS",b["brand_id"],market_counts[b["brand_id"]])
            except Exception as e:
                market_counts[b["brand_id"]]={"search_total_count":None,"search_domestic_jp_count":None,"search_korea_count":None,"search_other_count":None,"search_count_status":None}
                print("COUNT_ERR",b["brand_id"],type(e).__name__,str(e)[:120])
            for pg in range(1,PAGES+1):
                try:
                    status,rows,html=await search_page(page,b,pg)
                    (runraw/f"{b['brand_id']}_p{pg}.html").write_text(html,encoding="utf-8")
                    print("SEARCH",b["brand_id"],pg,status,len(rows))
                    for r in rows:
                        r.update({"snapshot_utc":datetime.now(timezone.utc).isoformat(),"brand_id":b["brand_id"],"brand_name_ko":b["brand_name_ko"],"selection_axis":b.get("selection_axis"),"domestic_index":float(b.get("domestic_index") or 0),"search_page":pg,"global_rank":(pg-1)*200+(r["page_rank"] or 0),"recent_sold_lower_bound":sold_lb(r.get("sold_text"))})
                        search_rows.append(r)
                except Exception as e: print("SEARCH_ERR",b["brand_id"],pg,type(e).__name__,str(e)[:120])

        # exact goods dedupe before detail requests
        dedup={}
        for r in search_rows:
            dedup[(r["brand_id"],r["goods_code"])]=r
        search_rows=list(dedup.values())

        sem=asyncio.Semaphore(DETAIL_CONCURRENCY)
        async def fetch(r):
            async with sem:
                try:
                    resp=await ctx.request.get(r["product_url"],timeout=30000,headers={"Referer":"https://www.qoo10.jp/"})
                    txt=await resp.text()
                    total,rv,shop,official,sid=detail_parse(txt)
                    return {**r,"detail_status":resp.status,"cumulative_sales_units":total,"detail_review_count":rv,"shop_name":shop,"is_flagship":1 if official else 0,"seller_id":sid,"full_price_jpy":money(r.get("list_price_text")),"current_price_jpy":money(r.get("current_price_text"))}
                except Exception as e:
                    return {**r,"detail_status":None,"cumulative_sales_units":None,"detail_review_count":None,"shop_name":None,"is_flagship":None,"seller_id":None,"detail_error":type(e).__name__}

        details=[]
        for i in range(0,len(search_rows),200):
            part=await asyncio.gather(*[fetch(r) for r in search_rows[i:i+200]])
            details.extend(part);print("DETAIL",len(details),"/",len(search_rows))
        await browser.close()

    save_csv(OUT/"raw_top3_listings.csv",details)

    # Brand-level actual sales
    brand_out=[]
    bybrand=defaultdict(list)
    for r in details:bybrand[r["brand_id"]].append(r)
    for bid,rs in bybrand.items():
        valid=[r for r in rs if r.get("cumulative_sales_units") is not None and r.get("is_flagship") is not None]
        total=sum(r["cumulative_sales_units"] for r in valid)
        flag=sum(r["cumulative_sales_units"] for r in valid if r["is_flagship"]==1)
        res=total-flag
        sellers=defaultdict(int)
        for r in valid:
            if r["is_flagship"]==0:sellers[r.get("shop_name") or r.get("seller_id") or "?"]+=r["cumulative_sales_units"]
        top3=sum(sorted(sellers.values(),reverse=True)[:3])
        mc=market_counts.get(bid,{})
        brand_out.append({"brand_id":bid,"brand_name_ko":rs[0]["brand_name_ko"],"domestic_index":rs[0]["domestic_index"],
        "search_total_count":mc.get("search_total_count"),"search_domestic_jp_count":mc.get("search_domestic_jp_count"),"search_korea_count":mc.get("search_korea_count"),"search_other_count":mc.get("search_other_count"),
        "search_pages_requested":PAGES,"effective_unique_search_listings":len(rs),"pagination_note":"Qoo10 mobile endpoint returned repeated/overlapping results; effective coverage is unique listings actually observed, not 5 distinct pages",
        "detail_valid_listings":len(valid),"coverage_pct":round(100*len(valid)/len(rs),2) if rs else 0,
        "observed_cumulative_sales_count":total,"flagship_sales_count":flag,"reseller_sales_count":res,
        "flagship_sales_share_pct":round(100*flag/total,2) if total else None,"reseller_sales_share_pct":round(100*res/total,2) if total else None,
        "reseller_seller_count":len(sellers),"reseller_top3_sales_concentration_pct":round(100*top3/res,2) if res else None,
        "sales_count_basis":"Qoo10 detail internal total_sell_amt interpreted as cumulative sold-item count; cross-checked against UI 個販売 field","scope":"brand keyword search; sales summed only across unique listings actually observed"})
    save_csv(OUT/"brand_top3_sales_share.csv",brand_out)

    # SKU clustering. Cluster all listings together first, then explicitly report official presence and mapping confidence.
    sku_out=[]
    for bid,rs in bybrand.items():
        brand=rs[0]["brand_name_ko"]
        valid=[r for r in rs if r.get("cumulative_sales_units") is not None]
        clusters=[]
        for r in sorted(valid,key=lambda x:(x.get("cumulative_sales_units") or 0),reverse=True):
            best=None;bestscore=0
            for c in clusters:
                sc=sim(r.get("product_name") or "",c["seed_name"],brand)
                if sc>bestscore:bestscore=sc;best=c
            if best is not None and bestscore>=.62:
                best["rows"].append(r);best["pair_scores"].append(bestscore)
            else:
                clusters.append({"seed_name":r.get("product_name") or "","rows":[r],"pair_scores":[1.0]})
        for c in clusters:
            rr=c["rows"];total=sum(r["cumulative_sales_units"] for r in rr);flag=sum(r["cumulative_sales_units"] for r in rr if r.get("is_flagship")==1);res=total-flag
            official_rows=[r for r in rr if r.get("is_flagship")==1];reseller_rows=[r for r in rr if r.get("is_flagship")==0]
            rep=max(rr,key=lambda x:x.get("cumulative_sales_units") or 0)
            confidence=round(sum(c["pair_scores"])/len(c["pair_scores"]),3)
            status="BOTH_FOUND" if official_rows and reseller_rows else ("FLAGSHIP_ONLY" if official_rows else "RESELLER_ONLY_UNVERIFIED")
            sku_out.append({"brand_id":bid,"brand_name_ko":brand,"canonical_product_name":rep.get("product_name"),"listing_count":len(rr),"flagship_listing_count":len(official_rows),"reseller_listing_count":len(reseller_rows),"official_presence_status":status,"mapping_confidence":confidence,"observed_cumulative_sales_count":total,"flagship_sales_count":flag if official_rows else None,"reseller_sales_count":res,"reseller_sales_share_pct":round(100*res/total,2) if total and official_rows else None,"representative_goods_code":rep.get("goods_code"),"representative_shop":rep.get("shop_name"),"representative_full_price_jpy":rep.get("full_price_jpy"),"sales_count_basis":"Qoo10 detail internal total_sell_amt interpreted as cumulative sold-item count"})
    # only rank source candidates when both flagship/reseller comparison exists, or flag as unverified
    verified=[x for x in sku_out if x["official_presence_status"]=="BOTH_FOUND"]
    salesvals=[x["observed_cumulative_sales_count"] for x in verified]
    for x in sku_out:
        if x["official_presence_status"]=="BOTH_FOUND":
            sales_score=percentile(salesvals,x["observed_cumulative_sales_count"],True)
            x["verified_sourcing_index"]=round(.60*sales_score+.40*(x["reseller_sales_share_pct"] or 0),2)
        else:x["verified_sourcing_index"]=None
    sku_out.sort(key=lambda x:(x["verified_sourcing_index"] is not None,x["verified_sourcing_index"] or -1,x["observed_cumulative_sales_count"]),reverse=True)
    for i,x in enumerate(sku_out,1):x["row_rank"]=i
    save_csv(OUT/"sku_top3_verified_index.csv",sku_out)
    save_csv(OUT/"candidate20_verified.csv",[x for x in sku_out if x["verified_sourcing_index"] is not None][:20])

    meta={"run_id":run_id,"brands":[b["brand_id"] for b in brands],"pages_requested_per_brand":PAGES,"raw_listings":len(details),"brand_rows":len(brand_out),"sku_clusters":len(sku_out),"verified_sku_clusters":len(verified),"important":"RESELLER_ONLY_UNVERIFIED rows never receive a 100% reseller share; official absence is treated as NOT VERIFIED, not zero sales. search_pages_requested does not equal effective pagination coverage when Qoo10 repeats results."}
    (OUT/"run_meta.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(meta,ensure_ascii=False))

if __name__=="__main__":asyncio.run(main())
