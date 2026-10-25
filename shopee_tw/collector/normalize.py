#!/usr/bin/env python3
"""Lossless normalization of permissioned Shopee TW observations."""
import argparse,csv,json,re
from pathlib import Path
from datetime import datetime,timezone
FIELDS=["brand","query","shop_name","shop_url","shop_id","item_id","product_name","product_url","price_twd","sold_display","sold_period","source_url","collected_at"]
def clean(s): return (s or "").strip()
def key(r):
    if r["shop_id"] and r["item_id"]: return "id:"+r["shop_id"]+":"+r["item_id"]
    if r["product_url"]: return "url:"+r["product_url"].split("?")[0].rstrip("/")
    return None
def main():
    a=argparse.ArgumentParser()
    a.add_argument("--input",default="shopee_tw/input/observations.csv")
    a.add_argument("--out",default="shopee_tw/output")
    opt=a.parse_args()
    out=Path(opt.out);out.mkdir(parents=True,exist_ok=True)
    with open(opt.input,encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f)
        missing=set(FIELDS)-set(reader.fieldnames or [])
        if missing: raise ValueError("Missing columns: "+", ".join(sorted(missing)))
        observations=[{k:clean(r.get(k)) for k in FIELDS} for r in reader]
    issues=[];unique={};shops={}
    for n,r in enumerate(observations,2):
        if not r["source_url"]:issues.append({"row":n,"error":"source_url_missing"})
        if not r["shop_url"] and not r["shop_id"]:issues.append({"row":n,"error":"shop_identifier_missing"})
        if not r["item_id"] and not r["product_url"]:issues.append({"row":n,"error":"listing_identifier_missing"})
        if r["sold_display"] and r["sold_period"] not in ("cumulative","monthly","unknown"):
            issues.append({"row":n,"error":"sold_period_must_be_explicit"})
        k=key(r)
        if k:unique[k]=r
        sk=r["shop_id"] or r["shop_url"].split("?")[0].rstrip("/")
        if sk:
            shops.setdefault(sk,{"shop_id":r["shop_id"],"shop_name":r["shop_name"],"shop_url":r["shop_url"],"observed_products":0})
            # Count unique listings per shop only after deduplication
    for r in unique.values():
        sk=r["shop_id"] or r["shop_url"].split("?")[0].rstrip("/")
        if sk in shops: shops[sk]["observed_products"]+=1
    def export(name,cols,rows):
        with open(out/name,"w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=cols,extrasaction="ignore");w.writeheader();w.writerows(rows)
    export("raw_observations.csv",FIELDS,observations)
    export("deduped_listings.csv",FIELDS,list(unique.values()))
    export("seller_master.csv",["shop_id","shop_name","shop_url","observed_products"],list(shops.values()))
    report={"generated_at":datetime.now(timezone.utc).isoformat(),"raw_rows":len(observations),"unique_listing_keys":len(unique),"unique_shop_keys":len(shops),"validation_issues":issues,"search_results_exhausted":False,"marketplace_coverage":"unknown","note":"Only ingested observations; no Shopee network collector is enabled."}
    (out/"coverage_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="validation_issues"},ensure_ascii=False))
if __name__=="__main__":main()
