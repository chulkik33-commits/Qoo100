import asyncio,csv,json,math,re,random,os
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import quote
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parent
BRANDS=ROOT/os.getenv("BRAND_UNIVERSE","category_brand_universe_v1.csv")
OUT=ROOT/os.getenv("OUTPUT_DIR","output_category_brand_index");OUT.mkdir(parents=True,exist_ok=True)
PAGES=3;PAGE_SIZE=40;SEARCH_CONC=8;DETAIL_CONC=4;RETRIES=5

def clean(s):return re.sub(r"\s+"," ",(s or "")).strip()
def ntext(el):
    if not el:return None
    m=re.search(r"([0-9][0-9,]*)",clean(el.get_text(" ",strip=True)))
    return int(m.group(1).replace(",","")) if m else None
def parse_search(txt):
    s=BeautifulSoup(txt,"html.parser");out=[]
    for i,li in enumerate(s.select("[data_gd_no]"),1):
        gd=li.get("data_gd_no");title=li.select_one(".list_v2_title");brand=li.select_one(".common_ui_seller_brand")
        a=li.select_one("a[href*='goodscode']");rv=li.select_one(".rate_count");orig=li.select_one(".price_original_value");cur=li.select_one(".price_final_value")
        img=li.select_one("img.thumbnail_image")
        out.append({"page_rank":i,"goods_code":gd,"product_url":a.get("href") if a else None,
          "product_name":clean(title.get_text(" ",strip=True)) if title else (img.get("alt") if img else None),
          "brand_text":clean(brand.get_text(" ",strip=True)) if brand else None,
          "review_count_search":ntext(rv),"list_price_jpy":ntext(orig),"current_price_jpy":ntext(cur)})
    return out
def detail_parse(txt):
    def num(k):
        m=re.search(r'"'+re.escape(k)+r'"\s*:\s*([0-9.]+)',txt);return int(float(m.group(1))) if m else None
    def js(k):
        m=re.search(r'"'+re.escape(k)+r'"\s*:\s*"((?:\\.|[^"])*)"',txt)
        if not m:return None
        try:return json.loads('"'+m.group(1)+'"')
        except:return m.group(1)
    mini=js("minishopURL");shop=None
    if mini:
        mm=re.search(r"/shop/([^/?#]+)",mini,re.I);shop=mm.group(1) if mm else None
    return {"sales":num("total_sell_amt"),"review_count":num("review_cnt"),"seller_id":js("enc_seller_cust_no"),
      "seller_shop":shop,"official":1 if "公式ショップ" in txt else 0,"detail_name":js("gd_nm")}
def pct(vals,v,log=False,reverse=False):
    xs=[x for x in vals if x is not None]
    if not xs or v is None:return 0
    if log:xs=[math.log1p(max(0,x)) for x in xs];v=math.log1p(max(0,v))
    xs=sorted(xs);score=100*(sum(x<v for x in xs)+.5*sum(x==v for x in xs))/len(xs)
    return 100-score if reverse else score
def share_score(x,verified):
    if not verified:return min(70,x)
    pts=[(0,0),(5,10),(10,25),(20,45),(35,65),(50,80),(70,95),(100,100)]
    for (a,sa),(b,sb) in zip(pts,pts[1:]):
        if x<=b:return sa+(x-a)*(sb-sa)/(b-a)
    return 100
def save(path,rows):
    if not rows:return
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields:fields.append(k)
    with open(path,"w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

async def main():
    with open(BRANDS,encoding="utf-8-sig") as f:brands=list(csv.DictReader(f))
    batch=int(os.getenv("BATCH_SIZE","0"))
    if batch:
        offset=int(os.getenv("BATCH_OFFSET","0"))
        brands=brands[offset:offset+batch]
    progress={"run_id":datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),"stage":"search","brands":{},"issues":[]}
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True,args=["--no-sandbox"]);c=await b.new_context(locale="ja-JP",timezone_id="Asia/Tokyo")
        sem=asyncio.Semaphore(SEARCH_CONC)
        async def page(kw,n):
            u=("https://www.qoo10.jp/gmkt.inc/Mobile/Search/MobileTotalSearchAppend.aspx?"
               f"search_type=SRP&page_no={n}&page_size={PAGE_SIZE}&sort_type=11&partial=on&catalogue_yn=Y&plus_type=KW&keyword={quote(kw)}")
            async with sem:
                for a in range(RETRIES):
                    try:
                        r=await c.request.get(u,timeout=30000,headers={"Referer":"https://www.qoo10.jp/"})
                        if r.status==200:return parse_search(await r.text())
                    except:pass
                    await asyncio.sleep(.4*(a+1)+random.random()*.3)
            return []
        raw=[]
        for br in brands:
            allrows=[]
            for kw in br["keywords"].split("|"):
                parts=await asyncio.gather(*[page(kw,n) for n in range(1,PAGES+1)])
                for n,rows in enumerate(parts,1):
                    for r in rows:r.update({"brand_id":br["brand_id"],"brand_name_ko":br["brand_name_ko"],"category":br["category"],"domestic_index":float(br["domestic_index"]),"keyword_used":kw,"search_page":n})
                    allrows+=rows
            ded={}
            for r in allrows:
                if r.get("goods_code"):ded[r["goods_code"]]=r
            rows=list(ded.values());raw+=rows
            progress["brands"][br["brand_id"]]={"search_unique":len(rows)}
            print("SEARCH",br["category"],br["brand_id"],len(rows))
        save(OUT/"01_search_unique.csv",raw)
        progress["stage"]="detail";progress["unique_listing_count"]=len(raw)
        (OUT/"00_progress.json").write_text(json.dumps(progress,ensure_ascii=False,indent=2),encoding="utf-8")
        dsem=asyncio.Semaphore(DETAIL_CONC)
        async def one(r):
            async with dsem:
                url=r.get("product_url") or f"https://m.qoo10.jp/gmkt.inc/Mobile/goods/goods.aspx?goodscode={r['goods_code']}"
                for a in range(1,RETRIES+1):
                    try:
                        q=await c.request.get(url,timeout=30000,headers={"Referer":"https://www.qoo10.jp/","Cache-Control":"no-cache"})
                        txt=await q.text();d=detail_parse(txt)
                        if d["sales"] is not None and d["seller_id"]:
                            return {**r,**d,"detail_status":"OK","attempt":a}
                    except:pass
                    await asyncio.sleep(.6*a+random.random()*.4)
                return {**r,"detail_status":"FAILED","attempt":RETRIES}
        detail=[]
        for st in range(0,len(raw),200):
            detail+=await asyncio.gather(*[one(r) for r in raw[st:st+200]])
            progress["detail_done"]=len(detail);progress["detail_ok"]=sum(x.get("detail_status")=="OK" for x in detail)
            (OUT/"00_progress.json").write_text(json.dumps(progress,ensure_ascii=False,indent=2),encoding="utf-8")
            print("DETAIL",len(detail),"/",len(raw),"OK",progress["detail_ok"])
        await b.close()
    save(OUT/"02_detail.csv",detail)

    rows=[]
    by=defaultdict(list)
    for r in detail:by[r["brand_id"]].append(r)
    meta={r["brand_id"]:r for r in brands}
    for bid,rr in by.items():
        ok=[x for x in rr if x.get("detail_status")=="OK"]
        total=sum(x.get("sales") or 0 for x in ok)
        official=[x for x in ok if x.get("official")==1];reseller=[x for x in ok if x.get("official")==0]
        fs=sum(x.get("sales") or 0 for x in official);rs=sum(x.get("sales") or 0 for x in reseller)
        sellers=defaultdict(int)
        for x in reseller:sellers[x.get("seller_id")]+=x.get("sales") or 0
        vals=sorted(sellers.values(),reverse=True)
        verified=bool(official)
        rows.append({"brand_id":bid,"brand_name_ko":meta[bid]["brand_name_ko"],"category":meta[bid]["category"],"domestic_index":float(meta[bid]["domestic_index"]),
          "search_unique_listings":len(rr),"detail_ok":len(ok),"detail_coverage_pct":100*len(ok)/len(rr) if rr else 0,
          "observed_sales":total,"flagship_sales":fs,"reseller_sales":rs,"reseller_sales_share_pct":100*rs/total if total else 0,
          "flagship_observed":"YES" if verified else "NO","reseller_seller_count":len(sellers),
          "qualified_reseller_count":sum(v>=100 for v in vals),"strong_reseller_count":sum(v>=1000 for v in vals),
          "top3_reseller_concentration_pct":100*sum(vals[:3])/rs if rs else 100})
    final=[]
    for cat in sorted(set(x["category"] for x in rows)):
        cc=[x for x in rows if x["category"]==cat]
        sales=[x["observed_sales"] for x in cc];qual=[x["qualified_reseller_count"] for x in cc];strong=[x["strong_reseller_count"] for x in cc];conc=[x["top3_reseller_concentration_pct"] for x in cc]
        for x in cc:
            demand=pct(sales,x["observed_sales"],log=True)
            access=share_score(x["reseller_sales_share_pct"],x["flagship_observed"]=="YES")
            depth=.6*pct(qual,x["qualified_reseller_count"],log=True)+.4*pct(strong,x["strong_reseller_count"],log=True)
            competition=100-pct(conc,x["top3_reseller_concentration_pct"])
            x["qoo10_demand_score"]=round(demand,2);x["reseller_access_score"]=round(access,2);x["reseller_depth_score"]=round(depth,2);x["competition_score"]=round(competition,2)
            x["brand_index"]=round(.25*x["domestic_index"]+.35*demand+.20*access+.15*depth+.05*competition,2)
            x["index_meaning"]="Higher = more worth trying for our reseller business"
            final.append(x)
    final.sort(key=lambda x:(x["category"],-x["brand_index"]))
    ranks=defaultdict(int)
    for x in final:ranks[x["category"]]+=1;x["category_rank"]=ranks[x["category"]]
    save(OUT/"03_category_brand_index.csv",final)
    save(OUT/"04_top10_by_category.csv",[x for x in final if x["category_rank"]<=10])
    progress["stage"]="completed";progress["brand_count"]=len(rows);progress["issues_count"]=len(progress["issues"])
    (OUT/"00_progress.json").write_text(json.dumps(progress,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(progress,ensure_ascii=False))
if __name__=="__main__":asyncio.run(main())