import csv, math
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"output_resell"

def fnum(x,default=0):
    try:return float(x)
    except:return default

def percentile(vals,v):
    xs=sorted([x for x in vals if x is not None])
    if not xs:return 0
    below=sum(x<v for x in xs);eq=sum(x==v for x in xs)
    return round(100*(below+0.5*eq)/len(xs),2)

def inv_percentile(vals,v):
    return round(100-percentile(vals,v),2)

def main():
    with open(OUT/"raw_market.csv",encoding="utf-8-sig") as f: market=list(csv.DictReader(f))
    with open(OUT/"raw_listings.csv",encoding="utf-8-sig") as f: listings=list(csv.DictReader(f))

    # de-duplicate repeated observation of same goods listing across JP/EN keywords and sort modes
    goods={}
    for r in listings:
        key=(r["brand_id"],r.get("goods_code") or r.get("product_url") or r.get("product_name"))
        old=goods.get(key)
        if old is None or fnum(r.get("review_count"))>fnum(old.get("review_count")):
            goods[key]=r
    rows=list(goods.values())

    by=defaultdict(list)
    for r in rows: by[r["brand_id"]].append(r)
    market_by=defaultdict(list)
    for r in market: market_by[r["brand_id"]].append(r)

    out=[]
    for bid,rs in by.items():
        mr=market_by.get(bid,[])
        meta=(mr[0] if mr else rs[0])
        total=max([fnum(x.get("total_count"),0) for x in mr] or [0])
        jp=max([fnum(x.get("japan_count"),0) for x in mr] or [0])
        kr=max([fnum(x.get("korea_count"),0) for x in mr] or [0])
        reviews=[fnum(r.get("review_count"),0) for r in rs]
        max_review=max(reviews) if reviews else 0
        sum_review=sum(reviews)
        best_pop=min([int(float(r["rank"])) for r in rs if r.get("sort_mode")=="popular" and r.get("rank")] or [999])

        official=[r for r in rs if str(r.get("is_official_shop"))=="1"]
        reseller=[r for r in rs if str(r.get("is_official_shop"))!="1"]
        official_shops={r.get("shop_name") for r in official if r.get("shop_name")}
        reseller_shops={r.get("shop_name") for r in reseller if r.get("shop_name")}

        direct=[r for r in rs if r.get("sales_count") not in ("",None)]
        direct_total=sum(fnum(r.get("sales_count"),0) for r in direct)
        direct_reseller=sum(fnum(r.get("sales_count"),0) for r in direct if str(r.get("is_official_shop"))!="1")
        review_total=sum(fnum(r.get("review_count"),0) for r in rs)
        review_reseller=sum(fnum(r.get("review_count"),0) for r in reseller)

        if direct_total>0:
            reseller_share=100*direct_reseller/direct_total
            share_basis="DIRECT_SALES_COUNT"
        elif review_total>0:
            reseller_share=100*review_reseller/review_total
            share_basis="REVIEW_WEIGHTED_PROXY"
        else:
            reseller_share=100*len(reseller)/len(rs) if rs else 0
            share_basis="LISTING_SHARE_PROXY"

        seller_review=defaultdict(float)
        for r in reseller:
            seller_review[r.get("shop_name") or "(unknown)"]+=fnum(r.get("review_count"),0)
        ordered=sorted(seller_review.values(),reverse=True)
        top3=sum(ordered[:3]); reseller_review_total=sum(ordered)
        top3_conc=100*top3/reseller_review_total if reseller_review_total else 100

        out.append({
            "brand_id":bid,
            "brand_name_ko":meta.get("brand_name_ko"),
            "selection_axis":meta.get("selection_axis"),
            "domestic_index":round(fnum(meta.get("domestic_index")),2),
            "qoo10_total_result_count":int(total),
            "qoo10_japan_shipping_count":int(jp),
            "qoo10_korea_shipping_count":int(kr),
            "observed_unique_listings":len(rs),
            "max_review_count":int(max_review),
            "sum_review_count":int(sum_review),
            "best_popular_rank":None if best_pop==999 else best_pop,
            "flagship_shop_count":len(official_shops),
            "reseller_shop_count":len(reseller_shops),
            "flagship_listing_count":len(official),
            "reseller_listing_count":len(reseller),
            "reseller_listing_share_pct":round(100*len(reseller)/len(rs),2) if rs else 0,
            "reseller_sales_share_pct":round(reseller_share,2),
            "reseller_sales_share_basis":share_basis,
            "direct_sales_listings_observed":len(direct),
            "reseller_top3_concentration_pct":round(top3_conc,2),
        })

    total_vals=[math.log1p(x["qoo10_total_result_count"]) for x in out]
    review_vals=[math.log1p(x["max_review_count"]) for x in out]
    sumrev_vals=[math.log1p(x["sum_review_count"]) for x in out]
    seller_vals=[x["reseller_shop_count"] for x in out]
    conc_vals=[x["reseller_top3_concentration_pct"] for x in out]

    for x in out:
        search_score=percentile(total_vals,math.log1p(x["qoo10_total_result_count"]))
        review_score=percentile(review_vals,math.log1p(x["max_review_count"]))
        depth_score=percentile(sumrev_vals,math.log1p(x["sum_review_count"]))
        rank_score=0 if x["best_popular_rank"] is None else max(0,100*(41-x["best_popular_rank"])/40)
        x["jp_demand_index"]=round(.25*search_score+.30*review_score+.25*depth_score+.20*rank_score,2)

        reseller_share_score=max(0,min(100,x["reseller_sales_share_pct"]))
        reseller_count_score=percentile(seller_vals,x["reseller_shop_count"])
        concentration_score=inv_percentile(conc_vals,x["reseller_top3_concentration_pct"])
        x["reseller_access_index"]=round(.55*reseller_share_score+.25*reseller_count_score+.20*concentration_score,2)

        # Domestic demand establishes candidate quality, Japan demand establishes market fit,
        # reseller access measures whether sales are actually available to non-flagship sellers.
        x["cross_market_brand_index"]=round(.25*x["domestic_index"]+.45*x["jp_demand_index"]+.30*x["reseller_access_index"],2)

    out.sort(key=lambda x:x["cross_market_brand_index"],reverse=True)
    for i,x in enumerate(out,1):x["cross_market_rank"]=i

    fields=list(out[0].keys()) if out else []
    with open(OUT/"brand_cross_market_index.csv","w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(out)
    with open(OUT/"brand_top20_qoo10.csv","w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(out[:20])
    print({"brands":len(out),"top20":len(out[:20])})

if __name__=="__main__":main()
