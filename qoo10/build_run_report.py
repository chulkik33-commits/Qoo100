import csv, json
from pathlib import Path
OUT=Path(__file__).resolve().parent/"output_resell"

def read_csv(name):
    p=OUT/name
    if not p.exists(): return []
    with open(p,encoding="utf-8-sig") as f:return list(csv.DictReader(f))

def main():
    meta=json.load(open(OUT/"run_meta.json",encoding="utf-8")) if (OUT/"run_meta.json").exists() else {}
    brands=read_csv("brand_cross_market_index.csv")
    skus=read_csv("candidate20_indexed.csv")
    lines=[]
    lines += ["# Qoo10 JP Reseller Collection Report",""]
    lines += [f"- Run ID: {meta.get('run_id','')}",f"- Brands collected: {meta.get('brand_count','')}",f"- Market rows: {meta.get('market_rows','')}",f"- Raw listing rows: {meta.get('raw_listing_rows','')}",f"- Candidate rows: {meta.get('candidate_rows','')}",f"- Price policy: {meta.get('price_policy','')}",f"- Sales-share policy: {meta.get('sales_share_policy','')}", ""]
    lines += ["## Top 20 Brands by Cross-market Index","", "|Rank|Brand|Axis|Domestic|JP Demand|Reseller Access|Reseller Sales Share|Basis|", "|---:|---|---|---:|---:|---:|---:|---|"]
    for r in brands[:20]:
        lines.append(f"|{r.get('cross_market_rank','')}|{r.get('brand_name_ko','')}|{r.get('selection_axis','')}|{r.get('domestic_index','')}|{r.get('jp_demand_index','')}|{r.get('reseller_access_index','')}|{r.get('reseller_sales_share_pct','')}%|{r.get('reseller_sales_share_basis','')}|")
    lines += ["","## Top 20 SKU Candidates Before Wholesale Cost","", "|Rank|Brand|SKU|Index|Max Reviews|Best Popular Rank|Shops|Min Full Price|Median Full Price|", "|---:|---|---|---:|---:|---:|---:|---:|---:|"]
    for i,r in enumerate(skus[:20],1):
        name=(r.get("canonical_product_name") or "").replace("|","/")
        lines.append(f"|{i}|{r.get('brand_id','')}|{name}|{r.get('pre_cost_index','')}|{r.get('max_review_count','')}|{r.get('best_popular_rank','')}|{r.get('unique_shop_count','')}|{r.get('min_price_jpy','')}|{r.get('median_price_jpy','')}|")
    lines += ["","## Verification Files","", "- raw_market.csv", "- raw_listings.csv", "- canonical_sku_index.csv", "- sku_listing_map.csv", "- brand_cross_market_index.csv", "- brand_top20_qoo10.csv", "- candidate20_indexed.csv", "- raw/*.html", ""]
    (OUT/"REPORT.md").write_text("\n".join(lines),encoding="utf-8")
    print("REPORT.md created")
if __name__=="__main__": main()
