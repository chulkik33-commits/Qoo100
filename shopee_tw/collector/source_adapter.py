"""Import authorized, locally supplied Shopee observations into the standard schema.

This is a feed adapter, NOT a crawler. It does not access shopee.tw or bypass
marketplace controls. Supply an exported CSV obtained with appropriate permission.
"""
import argparse, csv
from pathlib import Path
from datetime import datetime, timezone

COLUMNS = ["brand","query","shop_name","shop_url","shop_id","item_id",
           "product_name","product_url","price_twd","sold_display",
           "sold_period","source_url","collected_at"]

def import_csv(source, target):
    source, target = Path(source), Path(target)
    with source.open(encoding="utf-8-sig",newline="") as fh:
        reader=csv.DictReader(fh)
        headers=set(reader.fieldnames or [])
        if not {"shop_url","product_observed"}.issubset(headers) and not set(COLUMNS).issubset(headers):
            raise ValueError("Expected native schema or legacy shop_url/product_observed columns")
        records=[]
        for raw in reader:
            if set(COLUMNS).issubset(headers):
                out={field:(raw.get(field) or "").strip() for field in COLUMNS}
            else:
                out={
                    "brand":raw.get("brand","JUNGSAEMMOOL"),
                    "query":"",
                    "shop_name":raw.get("shop_display") or raw.get("shop_username") or "",
                    "shop_url":raw.get("shop_url",""),
                    "shop_id":raw.get("shop_id",""),
                    "item_id":raw.get("item_id",""),
                    "product_name":raw.get("product_observed",""),
                    "product_url":raw.get("listing_url",""),
                    "price_twd":raw.get("display_price_twd",""),
                    "sold_display":raw.get("sold_display",""),
                    "sold_period":"unknown",
                    "source_url":raw.get("listing_url") or raw.get("shop_url",""),
                    "collected_at":""
                }
            if out["shop_url"] or out["shop_id"]:
                records.append(out)
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("w",encoding="utf-8-sig",newline="") as fh:
        writer=csv.DictWriter(fh,fieldnames=COLUMNS)
        writer.writeheader();writer.writerows(records)
    return len(records)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",required=True)
    p.add_argument("--target",default="shopee_tw/input/observations.csv")
    args=p.parse_args()
    print("Imported rows:",import_csv(args.source,args.target))
