import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

import requests

KEYWORD = sys.argv[1] if len(sys.argv) > 1 else "ジョンセンムル"
url = f"https://www.qoo10.jp/s/{quote(KEYWORD)}?keyword={quote(KEYWORD)}"

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
}

r = requests.get(url, headers=headers, timeout=30)
r.raise_for_status()
text = r.text

patterns = {
    "total_candidates": [
        r"([0-9,]+)\s*件",
        r"([0-9,]+)\s*商品",
    ],
    "review_sort_present": [r"レビューが多い順", r"レビュー.*?順"],
    "shipping_korea_present": [r"韓国"],
    "shipping_japan_present": [r"国内\s*\(日本\)", r"日本"],
}

out = {
    "keyword": KEYWORD,
    "url": url,
    "status_code": r.status_code,
    "html_bytes": len(r.content),
    "final_url": r.url,
}

for key, pats in patterns.items():
    hits = []
    for p in pats:
        hits.extend(re.findall(p, text, flags=re.I | re.S)[:20])
    out[key] = hits if key == "total_candidates" else bool(hits)

for token in ["レビューが多い順", "発送国", "韓国", "関連検索"]:
    i = text.find(token)
    if i >= 0:
        out[f"snippet_{token}"] = re.sub(
            r"\s+", " ", text[max(0, i - 250): i + 500]
        )[:1000]

Path("qoo10/output").mkdir(parents=True, exist_ok=True)
Path("qoo10/output/probe.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
)
Path("qoo10/output/search.html").write_text(text, encoding="utf-8")

print(json.dumps(out, ensure_ascii=False, indent=2))
