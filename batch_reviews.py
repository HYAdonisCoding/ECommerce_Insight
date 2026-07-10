#!/usr/bin/env python3
"""批量采集京东商品评价摘要 - 后台运行版本"""
import json, time, sqlite3, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_browser import CDPBrowser, ensure_chrome

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ecommerce.db")
db = sqlite3.connect(DB_PATH)

c = db.cursor()
c.execute("SELECT product_id FROM products WHERE comment_count = 0 ORDER BY id")
skus = [r[0] for r in c.fetchall()]
print(f"待采集: {len(skus)} 个商品", flush=True)

SUMMARY_JS = r"""
(function() {
    try {
        var commentCount = 0;
        var goodRate = 0;
        var els = document.querySelectorAll('a, span, div, em');
        for (var i = 0; i < els.length; i++) {
            var t = els[i].textContent.trim();
            if (t.indexOf('\u8bc4\u4ef7') > -1 && t.length < 30) {
                var m = t.match(/(\d+)/);
                if (m) { commentCount = parseInt(m[1]); if (t.indexOf('\u4e07') > -1) commentCount *= 10000; break; }
            }
        }
        var rateEls = document.querySelectorAll('span, div, em');
        for (var i = 0; i < rateEls.length; i++) {
            var t = rateEls[i].textContent.trim();
            if (t.indexOf('\u597d\u8bc4') > -1 && t.indexOf('%') > -1 && t.length < 30) {
                var m = t.match(/(\d+(?:\.\d+)?)\s*%/);
                if (m) { goodRate = parseFloat(m[1]); break; }
            }
        }
        return JSON.stringify({comment_count: commentCount, good_rate: goodRate});
    } catch(e) { return JSON.stringify({error: e.message}); }
})();
"""

ensure_chrome(9222)
browser = CDPBrowser("127.0.0.1", 9222)
browser.block_resources()
browser.navigate("https://www.jd.com/", wait_sec=2)

success = 0
fail = 0

for i, sku in enumerate(skus):
    browser.navigate(f"https://item.jd.com/{sku}.html", wait_sec=3)

    cur_url = browser.get_url() or ""
    if "login" in cur_url.lower():
        print(f"  [{i+1}/{len(skus)}] {sku}: 登录页跳过", flush=True)
        continue

    time.sleep(1)
    browser.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.7)")
    time.sleep(0.5)

    result = browser.evaluate(SUMMARY_JS)
    if result:
        try:
            data = json.loads(result)
            cc = data.get("comment_count", 0)
            gr = data.get("good_rate", 0)
            if cc > 0:
                c = db.cursor()
                c.execute("UPDATE products SET comment_count=?, good_rate=?, updated_at=datetime('now','localtime') WHERE product_id=?", (cc, gr, sku))
                db.commit()
                success += 1
                if (i+1) % 10 == 0 or cc >= 100:
                    print(f"  [{i+1}/{len(skus)}] {sku}: 评价{cc}条 好评率{gr}%", flush=True)
            else:
                fail += 1
        except:
            fail += 1
    else:
        fail += 1

    time.sleep(0.3)

print(f"\n完成! 成功: {success} 失败: {fail}", flush=True)
browser.close()
db.close()
