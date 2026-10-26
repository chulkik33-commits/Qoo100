import asyncio,csv,json,math,re,random
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import quote
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parent
BRANDS=ROOT/"oliveyoung_top100_brand_universe.csv"
OUT=ROOT/"output_top100_brand_index";OUT.mkdir(parents=True,exist_ok=True)
PAGES=3;PAGE_SIZE=40;SEARCH_CONC=8;DETAIL_CONC=4;RETRIES=6

def clean(s): return re.sub(r"\s+"," ",(s or "")).strip()
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
    return {"sales":num("total_sell_amt"),"review_count":num("review_cnt"),"seller_id":js("enc_seller_cust_no"),"seller_shop":shop,
      "official":1 if "公式ショップ" in txt else 0,"detail_name":js("gd_nm")}
def pct(vals,v,log=False):
    xs=[x for x in vals if x is not None]
    if not xs or v is None:return 0
    if log:xs=[math.log1p(max(0,x)) for x in xs];v=math.log1p(max(0,v))
    xs=sorted(xs);return 100*(sum(x<v for x in xs)+.5*sum(x==v for x in xs))/len(xs)
def share_score(x,verified):
    if not verified:return min(70,x)
    pts=[(0,0),(5,10),(10,25),(20,45),(35,65),(50,80),(70,95),(100,100)]
    for (a,sa),(b,sb) in zip(pts,pts[1:]):
        if x<=b:return sa+(x-a)*(sb-sa)/(b-a)
    return 100
def domestic_score(best,count,reviews):
    rank=(101-best)
    breadth=min(100,25*count)
    rev=min(100,20*math.log10(max(1,reviews)))
    return .45*rank+.25*breadth+.30*rev

MULTI_CATEGORY_BRANDS={"VT","ETUDE"}

CATEGORY_TERMS={
 "SKINCARE":[
  "serum","ampoule","cream","toner","lotion","essence","mask","pad","cleanser","cleansing","sunscreen","sun cream","moisture","pdrn","retinol","cica","hyaluronic",
  "セラム","アンプル","クリーム","トナー","ローション","エッセンス","マスク","パッド","クレンジング","日焼け止め","美容液","化粧水","乳液",
  "세럼","앰플","크림","토너","로션","에센스","마스크","패드","클렌징","선크림"
 ],
 "MAKEUP":[
  "cushion","foundation","tint","lip","blush","mascara","eyeliner","eyeshadow","palette","concealer","powder","primer","brow","highlighter","contour",
  "クッション","ファンデ","ティント","リップ","チーク","マスカラ","アイライナー","アイシャドウ","パレット","コンシーラー","パウダー","プライマー","ブロウ","ハイライト",
  "쿠션","파운데이션","틴트","립","블러셔","마스카라","아이라이너","아이섀도","팔레트","컨실러","파우더","프라이머","브로우"
 ],
 "HAIRCARE":[
  "hair","shampoo","treatment","conditioner","scalp","hair oil","hair serum","hair mask","hair mist","dye","color","styling",
  "ヘア","シャンプー","トリートメント","コンディショナー","スカルプ","ヘアオイル","ヘアセラム","ヘアマスク","ヘアミスト","カラー","スタイリング",
  "헤어","샴푸","트리트먼트","컨디셔너","두피","헤어오일","헤어세럼","헤어팩","헤어미스트","염색","스타일링"
 ]
}
def category_relevant(r):
    bid=r.get("brand_id","")
    base=bid.split("_")[-1]
    if base not in MULTI_CATEGORY_BRANDS:return True
    text=(" "+(r.get("product_name") or "")+" "+(r.get("detail_name") or "")+" ").lower()
    cat=r.get("category")
    return any(term.lower() in text for term in CATEGORY_TERMS.get(cat,[]))

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
    progress={"run_id":datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),"stage":"search","brand_count":len(brands),"brands":{}}
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
                    await asyncio.sleep(.5*(a+1)+random.random()*.3)
            return []
        raw=[]
        for br in brands:
            allrows=[]
            for kw in br["keywords"].split("|"):
                parts=await asyncio.gather(*[page(kw,n) for n in range(1,PAGES+1)])
                for n,rows in enumerate(parts,1):
                    for r in rows:r.update({"brand_id":br["brand_id"],"brand_name_ko":br["brand_name_ko"],"category":br["category"],
                      "domestic_best_rank":int(br["domestic_best_rank"]),"domestic_top100_count":int(br["domestic_top100_count"]),
                      "domestic_review_sum":int(br["domestic_review_sum"]),"keyword_used":kw,"search_page":n})
                    allrows+=rows
            ded={}
            for r in allrows:
                if r.get("goods_code"):ded[r["goods_code"]]=r
            rows=list(ded.values());raw+=rows;progress["brands"][br["brand_id"]]={"search_unique":len(rows)}
            print("SEARCH",br["category"],br["brand_id"],len(rows),flush=True)
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
                        if d["sales"] is not None and d["seller_id"]:return {**r,**d,"detail_status":"OK","attempt":a}
                    except:pass
                    await asyncio.sleep(.7*a+random.random()*.4)
                return {**r,"detail_status":"FAILED","attempt":RETRIES}
        detail=[]
        for st in range(0,len(raw),200):
            detail+=await asyncio.gather(*[one(r) for r in raw[st:st+200]])
            progress["detail_done"]=len(detail);progress["detail_ok"]=sum(x.get("detail_status")=="OK" for x in detail)
            (OUT/"00_progress.json").write_text(json.dumps(progress,ensure_ascii=False,indent=2),encoding="utf-8")
            print("DETAIL",len(detail),"/",len(raw),"OK",progress["detail_ok"],flush=True)
        await b.close()
    save(OUT/"02_detail.csv",detail)
    filtered=[r for r in detail if category_relevant(r)]
    save(OUT/"02b_detail_category_filtered.csv",filtered)
    rows=[];by=defaultdict(list);meta={r["brand_id"]:r for r in brands}
    for r in filtered:by[r["brand_id"]].append(r)
    for br in brands:
        bid=br["brand_id"]; rr=by.get(bid,[])
        ok=[x for x in rr if x.get("detail_status")=="OK"];total=sum(x.get("sales") or 0 for x in ok)
        official=[x for x in ok if x.get("official")==1];reseller=[x for x in ok if x.get("official")==0]
        fs=sum(x.get("sales") or 0 for x in official);rs=sum(x.get("sales") or 0 for x in reseller)
        sellers=defaultdict(int)
        for x in reseller:sellers[x.get("seller_id")]+=x.get("sales") or 0
        vals=sorted(sellers.values(),reverse=True);m=meta[bid]
        rows.append({"brand_id":bid,"brand_name_ko":m["brand_name_ko"],"category":m["category"],"domestic_best_rank":int(m["domestic_best_rank"]),
          "domestic_top100_count":int(m["domestic_top100_count"]),"domestic_review_sum":int(m["domestic_review_sum"]),
          "domestic_score":round(domestic_score(int(m["domestic_best_rank"]),int(m["domestic_top100_count"]),int(m["domestic_review_sum"])),2),
          "search_unique_listings":len(rr),"detail_ok":len(ok),"detail_coverage_pct":round(100*len(ok)/len(rr),2) if rr else 0,
          "observed_sales":total,"flagship_sales":fs,"reseller_sales":rs,"reseller_sales_share_pct":round(100*rs/total,2) if total else 0,
          "flagship_observed":"YES" if official else "NO","reseller_seller_count":len(sellers),
          "qualified_reseller_count":sum(v>=100 for v in vals),"strong_reseller_count":sum(v>=1000 for v in vals),
          "top3_reseller_concentration_pct":round(100*sum(vals[:3])/rs,2) if rs else 100})
    final=[]
    for cat in sorted(set(x["category"] for x in rows)):
        cc=[x for x in rows if x["category"]==cat]
        sales=[x["observed_sales"] for x in cc];qual=[x["qualified_reseller_count"] for x in cc];strong=[x["strong_reseller_count"] for x in cc];conc=[x["top3_reseller_concentration_pct"] for x in cc]
        for x in cc:
            demand=pct(sales,x["observed_sales"],log=True);access=share_score(x["reseller_sales_share_pct"],x["flagship_observed"]=="YES")
            depth=.6*pct(qual,x["qualified_reseller_count"],log=True)+.4*pct(strong,x["strong_reseller_count"],log=True)
            competition=100-pct(conc,x["top3_reseller_concentration_pct"])
            x["qoo10_demand_score"]=round(demand,2);x["reseller_access_score"]=round(access,2);x["reseller_depth_score"]=round(depth,2);x["competition_score"]=round(competition,2)
            x["brand_index"]=round(.25*x["domestic_score"]+.35*demand+.20*access+.15*depth+.05*competition,2)
            x["index_meaning"]="Higher = more worth trying for our reseller business";final.append(x)
    final.sort(key=lambda x:(x["category"],-x["brand_index"]));ranks=defaultdict(int)
    for x in final:ranks[x["category"]]+=1;x["category_rank"]=ranks[x["category"]]
    save(OUT/"03_category_brand_index.csv",final)
    save(OUT/"04_all_ranked.csv",final)
    progress["stage"]="completed";progress["detail_ok"]=sum(x.get("detail_status")=="OK" for x in detail);progress["brand_rows"]=len(final)
    (OUT/"00_progress.json").write_text(json.dumps(progress,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(progress,ensure_ascii=False),flush=True)
if __name__=="__main__":asyncio.run(main())