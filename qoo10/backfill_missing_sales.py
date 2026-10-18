import asyncio,csv,json,re,random
from pathlib import Path
from playwright.async_api import async_playwright

SRC=Path("qoo10/input_previous/03_detail_all_unique.csv")
OUT=Path("qoo10/output_missing_sales_backfill");OUT.mkdir(parents=True,exist_ok=True)
CONC=4;RETRIES=6

def parse(txt):
    def num(key):
        m=re.search(r'"'+re.escape(key)+r'"\s*:\s*([0-9.]+)',txt)
        return int(float(m.group(1))) if m else None
    def jstr(key):
        m=re.search(r'"'+re.escape(key)+r'"\s*:\s*"((?:\\.|[^"])*)"',txt)
        if not m:return None
        try:return json.loads('"'+m.group(1)+'"')
        except:return m.group(1)
    return {
      "cumulative_sales_count":num("total_sell_amt"),
      "detail_review_count":num("review_cnt"),
      "seller_id":jstr("enc_seller_cust_no"),
      "product_name_detail":jstr("gd_nm"),
      "minishop_url":jstr("minishopURL")
    }

async def main():
    with open(SRC,encoding="utf-8-sig",newline="") as f: rows=list(csv.DictReader(f))
    missing=[r for r in rows if not r.get("cumulative_sales_count")]
    print("MISSING_INPUT",len(missing))
    sem=asyncio.Semaphore(CONC)
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True,args=["--no-sandbox"])
        c=await b.new_context(locale="ja-JP",timezone_id="Asia/Tokyo")
        async def one(r):
            async with sem:
                url=r.get("product_url") or f"https://m.qoo10.jp/gmkt.inc/Mobile/goods/goods.aspx?goodscode={r['goods_code']}"
                last={}
                for attempt in range(1,RETRIES+1):
                    try:
                        resp=await c.request.get(url,timeout=30000,headers={"Referer":"https://www.qoo10.jp/","Cache-Control":"no-cache"})
                        txt=await resp.text()
                        d=parse(txt)
                        if d["cumulative_sales_count"] is not None and d["seller_id"]:
                            return {**r,**d,"backfill_status":"OK","attempt":attempt}
                        last={"http_status":resp.status,"html_len":len(txt),"has_total_sell_amt":"total_sell_amt" in txt,"has_seller":"enc_seller_cust_no" in txt}
                    except Exception as e:
                        last={"error":type(e).__name__}
                    await asyncio.sleep(0.7*attempt + random.random()*0.6)
                return {**r,**last,"backfill_status":"FAILED","attempt":RETRIES}
        result=[]
        for start in range(0,len(missing),200):
            part=await asyncio.gather(*[one(r) for r in missing[start:start+200]])
            result.extend(part)
            ok=sum(x.get("backfill_status")=="OK" for x in result)
            print("PROGRESS",len(result),"/",len(missing),"OK",ok)
            await asyncio.sleep(1.5)
        await b.close()
    fields=[]
    for r in result:
        for k in r:
            if k not in fields:fields.append(k)
    with open(OUT/"missing_sales_backfill.csv","w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(result)
    summary={}
    for bid in ["MEDIHEAL","JSM","TORRIDEN"]:
        rr=[x for x in result if x.get("brand_id")==bid]
        summary[bid]={"missing_input":len(rr),"recovered":sum(x.get("backfill_status")=="OK" for x in rr),"still_missing":sum(x.get("backfill_status")!="OK" for x in rr)}
    (OUT/"backfill_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))
if __name__=="__main__":asyncio.run(main())