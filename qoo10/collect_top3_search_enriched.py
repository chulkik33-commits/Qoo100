import asyncio,csv,json,math,re
from pathlib import Path
from urllib.parse import quote
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parent
BRANDS=ROOT/"resell_brand_universe_top3.csv"
OUT=ROOT/"output_top3_search_enriched";OUT.mkdir(parents=True,exist_ok=True)
PAGE_SIZE=40;MAX_PAGE=51;MAX_PRICE=1000000;MIN_BUCKET_WIDTH=50;CONC=12

def clean(s):return re.sub(r"\s+"," ",(s or "")).strip()
def numtxt(el):
 if not el:return None
 m=re.search(r"([0-9][0-9,]*)",clean(el.get_text(" ",strip=True)))
 return int(m.group(1).replace(",","")) if m else None
def parse(txt):
 s=BeautifulSoup(txt,"html.parser");out=[]
 for i,li in enumerate(s.select("[data_gd_no]"),1):
  gd=li.get("data_gd_no")
  a=li.select_one("a[href*='goodscode']")
  title=li.select_one(".list_v2_title")
  brand=li.select_one(".common_ui_seller_brand")
  review=li.select_one(".rate_count")
  orig=li.select_one(".price_original_value")
  final=li.select_one(".price_final_value")
  img=li.select_one("img.thumbnail_image")
  out.append({"page_rank":i,"goods_code":gd,"product_url":a.get("href") if a else None,
   "product_name":clean(title.get_text(" ",strip=True)) if title else (img.get("alt") if img else None),
   "brand_text":clean(brand.get_text(" ",strip=True)) if brand else None,
   "review_count_search":numtxt(review),"list_price_jpy_search":numtxt(orig),"current_price_jpy_search":numtxt(final),
   "image_url":img.get("src") if img else None})
 return out
async def main():
 with open(BRANDS,encoding="utf-8-sig") as f:brands=list(csv.DictReader(f))
 async with async_playwright() as p:
  b=await p.chromium.launch(headless=True,args=["--no-sandbox"]);c=await b.new_context(locale="ja-JP",timezone_id="Asia/Tokyo")
  sem=asyncio.Semaphore(CONC)
  async def page(kw,n,lo,hi):
   u=("https://www.qoo10.jp/gmkt.inc/Mobile/Search/MobileTotalSearchAppend.aspx?"
      f"search_type=SRP&page_no={n}&page_size={PAGE_SIZE}&sort_type=11&partial=on&affiliate_group=0"
      f"&qx_delivery_search_yn=N&eticket_search_yn=N&research_yn=Y&catalogue_yn=Y&plus_type=KW"
      f"&keyword={quote(kw)}&min_price={lo}&max_price={hi}&free_shipping_search_yn=N")
   async with sem:
    for k in range(3):
     try:
      r=await c.request.get(u,timeout=30000,headers={"Referer":"https://www.qoo10.jp/"})
      if r.status==200:return parse(await r.text())
     except:pass
     await asyncio.sleep(.4*(k+1))
    return []
  async def collect_brand(br):
   kw=br["keyword_jp"]
   async def bucket(lo,hi):
    last=await page(kw,51,lo,hi)
    if len(last)>=40 and hi-lo>MIN_BUCKET_WIDTH:
     mid=(lo+hi)//2
     return (await bucket(lo,mid))+(await bucket(mid,hi))
    arr=[]
    for st in range(1,52,25):
     nums=list(range(st,min(52,st+25)))
     parts=await asyncio.gather(*[page(kw,n,lo,hi) for n in nums])
     empt=0
     for n,rows in zip(nums,parts):
      if not rows:empt+=1
      else:
       for r in rows:r.update({"brand_id":br["brand_id"],"brand_name_ko":br["brand_name_ko"],"price_bucket_min":lo,"price_bucket_max":hi,"search_page":n})
       arr.extend(rows)
     if empt>=3:break
    return arr
   return await bucket(0,MAX_PRICE)
  raw=[]
  for br in brands:
   rr=await collect_brand(br);raw+=rr;print("DONE",br["brand_id"],len(rr))
  await b.close()
 ded={}
 for r in raw:
  k=(r["brand_id"],r.get("goods_code"))
  if r.get("goods_code") and k not in ded:ded[k]=r
 rows=list(ded.values())
 fields=list(rows[0].keys())
 for name,data in [("01_search_enriched_raw.csv",raw),("02_search_enriched_unique.csv",rows)]:
  with open(OUT/name,"w",newline="",encoding="utf-8-sig") as f:
   w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(data)
 print(json.dumps({"raw":len(raw),"unique":len(rows)},ensure_ascii=False))
if __name__=="__main__":asyncio.run(main())