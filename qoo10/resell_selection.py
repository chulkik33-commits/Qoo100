import csv
import json
import math
import re
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
BRANDS = ROOT / "resell_brand_universe.csv"
COSTS = ROOT / "resell_cost_input.csv"
OUT = ROOT / "output_resell"
RAW = OUT / "raw"
OUT.mkdir(parents=True, exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)
TOPN = 40

def clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()

def nint(s):
    if s is None:
        return None
    m = re.search(r"([0-9][0-9,]*)", str(s))
    return int(m.group(1).replace(",", "")) if m else None

def nfloat(s):
    if s in (None, ""):
        return None
    try:
        return float(str(s).replace(",", "").strip())
    except Exception:
        return None

def parse_price_jpy(s):
    if not s:
        return None
    vals = re.findall(r"(?:¥|円)?\s*([0-9][0-9,]{2,})", s)
    if not vals:
        return None
    nums = [int(x.replace(",", "")) for x in vals]
    nums = [x for x in nums if 100 <= x <= 1000000]
    return nums[0] if nums else None

def norm_name(name):
    s = clean(name).lower()
    s = re.sub(r"\[[^\]]*\]|【[^】]*】|\([^)]*\)", " ", s)
    for token in ["qoo10", "公式", "韓国コスメ", "送料無料", "メガ割", "限定", "正規品", "即納"]:
        s = s.replace(token.lower(), " ")
    s = re.sub(r"[^0-9a-zぁ-んァ-ン一-龥가-힣]+", " ", s)
    return clean(s)

def percentile_score(values, value, log=False):
    xs = [x for x in values if x is not None]
    if value is None or not xs:
        return 0.0
    if log:
        xs = [math.log1p(max(0, x)) for x in xs]
        value = math.log1p(max(0, value))
    if len(xs) == 1:
        return 100.0
    xs = sorted(xs)
    below = sum(1 for x in xs if x < value)
    equal = sum(1 for x in xs if x == value)
    return round(100.0 * (below + 0.5 * equal) / len(xs), 2)

def read_brands():
    with open(BRANDS, encoding="utf-8-sig") as f:
        return [r for r in csv.DictReader(f) if str(r.get("active","1")).strip() == "1"]

def read_costs():
    if not COSTS.exists():
        return {}
    out = {}
    with open(COSTS, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            key=(r.get("brand_id","").strip(), r.get("sku_key","").strip())
            if key[0] and key[1]:
                out[key]=r
    return out

def market_snapshot(page, brand_id, keyword_type, keyword):
    url=f"https://www.qoo10.jp/s/{quote(keyword)}?keyword={quote(keyword)}"
    resp=page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3500)
    data=page.evaluate("""() => {
      const c=s=>(s||'').replace(/\\s+/g,' ').trim();
      const ship={};
      for(const a of document.querySelectorAll('a.local[data-nation_code]')){
        const code=a.getAttribute('data-nation_code')||'ALL';
        const n=a.querySelector('.num');
        if(!(code in ship)) ship[code]=c(n?n.textContent:'');
      }
      const related=[...document.querySelectorAll('#search_keyword_list a')].map(a=>c(a.textContent)).filter(Boolean);
      const cats=[];
      for(const a of document.querySelectorAll('a[href*="gdlc_cd="]')){
        const sp=a.querySelector('span');
        if(!sp || !/\\([0-9,]+\\)/.test(sp.textContent||'')) continue;
        const name=c([...a.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join(' '));
        if(name) cats.push({name,count_text:c(sp.textContent)});
      }
      return {title:document.title,final_url:location.href,shipping:ship,related:[...new Set(related)],categories:cats};
    }""")
    return {
        "snapshot_utc": datetime.now(timezone.utc).isoformat(),
        "brand_id": brand_id,
        "keyword_type": keyword_type,
        "keyword": keyword,
        "http_status": resp.status if resp else None,
        "page_title": data["title"],
        "final_url": data["final_url"],
        "total_count": nint(data["shipping"].get("ALL")),
        "japan_count": nint(data["shipping"].get("JP")),
        "korea_count": nint(data["shipping"].get("KR")),
        "related_words": " | ".join(data["related"]),
        "categories_json": json.dumps([
            {"name":x["name"],"count":nint(x["count_text"])} for x in data["categories"]
        ], ensure_ascii=False)
    }

def extract_rows(page, brand_id, keyword_type, keyword, sort_mode):
    rows=page.evaluate(f"""() => {{
      const c=s=>(s||'').replace(/\\s+/g,' ').trim();
      return [...document.querySelectorAll('#search_result_item_list tr[list_type="search_new_list_type"]')].slice(0,{TOPN}).map((r,i)=>{{
        const goods=r.querySelector('.sbj a[data-type="goods_url"]');
        const rev=r.querySelector('.review_total_count');
        const shop=r.querySelector('a.lnk_sh');
        const price=r.querySelector('.td_prc');
        const ship=r.querySelector('.td_ship .shp_ntn');
        const brand=r.querySelector('.txt_brand');
        return {{
          rank:i+1, goods_code:r.getAttribute('goodscode'),
          brand_text:brand?c(brand.textContent):null,
          product_name:goods?c(goods.textContent):null,
          product_url:goods?goods.href:null,
          price_text:price?c(price.textContent):null,
          review_text:rev?c(rev.textContent):null,
          shop_name:shop?c(shop.textContent).replace(/^Power seller\\s*/,''):null,
          shop_url:shop?shop.href:null,
          shipping_country:ship?c(ship.textContent):null
        }};
      }});
    }}""")
    ts=datetime.now(timezone.utc).isoformat()
    out=[]
    for r in rows:
        name=r.get("product_name")
        shop=r.get("shop_name") or ""
        out.append({
            "snapshot_utc":ts, "brand_id":brand_id, "keyword_type":keyword_type, "keyword":keyword,
            "sort_mode":sort_mode, "rank":r.get("rank"), "goods_code":r.get("goods_code"),
            "brand_text":r.get("brand_text"), "product_name":name, "sku_key":norm_name(name),
            "price_jpy":parse_price_jpy(r.get("price_text")), "price_text":r.get("price_text"),
            "review_count":nint(r.get("review_text")), "review_text":r.get("review_text"),
            "shop_name":shop, "is_official_shop":1 if ("公式" in shop or "official" in shop.lower()) else 0,
            "shipping_country":r.get("shipping_country"), "product_url":r.get("product_url"), "shop_url":r.get("shop_url")
        })
    return out

def set_review_sort(page):
    loc=page.locator('a[val="MOST_REVIEWED"]').first
    if loc.count()==0:
        return False
    loc.evaluate("el => el.click()")
    page.wait_for_timeout(5000)
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    return True

def save_csv(path, rows, fields):
    with open(path,"w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader(); w.writerows(rows)

def build_candidates(rows, costs):
    by=defaultdict(list)
    for r in rows:
        if r.get("sku_key"):
            by[(r["brand_id"],r["sku_key"])].append(r)
    candidates=[]
    for (brand_id,sku_key), rs in by.items():
        prices=[r["price_jpy"] for r in rs if r.get("price_jpy")]
        reviews=[r["review_count"] for r in rs if r.get("review_count") is not None]
        popular=[r["rank"] for r in rs if r["sort_mode"]=="popular" and r.get("rank")]
        reviewed=[r["rank"] for r in rs if r["sort_mode"]=="review" and r.get("rank")]
        shops={r["shop_name"] for r in rs if r.get("shop_name")}
        nonofficial={r["shop_name"] for r in rs if r.get("shop_name") and not r.get("is_official_shop")}
        korea=sum(1 for r in rs if "韓国" in (r.get("shipping_country") or "") or "Korea" in (r.get("shipping_country") or ""))
        rep=max(rs,key=lambda x:(x.get("review_count") or 0, -(x.get("rank") or 9999)))
        median=statistics.median(prices) if prices else None
        pmin=min(prices) if prices else None
        spread=((median-pmin)/median*100) if median and pmin is not None else 0
        candidates.append({
            "brand_id":brand_id,"sku_key":sku_key,"representative_name":rep.get("product_name"),
            "representative_goods_code":rep.get("goods_code"),"representative_url":rep.get("product_url"),
            "max_review_count":max(reviews) if reviews else 0,
            "best_popular_rank":min(popular) if popular else None,
            "best_review_rank":min(reviewed) if reviewed else None,
            "listing_observations":len(rs),"unique_shop_count":len(shops),
            "nonofficial_shop_count":len(nonofficial),
            "nonofficial_shop_share_pct":round(100*len(nonofficial)/len(shops),2) if shops else 0,
            "korea_shipping_share_pct":round(100*korea/len(rs),2) if rs else 0,
            "min_price_jpy":pmin,"median_price_jpy":round(median,2) if median else None,
            "price_spread_pct":round(spread,2)
        })
    reviews_all=[x["max_review_count"] for x in candidates]
    for x in candidates:
        x["demand_review_score"]=percentile_score(reviews_all,x["max_review_count"],log=True)
        bp=x["best_popular_rank"]
        x["visibility_score"]=round(max(0,100*(TOPN-(bp or TOPN))/max(1,TOPN-1)),2) if bp else 0
        x["contestability_score"]=round(min(100,x["nonofficial_shop_share_pct"]),2)
        x["price_room_score"]=round(min(100,max(0,x["price_spread_pct"]/30*100)),2)
        x["korea_ship_score"]=round(min(100,x["korea_shipping_share_pct"]),2)
        # first snapshot: momentum is intentionally neutral until a second snapshot exists
        x["momentum_score"]=50.0
        x["market_score"]=round(
            0.35*x["demand_review_score"]+
            0.20*x["visibility_score"]+
            0.20*x["contestability_score"]+
            0.10*x["price_room_score"]+
            0.05*x["korea_ship_score"]+
            0.10*x["momentum_score"],2)
        cost=costs.get((x["brand_id"],x["sku_key"]))
        x["cost_status"]="COST_REQUIRED"
        x["expected_margin_jpy"]=None
        x["expected_margin_pct"]=None
        x["economics_score"]=None
        x["final_score"]=None
        if cost and nfloat(cost.get("b2b_cost_krw")) is not None and nfloat(cost.get("fx_jpy_per_krw")) is not None and x.get("median_price_jpy"):
            sell=x["median_price_jpy"]
            b2b=nfloat(cost["b2b_cost_krw"]) or 0
            fx=nfloat(cost["fx_jpy_per_krw"]) or 0
            domestic=(nfloat(cost.get("domestic_freight_krw")) or 0)*fx
            intl=nfloat(cost.get("international_freight_jpy")) or 0
            duty=nfloat(cost.get("duty_tax_jpy")) or 0
            pct=sum((nfloat(cost.get(k)) or 0) for k in ["platform_fee_pct","payment_fee_pct","promo_allowance_pct","return_loss_pct"])
            total=b2b*fx+domestic+intl+duty+sell*pct/100
            margin=sell-total
            mpct=100*margin/sell if sell else None
            x["expected_margin_jpy"]=round(margin,2)
            x["expected_margin_pct"]=round(mpct,2) if mpct is not None else None
            x["economics_score"]=round(max(0,min(100,(mpct or 0)/30*100)),2)
            x["final_score"]=round(0.55*x["market_score"]+0.45*x["economics_score"],2)
            x["cost_status"]="READY"
    candidates.sort(key=lambda x:x["market_score"], reverse=True)
    for i,x in enumerate(candidates,1):
        x["market_rank"]=i
    ready=[x for x in candidates if x["cost_status"]=="READY"]
    ready.sort(key=lambda x:x["final_score"], reverse=True)
    for i,x in enumerate(ready,1):
        x["final_rank"]=i
    return candidates, ready

def main():
    brands=read_brands()
    costs=read_costs()
    market=[]
    listings=[]
    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_raw=RAW/run_id
    run_raw.mkdir(parents=True,exist_ok=True)

    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=["--no-sandbox"])
        ctx=browser.new_context(locale="ja-JP",timezone_id="Asia/Tokyo",viewport={"width":1440,"height":1200})
        page=ctx.new_page()
        for b in brands:
            for keyword_type,col in [("jp","keyword_jp"),("en","keyword_en")]:
                keyword=clean(b.get(col))
                if not keyword: continue
                snap=market_snapshot(page,b["brand_id"],keyword_type,keyword)
                market.append(snap)
                (run_raw/f"{b['brand_id']}_{keyword_type}_popular.html").write_text(page.content(),encoding="utf-8")
                listings.extend(extract_rows(page,b["brand_id"],keyword_type,keyword,"popular"))
                if set_review_sort(page):
                    (run_raw/f"{b['brand_id']}_{keyword_type}_review.html").write_text(page.content(),encoding="utf-8")
                    listings.extend(extract_rows(page,b["brand_id"],keyword_type,keyword,"review"))
        browser.close()

    market_fields=["snapshot_utc","brand_id","keyword_type","keyword","http_status","page_title","final_url","total_count","japan_count","korea_count","related_words","categories_json"]
    listing_fields=["snapshot_utc","brand_id","keyword_type","keyword","sort_mode","rank","goods_code","brand_text","product_name","sku_key","price_jpy","price_text","review_count","review_text","shop_name","is_official_shop","shipping_country","product_url","shop_url"]
    save_csv(OUT/"raw_market.csv",market,market_fields)
    save_csv(OUT/"raw_listings.csv",listings,listing_fields)

    candidates,ready=build_candidates(listings,costs)
    cand_fields=list(candidates[0].keys()) if candidates else []
    if candidates:
        save_csv(OUT/"candidate_database.csv",candidates,cand_fields)
        save_csv(OUT/"candidate20_market.csv",candidates[:20],cand_fields)
    if ready:
        save_csv(OUT/"selected10_resell.csv",ready[:10],list(ready[0].keys()))
    else:
        (OUT/"selected10_resell.csv").write_text("status\nCOST_REQUIRED: fill qoo10/resell_cost_input.csv and rerun\n",encoding="utf-8-sig")

    meta={
      "run_id":run_id,
      "topn_per_sort":TOPN,
      "brand_count":len(brands),
      "market_rows":len(market),
      "raw_listing_rows":len(listings),
      "candidate_skus":len(candidates),
      "economics_ready_skus":len(ready),
      "scoring":{
        "market_score":{
          "demand_review_score":0.35,"visibility_score":0.20,"contestability_score":0.20,
          "price_room_score":0.10,"korea_ship_score":0.05,"momentum_score":0.10
        },
        "final_score":{"market_score":0.55,"economics_score":0.45},
        "note":"momentum_score=50 on first snapshot; replace with review growth after multiple snapshots."
      }
    }
    (OUT/"run_meta.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(meta,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
