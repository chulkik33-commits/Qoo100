import csv, json, math, re, statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent
BRANDS=ROOT/"resell_brand_universe.csv"
COSTS=ROOT/"resell_cost_input.csv"
OUT=ROOT/"output_resell"; RAW=OUT/"raw"
OUT.mkdir(parents=True,exist_ok=True); RAW.mkdir(parents=True,exist_ok=True)
TOPN=40

def clean(s): return re.sub(r"\s+"," ",(s or "")).strip()
def nint(s):
    m=re.search(r"([0-9][0-9,]*)",str(s or ""))
    return int(m.group(1).replace(",","")) if m else None
def nfloat(s):
    try: return float(str(s).replace(",","").strip()) if s not in (None,"") else None
    except: return None
def all_prices(s):
    vals=[int(x.replace(",","")) for x in re.findall(r"(?:¥|円)?\s*([0-9][0-9,]{2,})",s or "")]
    return [x for x in vals if 100<=x<=1000000]
def parse_display_price(s):
    xs=all_prices(s); return xs[0] if xs else None
def parse_full_price(s):
    xs=all_prices(s); return max(xs) if xs else None
def parse_sales_count(s):
    for pat in [r"販売(?:数|件数)?\s*[:：]?\s*([0-9][0-9,]*)",r"購入(?:数|件数)?\s*[:：]?\s*([0-9][0-9,]*)",r"売れた\s*([0-9][0-9,]*)"]:
        m=re.search(pat,s or "",re.I)
        if m: return int(m.group(1).replace(",",""))
    return None
def norm_name(name):
    s=clean(name).lower()
    s=re.sub(r"\[[^\]]*\]|【[^】]*】|\([^)]*\)"," ",s)
    for t in ["qoo10","公式","韓国コスメ","送料無料","メガ割","限定","正規品","即納"]: s=s.replace(t.lower()," ")
    return clean(re.sub(r"[^0-9a-zぁ-んァ-ン一-龥가-힣]+"," ",s))
def percentile_score(values,value,log=False):
    xs=[x for x in values if x is not None]
    if value is None or not xs:return 0.0
    if log: xs=[math.log1p(max(0,x)) for x in xs]; value=math.log1p(max(0,value))
    xs=sorted(xs); below=sum(x<value for x in xs); eq=sum(x==value for x in xs)
    return round(100*(below+0.5*eq)/len(xs),2)
def read_brands():
    with open(BRANDS,encoding="utf-8-sig") as f:return [r for r in csv.DictReader(f) if r.get("active","1").strip()=="1"]
def read_costs():
    if not COSTS.exists():return {}
    with open(COSTS,encoding="utf-8-sig") as f:
        return {(r.get("brand_id","").strip(),r.get("sku_key","").strip()):r for r in csv.DictReader(f)}
def market_snapshot(page,b,keyword_type,keyword):
    url=f"https://www.qoo10.jp/s/{quote(keyword)}?keyword={quote(keyword)}"
    resp=page.goto(url,wait_until="domcontentloaded",timeout=60000); page.wait_for_timeout(3000)
    data=page.evaluate("""() => {
      const c=s=>(s||'').replace(/\s+/g,' ').trim(); const ship={};
      for(const a of document.querySelectorAll('a.local[data-nation_code]')){const code=a.getAttribute('data-nation_code')||'ALL';const n=a.querySelector('.num');if(!(code in ship))ship[code]=c(n?n.textContent:'');}
      const related=[...document.querySelectorAll('#search_keyword_list a')].map(a=>c(a.textContent)).filter(Boolean);
      const cats=[]; for(const a of document.querySelectorAll('a[href*="gdlc_cd="]')){const sp=a.querySelector('span');if(!sp||!/\([0-9,]+\)/.test(sp.textContent||''))continue;const name=c([...a.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join(' '));if(name)cats.push({name,count_text:c(sp.textContent)});}
      return {title:document.title,final_url:location.href,shipping:ship,related:[...new Set(related)],categories:cats};
    }""")
    return {"snapshot_utc":datetime.now(timezone.utc).isoformat(),"brand_id":b["brand_id"],"brand_name_ko":b["brand_name_ko"],"selection_axis":b.get("selection_axis"),"domestic_index":b.get("domestic_index"),"keyword_type":keyword_type,"keyword":keyword,"http_status":resp.status if resp else None,"page_title":data["title"],"final_url":data["final_url"],"total_count":nint(data["shipping"].get("ALL")),"japan_count":nint(data["shipping"].get("JP")),"korea_count":nint(data["shipping"].get("KR")),"related_words":" | ".join(data["related"]),"categories_json":json.dumps([{"name":x["name"],"count":nint(x["count_text"])} for x in data["categories"]],ensure_ascii=False)}
def extract_rows(page,b,keyword_type,keyword,sort_mode):
    rows=page.evaluate(f"""() => {{
      const c=s=>(s||'').replace(/\s+/g,' ').trim();
      return [...document.querySelectorAll('#search_result_item_list tr[list_type="search_new_list_type"]')].slice(0,{TOPN}).map((r,i)=>{{
        const goods=r.querySelector('.sbj a[data-type="goods_url"]'),rev=r.querySelector('.review_total_count'),shop=r.querySelector('a.lnk_sh'),price=r.querySelector('.td_prc'),ship=r.querySelector('.td_ship .shp_ntn'),brand=r.querySelector('.txt_brand');
        return {{rank:i+1,goods_code:r.getAttribute('goodscode'),brand_text:brand?c(brand.textContent):null,product_name:goods?c(goods.textContent):null,product_url:goods?goods.href:null,price_text:price?c(price.textContent):null,review_text:rev?c(rev.textContent):null,shop_name:shop?c(shop.textContent).replace(/^Power seller\s*/, ''):null,shop_url:shop?shop.href:null,shipping_country:ship?c(ship.textContent):null,row_text:c(r.textContent)}}; }});
    }}""")
    ts=datetime.now(timezone.utc).isoformat(); out=[]
    for r in rows:
        shop=r.get("shop_name") or ""; row_text=r.get("row_text") or ""; name=r.get("product_name")
        official=1 if ("公式" in shop or "official" in shop.lower() or "公式" in row_text) else 0
        out.append({"snapshot_utc":ts,"brand_id":b["brand_id"],"brand_name_ko":b["brand_name_ko"],"selection_axis":b.get("selection_axis"),"domestic_index":b.get("domestic_index"),"keyword_type":keyword_type,"keyword":keyword,"sort_mode":sort_mode,"rank":r.get("rank"),"goods_code":r.get("goods_code"),"brand_text":r.get("brand_text"),"product_name":name,"sku_key":norm_name(name),"display_price_jpy":parse_display_price(r.get("price_text")),"full_price_jpy":parse_full_price(r.get("price_text")),"price_text":r.get("price_text"),"review_count":nint(r.get("review_text")),"review_text":r.get("review_text"),"sales_count":parse_sales_count(row_text),"row_text":row_text,"shop_name":shop,"is_official_shop":official,"shipping_country":r.get("shipping_country"),"product_url":r.get("product_url"),"shop_url":r.get("shop_url")})
    return out
def set_review_sort(page):
    loc=page.locator('a[val="MOST_REVIEWED"]').first
    if loc.count()==0:return False
    loc.evaluate("el => el.click()"); page.wait_for_timeout(4500)
    try:page.wait_for_load_state("networkidle",timeout=8000)
    except:pass
    return True
def save_csv(path,rows,fields):
    with open(path,"w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(rows)
def build_candidates(rows,costs):
    by=defaultdict(list)
    for r in rows:
        if r.get("sku_key"):by[(r["brand_id"],r["sku_key"])].append(r)
    out=[]
    for (bid,key),rs in by.items():
        prices=[r["full_price_jpy"] for r in rs if r.get("full_price_jpy")]; reviews=[r["review_count"] for r in rs if r.get("review_count") is not None]
        pop=[r["rank"] for r in rs if r["sort_mode"]=="popular" and r.get("rank")]; rev=[r["rank"] for r in rs if r["sort_mode"]=="review" and r.get("rank")]
        shops={r["shop_name"] for r in rs if r.get("shop_name")}; non={r["shop_name"] for r in rs if r.get("shop_name") and not r.get("is_official_shop")}
        official={r["shop_name"] for r in rs if r.get("shop_name") and r.get("is_official_shop")}
        korea=sum("韓国" in (r.get("shipping_country") or "") or "Korea" in (r.get("shipping_country") or "") for r in rs)
        rep=max(rs,key=lambda x:(x.get("review_count") or 0,-(x.get("rank") or 9999))); med=statistics.median(prices) if prices else None;pmin=min(prices) if prices else None
        reseller_reviews=sum((r.get("review_count") or 0) for r in rs if not r.get("is_official_shop")); official_reviews=sum((r.get("review_count") or 0) for r in rs if r.get("is_official_shop"))
        denom=reseller_reviews+official_reviews
        out.append({"brand_id":bid,"brand_name_ko":rep.get("brand_name_ko"),"selection_axis":rep.get("selection_axis"),"domestic_index":rep.get("domestic_index"),"sku_key":key,"representative_name":rep.get("product_name"),"representative_goods_code":rep.get("goods_code"),"representative_url":rep.get("product_url"),"max_review_count":max(reviews) if reviews else 0,"best_popular_rank":min(pop) if pop else None,"best_review_rank":min(rev) if rev else None,"listing_observations":len(rs),"unique_shop_count":len(shops),"official_shop_count":len(official),"nonofficial_shop_count":len(non),"nonofficial_shop_share_pct":round(100*len(non)/len(shops),2) if shops else 0,"reseller_review_share_pct":round(100*reseller_reviews/denom,2) if denom else None,"korea_shipping_share_pct":round(100*korea/len(rs),2) if rs else 0,"min_full_price_jpy":pmin,"median_full_price_jpy":round(med,2) if med else None,"price_spread_pct":round((med-pmin)/med*100,2) if med and pmin is not None else 0})
    vals=[x["max_review_count"] for x in out]
    for x in out:
        x["demand_review_score"]=percentile_score(vals,x["max_review_count"],True); bp=x["best_popular_rank"]
        x["visibility_score"]=round(max(0,100*(TOPN-(bp or TOPN))/max(1,TOPN-1)),2) if bp else 0
        x["reseller_access_score"]=x["reseller_review_share_pct"] if x["reseller_review_share_pct"] is not None else x["nonofficial_shop_share_pct"]
        x["market_score"]=round(.4*x["demand_review_score"]+.2*x["visibility_score"]+.3*x["reseller_access_score"]+.1*min(100,x["korea_shipping_share_pct"]),2)
        x["cost_status"]="COST_REQUIRED";x["expected_margin_jpy"]=None;x["expected_margin_pct"]=None;x["economics_score"]=None;x["final_score"]=None
    out.sort(key=lambda x:x["market_score"],reverse=True)
    for i,x in enumerate(out,1):x["market_rank"]=i
    return out,[]
def main():
    brands=read_brands();costs=read_costs();market=[];listings=[];run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ");run_raw=RAW/run_id;run_raw.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=["--no-sandbox"]);ctx=browser.new_context(locale="ja-JP",timezone_id="Asia/Tokyo",viewport={"width":1440,"height":1200});page=ctx.new_page()
        for b in brands:
            for kt,col in [("jp","keyword_jp"),("en","keyword_en")]:
                kw=clean(b.get(col))
                if not kw:continue
                try:
                    market.append(market_snapshot(page,b,kt,kw));(run_raw/f"{b['brand_id']}_{kt}_popular.html").write_text(page.content(),encoding="utf-8");listings.extend(extract_rows(page,b,kt,kw,"popular"))
                    if set_review_sort(page):(run_raw/f"{b['brand_id']}_{kt}_review.html").write_text(page.content(),encoding="utf-8");listings.extend(extract_rows(page,b,kt,kw,"review"))
                except Exception as e:
                    print("ERROR",b["brand_id"],kt,type(e).__name__,str(e)[:180])
        browser.close()
    mf=["snapshot_utc","brand_id","brand_name_ko","selection_axis","domestic_index","keyword_type","keyword","http_status","page_title","final_url","total_count","japan_count","korea_count","related_words","categories_json"]
    lf=["snapshot_utc","brand_id","brand_name_ko","selection_axis","domestic_index","keyword_type","keyword","sort_mode","rank","goods_code","brand_text","product_name","sku_key","display_price_jpy","full_price_jpy","price_text","review_count","review_text","sales_count","row_text","shop_name","is_official_shop","shipping_country","product_url","shop_url"]
    save_csv(OUT/"raw_market.csv",market,mf);save_csv(OUT/"raw_listings.csv",listings,lf)
    c,_=build_candidates(listings,costs)
    if c:save_csv(OUT/"candidate_database.csv",c,list(c[0].keys()))
    (OUT/"run_meta.json").write_text(json.dumps({"run_id":run_id,"brand_count":len(brands),"market_rows":len(market),"raw_listing_rows":len(listings),"candidate_rows":len(c),"price_policy":"full/list price = maximum price value in Qoo10 price cell when multiple values exist","sales_share_policy":"direct sales_count when exposed; otherwise review-weighted proxy is explicitly labeled"},ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"brand_count":len(brands),"market_rows":len(market),"raw_listing_rows":len(listings)},ensure_ascii=False))
if __name__=="__main__":main()
