importScripts("capture_core.js");

chrome.action.onClicked.addListener(async tab => {
  if (!tab.id || !/^https:\/\/shopee\.tw\//.test(tab.url || "")) {
    await chrome.action.setBadgeText({tabId: tab.id, text: "TW?"});
    return;
  }
  try {
    const results = await chrome.scripting.executeScript({
      target: {tabId: tab.id},
      func: () => {
        const bodyText = document.body?.innerText || "";
        const priceCandidates = bodyText.match(/\$\s*[\d,]+(?:\s*[-~]\s*\$?\s*[\d,]+)?/g) || [];
        const soldCandidates = bodyText.match(/(?:已售出|已售)\s*[\d,.]+\s*[萬千Kk+]?/g) || [];
        return ({
        page_url: location.href,
        page_error: /頁面無法顯示|發生錯誤！請返回/.test(bodyText)
          ? "Shopee page cannot display" : "",
        detail_title: document.querySelector("h1")?.innerText?.trim() || document.title,
        price_candidates: [...new Set(priceCandidates)].slice(0, 20),
        sold_candidates: [...new Set(soldCandidates)].slice(0, 20),
        cards: [...document.querySelectorAll('a[href*="-i."]')].map(a => ({
          url: a.href, label: a.getAttribute("aria-label") || "", text: a.innerText || ""
        }))
      }); }
    });
    const page = results[0].result;
    const at = new Date().toISOString();
    const payload = TrackBCapture.normalizePage(page, at);
    const datePart = at.replace(/[:.]/g, "-");
    const filename = `Shopee_TW_Captures/capture_${datePart}.json`;
    const url = "data:application/json;charset=utf-8," + encodeURIComponent(JSON.stringify(payload, null, 2));
    await chrome.downloads.download({url, filename, saveAs: false, conflictAction: "uniquify"});
    await chrome.action.setBadgeBackgroundColor({tabId: tab.id, color: page.page_error ? "#a00" : "#167c3a"});
    await chrome.action.setBadgeText({tabId: tab.id, text: page.page_error ? "ERR" : String(payload.records.length)});
  } catch (error) {
    await chrome.action.setBadgeBackgroundColor({tabId: tab.id, color: "#a00"});
    await chrome.action.setBadgeText({tabId: tab.id, text: "ERR"});
    console.error("Capture failed", error);
  }
});
