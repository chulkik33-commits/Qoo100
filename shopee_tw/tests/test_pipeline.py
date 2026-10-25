import csv,json,subprocess,sys,tempfile
from pathlib import Path

HEADERS="brand,query,shop_name,shop_url,shop_id,item_id,product_name,product_url,price_twd,sold_display,sold_period,source_url,collected_at"
ROW1="JUNGSAEMMOOL,鄭瑄茉,Shop A,https://shopee.tw/shopa,101,501,Cushion,https://shopee.tw/product/101/501,699,23,unknown,https://shopee.tw/product/101/501,2026-10-25T10:00:00+09:00"
ROW2="JUNGSAEMMOOL,鄭瑄茉,Shop B,https://shopee.tw/shopb,102,502,Primer,https://shopee.tw/product/102/502,500,7,unknown,https://shopee.tw/product/102/502,2026-10-25T10:00:00+09:00"
def main():
    with tempfile.TemporaryDirectory() as d:
        root=Path(d)
        source=root/"sample.csv"
        source.write_text("\n".join([HEADERS,ROW1,ROW1,ROW2])+"\n",encoding="utf-8")
        out=root/"out"
        subprocess.run([sys.executable,"shopee_tw/collector/normalize.py","--input",str(source),"--out",str(out)],check=True)
        report=json.loads((out/"coverage_report.json").read_text(encoding="utf-8"))
        with (out/"seller_master.csv").open(encoding="utf-8-sig",newline="") as f:
            sellers=list(csv.DictReader(f))
        assert report["raw_rows"]==3,report
        assert report["unique_listing_keys"]==2,report
        assert report["unique_shop_keys"]==2,report
        assert sorted(int(r["observed_products"]) for r in sellers)==[1,1],sellers
        assert not report["validation_issues"],report
        print("PASS: CSV input, listing dedupe, seller dedupe, counts, provenance")
if __name__=="__main__":main()
