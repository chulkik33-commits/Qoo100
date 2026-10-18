import asyncio,re,json
from playwright.async_api import async_playwright

ITEMS={
"MEDIHEAL":{
"2G6W2LZFOPSRcuooo/Pplw==":"677451898","QuODcDvCEVog+Yqs6FEUAg==":"503618870","88XDM78j2C19ZUAcm1FV0g==":"896517193","B1l5ILmfTPL0rAOU10e5Rw==":"616223845","/Ua7iDh4NE8nbS3u3Lv6tw==":"616923003","q/E9fXXaecpOyDQ+/IQxkA==":"1001296974","n45qb/7YOzkAyg826esAXw==":"1025320229","U/Ko7h5XLQ27saXv05mH+w==":"864583916","j3AE3odIbNP0+3+subl1Ug==":"945535676","fVIY1pIUeejk8uFMJdifZw==":"876546858"},
"JSM":{
"B1l5ILmfTPL0rAOU10e5Rw==":"626412248","q/E9fXXaecpOyDQ+/IQxkA==":"1015189379","fs/Rd/uz+BmsVfBJ0n0YRA==":"1174516091","5XpVhhw8KHWXlcN8gBBT8Q==":"1079845181","Erbqqg7ZtNfwoDUCCy0BHw==":"859448457","2G6W2LZFOPSRcuooo/Pplw==":"755063800","88XDM78j2C19ZUAcm1FV0g==":"831340146","rmEpRVf+NkFmvDcnojHxMQ==":"1109655929","AmF2Ub5N9nVHFsywEE7NCQ==":"842349114","RC+J9f5oqSiD61Gs/mMtAQ==":"784093769"},
"TORRIDEN":{
"LBM1ZlBNy9HlCaYW7fahmg==":"933241218","w5iVG7/KXXMXN2jPDbvgYw==":"577244038","Erbqqg7ZtNfwoDUCCy0BHw==":"1021082522","wk2e/4cE6TONq6yi8HICgw==":"906679225","ntN06XfE5QtCSrjki7w0dw==":"983904090","q/E9fXXaecpOyDQ+/IQxkA==":"1069655984","w8Y358VZ8neMuEg8ShTrIw==":"1069661902","+AKTJM+DJ+hM8R1DtXOpNw==":"774672156","j3AE3odIbNP0+3+subl1Ug==":"1086650312","B1l5ILmfTPL0rAOU10e5Rw==":"1011379341"}
}
def jstr(t,key):
 m=re.search(r'"'+re.escape(key)+r'"\s*:\s*"((?:\\.|[^"])*)"',t)
 if not m:return None
 try:return json.loads('"'+m.group(1)+'"')
 except:return m.group(1)
async def main():
 async with async_playwright() as p:
  b=await p.chromium.launch(headless=True,args=["--no-sandbox"]);c=await b.new_context(locale="ja-JP",timezone_id="Asia/Tokyo")
  out=[]
  for brand,mp in ITEMS.items():
   for sid,g in mp.items():
    try:
     r=await c.request.get(f"https://m.qoo10.jp/gmkt.inc/Mobile/goods/goods.aspx?goodscode={g}",timeout=30000)
     t=await r.text()
     mini=jstr(t,"minishopURL"); name=jstr(t,"gd_nm"); actual=jstr(t,"enc_seller_cust_no")
     slug=None
     if mini:
      m=re.search(r"/shop/([^/?#]+)",mini,re.I);slug=m.group(1) if m else mini
     out.append({"brand_id":brand,"expected_seller_id":sid,"goods_code":g,"actual_seller_id":actual,"seller_shop":slug,"minishop_url":mini,"product_name":name,"status":r.status})
    except Exception as e:out.append({"brand_id":brand,"expected_seller_id":sid,"goods_code":g,"error":type(e).__name__})
  print(json.dumps(out,ensure_ascii=False))
  await b.close()
if __name__=="__main__":asyncio.run(main())