import asyncio,re,json
from playwright.async_api import async_playwright
SAMPLES=["1213538251","1145858402","1057300110","854410549"]
async def main():
  async with async_playwright() as p:
    b=await p.chromium.launch(headless=True,args=["--no-sandbox"])
    c=await b.new_context(locale="ja-JP",timezone_id="Asia/Tokyo")
    out={}
    for g in SAMPLES:
      u=f"https://m.qoo10.jp/gmkt.inc/Mobile/goods/goods.aspx?goodscode={g}"
      r=await c.request.get(u,timeout=30000)
      t=await r.text()
      keys={}
      for pat in ["total_sell_amt","gd_nm","goods_name","seller","shop","cust_nm","seller_nm","shop_name","enc_seller_cust_no","review_cnt","公式ショップ"]:
        hits=[]
        for m in re.finditer(pat,t,re.I):
          hits.append(re.sub(r"\s+"," ",t[max(0,m.start()-180):min(len(t),m.end()+300)]))
          if len(hits)>=5: break
        keys[pat]=hits
      title=re.search(r"<title[^>]*>(.*?)</title>",t,re.S|re.I)
      og=re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',t,re.I)
      out[g]={"status":r.status,"len":len(t),"title":title.group(1).strip() if title else None,"og":og.group(1) if og else None,"keys":keys}
    print(json.dumps(out,ensure_ascii=False,indent=2))
    await b.close()
if __name__=="__main__":asyncio.run(main())