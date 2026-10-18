import asyncio,re,json
from playwright.async_api import async_playwright
ITEMS=[("JSM","N4t+Nk68C8vwMXUMXjqxPA==","1179694605"),("TORRIDEN","gfy06qz6Eb53vb6mHhaQDA==","1202462079")]
def jstr(t,key):
 m=re.search(r'"'+re.escape(key)+r'"\s*:\s*"((?:\\.|[^"])*)"',t)
 if not m:return None
 try:return json.loads('"'+m.group(1)+'"')
 except:return m.group(1)
async def main():
 async with async_playwright() as p:
  b=await p.chromium.launch(headless=True,args=["--no-sandbox"]);c=await b.new_context(locale="ja-JP",timezone_id="Asia/Tokyo")
  out=[]
  for brand,sid,g in ITEMS:
   r=await c.request.get(f"https://m.qoo10.jp/gmkt.inc/Mobile/goods/goods.aspx?goodscode={g}",timeout=30000)
   t=await r.text();mini=jstr(t,"minishopURL")
   m=re.search(r"/shop/([^/?#]+)",mini or "",re.I)
   out.append({"brand_id":brand,"seller_id":sid,"goods_code":g,"seller_shop":m.group(1) if m else None,"minishop_url":mini,"product_name":jstr(t,"gd_nm")})
  print(json.dumps(out,ensure_ascii=False))
  await b.close()
if __name__=="__main__":asyncio.run(main())