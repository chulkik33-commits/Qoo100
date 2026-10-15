import csv
import hashlib
import math
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output_resell"
RAW_LISTINGS = OUT / "raw_listings.csv"

GENERIC = {
    "公式","正規品","送料無料","韓国","韓国コスメ","国内発送","即納","限定","new","newカラー",
    "qoo10","セット","set","本品","レフィル","リフィル","企画","メガ割","再入荷","お得","特価",
    "入り","付き","付","個","本","ml","g"
}

def clean(s):
    return re.sub(r"\s+"," ",(s or "")).strip()

def base_name(s):
    s=clean(s).lower()
    s=re.sub(r"【[^】]*】|\[[^\]]*\]|\([^)]*\)"," ",s)
    s=s.replace("jung saem mool","ジョンセンムル")
    s=re.sub(r"[^0-9a-zぁ-んァ-ン一-龥가-힣]+"," ",s)
    toks=[t for t in s.split() if t not in GENERIC and len(t)>1]
    return " ".join(toks)

def variant_signature(s):
    x=(s or "").lower()
    flags=[]
    if re.search(r"レフィル|リフィル|refill",x): flags.append("REFILL")
    if re.search(r"セット|set|企画|\+|付き|付属",x): flags.append("SET")
    if re.search(r"パフ|puff",x): flags.append("PUFF")
    if re.search(r"ミニ|mini",x): flags.append("MINI")
    nums=re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*(ml|g)",x)
    if nums:
        flags += [f"{a}{b}" for a,b in nums]
    return "|".join(sorted(set(flags))) or "BASE"

def tokens(s):
    return set(base_name(s).split())

def similarity(a,b):
    ba,bb=base_name(a),base_name(b)
    if not ba or not bb: return 0
    ta,tb=tokens(a),tokens(b)
    jac=len(ta&tb)/max(1,len(ta|tb))
    seq=SequenceMatcher(None,ba,bb).ratio()
    contain=1.0 if (ba in bb or bb in ba) and min(len(ba),len(bb))>=8 else 0.0
    return max(seq*0.65+jac*0.35, 0.88*contain+0.12*jac)

def stable_id(brand, canonical):
    h=hashlib.sha1(f"{brand}|{canonical}".encode("utf-8")).hexdigest()[:8].upper()
    return f"{brand}-{h}"

def main():
    with open(RAW_LISTINGS,encoding="utf-8-sig") as f:
        rows=list(csv.DictReader(f))

    by_brand=defaultdict(list)
    for i,r in enumerate(rows):
        r["_row_id"]=i+1
        by_brand[r["brand_id"]].append(r)

    index_rows=[]
    map_rows=[]
    for brand,brs in by_brand.items():
        # collapse exact same goods code first: same Qoo10 listing observed via JP/EN and sort modes
        goods_groups=defaultdict(list)
        for r in brs:
            goods_groups[r.get("goods_code") or f"ROW-{r['_row_id']}"].append(r)

        units=[]
        for goods_code,rs in goods_groups.items():
            rep=max(rs,key=lambda x:int(float(x.get("review_count") or 0)))
            units.append({
                "goods_code":goods_code,
                "name":rep.get("product_name") or "",
                "variant":variant_signature(rep.get("product_name") or ""),
                "rows":rs
            })

        clusters=[]
        for u in sorted(units,key=lambda x:len(base_name(x["name"])),reverse=True):
            best=None; bestscore=0
            for c in clusters:
                if u["variant"] != c["variant"]:
                    continue
                sc=similarity(u["name"],c["canonical_name"])
                if sc>bestscore:
                    bestscore=sc; best=c
            threshold=0.72
            if best is not None and bestscore>=threshold:
                best["units"].append(u)
                # use the title with highest review count as representative later
            else:
                clusters.append({"variant":u["variant"],"canonical_name":u["name"],"units":[u]})

        for c in clusters:
            allrows=[r for u in c["units"] for r in u["rows"]]
            rep=max(allrows,key=lambda x:int(float(x.get("review_count") or 0)))
            canonical=clean(rep.get("product_name") or c["canonical_name"])
            sku_id=stable_id(brand,base_name(canonical)+"|"+c["variant"])
            names=sorted({clean(r.get("product_name")) for r in allrows if clean(r.get("product_name"))})
            goods=sorted({str(r.get("goods_code")) for r in allrows if r.get("goods_code")})
            shops=sorted({clean(r.get("shop_name")) for r in allrows if clean(r.get("shop_name"))})
            prices=[]
            reviews=[]
            ranks_pop=[]; ranks_rev=[]
            for r in allrows:
                try:
                    if r.get("full_price_jpy"): prices.append(float(r["full_price_jpy"]))
                except: pass
                try:
                    if r.get("review_count"): reviews.append(int(float(r["review_count"])))
                except: pass
                try:
                    rank=int(float(r["rank"]))
                    if r.get("sort_mode")=="popular": ranks_pop.append(rank)
                    if r.get("sort_mode")=="review": ranks_rev.append(rank)
                except: pass
            confidence=1.0 if len(goods)==1 else round(min(0.99,0.72+0.03*min(9,len(goods)-1)),2)
            review_required=1 if (len(goods)>1 and confidence<0.85) else 0
            index_rows.append({
                "brand_id":brand,
                "sku_id":sku_id,
                "canonical_product_name":canonical,
                "variant_signature":c["variant"],
                "listing_goods_count":len(goods),
                "listing_observation_count":len(allrows),
                "unique_shop_count":len(shops),
                "min_price_jpy":int(min(prices)) if prices else None,
                "median_price_jpy":int(sorted(prices)[len(prices)//2]) if prices else None,
                "max_review_count":max(reviews) if reviews else 0,
                "best_popular_rank":min(ranks_pop) if ranks_pop else None,
                "best_review_rank":min(ranks_rev) if ranks_rev else None,
                "mapping_confidence":confidence,
                "review_required":review_required,
                "goods_codes":" | ".join(goods),
                "aliases":" | ".join(names[:12]),
                "shops":" | ".join(shops[:12]),
            })
            for r in allrows:
                map_rows.append({
                    "snapshot_utc":r.get("snapshot_utc"),
                    "brand_id":brand,
                    "sku_id":sku_id,
                    "goods_code":r.get("goods_code"),
                    "keyword_type":r.get("keyword_type"),
                    "keyword":r.get("keyword"),
                    "sort_mode":r.get("sort_mode"),
                    "rank":r.get("rank"),
                    "product_name":r.get("product_name"),
                    "shop_name":r.get("shop_name"),
                    "price_jpy":r.get("full_price_jpy"),
                    "review_count":r.get("review_count"),
                    "mapping_confidence":confidence,
                    "review_required":review_required
                })

    index_rows.sort(key=lambda x:(x["brand_id"],-(x["max_review_count"] or 0),x["canonical_product_name"]))
    for brand in by_brand:
        n=0
        for r in index_rows:
            if r["brand_id"]==brand:
                n+=1; r["brand_sku_seq"]=n

    fields=list(index_rows[0].keys()) if index_rows else []
    with open(OUT/"canonical_sku_index.csv","w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(index_rows)
    mfields=list(map_rows[0].keys()) if map_rows else []
    with open(OUT/"sku_listing_map.csv","w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=mfields); w.writeheader(); w.writerows(map_rows)

    # market-only shortlist from canonical SKU index; wholesale cost intentionally excluded
    review_vals=[math.log1p(r["max_review_count"] or 0) for r in index_rows]
    maxrv=max(review_vals) if review_vals else 1
    for r in index_rows:
        demand=100*math.log1p(r["max_review_count"] or 0)/maxrv if maxrv else 0
        pop=100*max(0,(41-(r["best_popular_rank"] or 41))/40)
        shops=min(100,20*(r["unique_shop_count"] or 0))
        r["pre_cost_index"]=round(0.55*demand+0.30*pop+0.15*shops,2)
    shortlist=sorted(index_rows,key=lambda x:x["pre_cost_index"],reverse=True)[:20]
    sfields=list(shortlist[0].keys()) if shortlist else []
    with open(OUT/"candidate20_indexed.csv","w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=sfields); w.writeheader(); w.writerows(shortlist)

    print({
        "canonical_skus":len(index_rows),
        "listing_map_rows":len(map_rows),
        "candidate20":len(shortlist),
        "review_required":sum(int(r["review_required"]) for r in index_rows)
    })

if __name__=="__main__":
    main()
