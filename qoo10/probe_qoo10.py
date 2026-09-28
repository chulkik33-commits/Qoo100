import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

import requests

DEFAULT_KEYWORDS = ["ジョンセンムル", "jungsaemmool"]
keywords = DEFAULT_KEYWORDS
if len(sys.argv) > 1 and sys.argv[1].strip():
    keywords = [k.strip() for k in sys.argv[1].split(",") if k.strip()]

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
}

outdir = Path("qoo10/output")
outdir.mkdir(parents=True, exist_ok=True)


def first_count(text: str):
    patterns = [
        r"([0-9][0-9,]*)\s*件",
        r"([0-9][0-9,]*)\s*商品",
        r"検索結果[^0-9]{0,30}([0-9][0-9,]*)",
    ]
    vals = []
    for p in patterns:
        vals.extend(re.findall(p, text, flags=re.I | re.S))
    if not vals:
        return None, []
    cleaned = []
    for v in vals:
        try:
            cleaned.append(int(v.replace(",", "")))
        except ValueError:
            pass
    return (cleaned[0] if cleaned else None), cleaned[:30]


def probe(keyword: str):
    url = f"https://www.qoo10.jp/s/{quote(keyword)}?keyword={quote(keyword)}"
    try:
        r = requests.get(url, headers=headers, timeout=30)
        text = r.text
    except Exception as e:
        return {
            "keyword": keyword,
            "url": url,
            "request_error": repr(e),
            "query_count": None,
        }, ""

    query_count, count_candidates = first_count(text)
    is_qoo10_error = (
        "section_error_full" in text
        or "Error" in text and "Qoo10" in text
        or "connecting " in text and len(text) < 10000
    )

    result = {
        "keyword": keyword,
        "url": url,
        "status_code": r.status_code,
        "html_bytes": len(r.content),
        "final_url": r.url,
        "query_count": query_count,
        "count_candidates": count_candidates,
        "qoo10_error_page": is_qoo10_error,
        "error_code_523_present": "523 Error" in text,
        "review_sort_present": bool(re.search(r"レビューが多い順|レビュー.*?順", text, re.I | re.S)),
        "shipping_korea_present": "韓国" in text,
        "shipping_japan_present": bool(re.search(r"国内\s*\(日本\)|日本", text)),
        "related_search_present": "関連検索" in text,
    }
    return result, text


results = []
for idx, keyword in enumerate(keywords, start=1):
    result, html = probe(keyword)
    results.append(result)
    safe = re.sub(r"[^0-9A-Za-z_-]+", "_", keyword).strip("_") or f"keyword_{idx}"
    (outdir / f"search_{idx}_{safe}.html").write_text(html, encoding="utf-8")

summary = {
    "keywords": keywords,
    "results": results,
    "note": "query_count is the Qoo10 search result count when present in returned HTML.",
}
(outdir / "probe.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(summary, ensure_ascii=False, indent=2))
