import asyncio,re,json
from playwright.async_api import async_playwright
G="854410549"
async def main():
  async with async_playwright() as p:
    b=await p.chromium.launch(headless=True,args=["--no-sandbox"])
    c=await b.new_context(locale="ja-JP",timezone_id="Asia/Tokyo")
    r=await c.request.get(f"https://m.qoo10.jp/gmkt.inc/Mobile/goods/goods.aspx?goodscode={G}",timeout=30000)
    t=await r.text()
    pairs=[]
    for m in re.finditer(r'"([^"]*(?:shop|seller|cust)[^"]*)"\s*:\s*(".*?"|true|false|null|-?\d+(?:\.\d+)?)',t,re.I):
      k=m.group(1);v=m.group(2)
      if len(v)<300:pairs.append((k,v))
    uniq=[];seen=set()
    for x in pairs:
      if x not in seen:seen.add(x);uniq.append(x)
    print(json.dumps(uniq[:300],ensure_ascii=False,indent=2))
    await b.close()
if __name__=="__main__":asyncio.run(main())