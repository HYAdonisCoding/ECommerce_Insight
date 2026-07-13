#!/usr/bin/env python3
"""
淘宝电火灶爬虫 v4 - 基于实际DOM分析
商品卡片: div[class*="doubleCard--"]
标题: [class*="title--"]
价格: ¥符号后的数字
销量: XX人付款
"""
import json
import time
import sqlite3
import re
import os
import sys
import subprocess
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "ecommerce.db")

KEYWORDS = ["电火灶", "电焰灶", "电燃灶", "电火灶商用", "电火灶家用", "电火灶双灶"]
PAGES_PER_KEYWORD = 3


def ensure_chrome(port=9223):
    try:
        resp = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=2)
        if resp.status_code == 200:
            print(f"  [Chrome] 端口 {port} 已就绪", flush=True)
            return True
    except Exception:
        pass

    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    subprocess.Popen([
        chrome_path,
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        "--no-first-run", "--no-default-browser-check",
        "--no-sandbox", "--disable-gpu",
        "--user-data-dir=/tmp/chrome_taobao",
        "--window-size=1920,1080",
        "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for _ in range(15):
        time.sleep(1)
        try:
            resp = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=2)
            if resp.status_code == 200:
                print(f"  [Chrome] 端口 {port} 已启动", flush=True)
                return True
        except Exception:
            pass
    return False


# 基于实际DOM分析的提取JS
EXTRACT_JS = r"""
(function() {
    try {
        var results = [];
        var seen = {};

        // 选择所有商品卡片
        var cards = document.querySelectorAll('div[class*="doubleCard--"]');
        
        // 如果没找到，尝试其他选择器
        if (cards.length === 0) {
            var altSelectors = [
                '[class*="contentItem--"]',
                '[class*="search-item"]',
                '[class*="Card--doubleCard"]'
            ];
            for (var s = 0; s < altSelectors.length; s++) {
                var found = document.querySelectorAll(altSelectors[s]);
                if (found.length > 0) { cards = found; break; }
            }
        }

        for (var i = 0; i < cards.length && i < 80; i++) {
            var card = cards[i];
            var cardText = card.textContent || '';

            // 提取标题 - 从title class元素获取
            var title = '';
            var titleEl = card.querySelector('[class*="title--"]');
            if (titleEl) {
                title = titleEl.textContent.trim();
            }
            // 如果没找到title class，尝试从整个卡片文本提取
            if (!title || title.length < 5) {
                // 标题通常在卡片文本的开头部分
                var lines = cardText.split(/[\n\r]+/);
                for (var l = 0; l < lines.length; l++) {
                    var line = lines[l].trim();
                    if (line.length > 8 && line.length < 200 &&
                        (line.indexOf('\u7535') > -1 || line.indexOf('\u7076') > -1 || line.indexOf('\u7130') > -1) &&
                        line.indexOf('\u4eba\u4ed8\u6b3e') === -1 && line.indexOf('\u770b\u8fc7') === -1) {
                        title = line;
                        break;
                    }
                }
            }

            if (!title || title.length < 5) continue;

            // 去重
            var titleKey = title.substring(0, 30);
            if (seen[titleKey]) continue;
            seen[titleKey] = true;

            // 提取价格 - 找¥符号后的数字
            var price = 0;
            var priceMatch = cardText.match(/\u00a5\s*(\d+(?:\.\d{1,2})?)/);
            if (priceMatch) {
                price = parseFloat(priceMatch[1]);
            } else {
                // 也尝试￥(全角)
                priceMatch = cardText.match(/\uffe5\s*(\d+(?:\.\d{1,2})?)/);
                if (priceMatch) price = parseFloat(priceMatch[1]);
            }
            // 如果还没找到，尝试找独立的数字
            if (!price) {
                var allText = cardText;
                var m = allText.match(/(\d{3,5}(?:\.\d{1,2})?)/);
                if (m) {
                    var p = parseFloat(m[1]);
                    if (p > 100 && p < 100000) price = p;
                }
            }

            // 提取销量 - "XX人付款" 或 "XX人付款"
            var sales = '';
            var salesMatch = cardText.match(/(\d+\+?\s*\u4eba\u4ed8\u6b3e)/);
            if (salesMatch) sales = salesMatch[1];
            if (!sales) {
                salesMatch = cardText.match(/(\d+\+?\s*\u6708\u9500)/);
                if (salesMatch) sales = salesMatch[1];
            }
            if (!sales) {
                salesMatch = cardText.match(/(\d+\+?\s*\u5df2\u552e)/);
                if (salesMatch) sales = salesMatch[1];
            }

            // 提取位置 - 在"人付款"后面的省市
            var location = '';
            var locMatch = cardText.match(/\u4eba\u4ed8\u6b3e\s*([\u4e00-\u9fa5]{2,4})\s+([\u4e00-\u9fa5]{2,4})/);
            if (locMatch) {
                location = locMatch[1] + ' ' + locMatch[2];
            } else {
                locMatch = cardText.match(/\u4eba\u4ed8\u6b3e\s*([\u4e00-\u9fa5]{2,})/);
                if (locMatch) location = locMatch[1];
            }

            // 提取店铺名 - 可能在卡片外层
            var shop = '';
            var shopEl = card.querySelector('[class*="shop"], [class*="Shop"], [class*="store"], [class*="Store"], [class*="nick"]');
            if (shopEl) shop = shopEl.textContent.trim();

            // 提取标签信息
            var tags = [];
            var tagEls = card.querySelectorAll('[class*="tag"], [class*="Tag"], [class*="icon"]');
            for (var t = 0; t < tagEls.length; t++) {
                var tagText = tagEls[t].textContent.trim();
                if (tagText.length > 0 && tagText.length < 15 && 
                    tagText.indexOf('\u4eba\u4ed8\u6b3e') === -1) {
                    tags.push(tagText);
                }
            }

            // 提取链接
            var link = '';
            var linkEl = card.querySelector('a[href]');
            if (linkEl) link = linkEl.href;

            // 提取图片
            var imgUrl = '';
            var imgEl = card.querySelector('img[src], img[data-src]');
            if (imgEl) {
                imgUrl = imgEl.getAttribute('src') || imgEl.getAttribute('data-src') || '';
                if (imgUrl.indexOf('//') === 0) imgUrl = 'https:' + imgUrl;
            }

            // 从标题提取品牌
            var brand = '';
            var brandList = ['\u534e\u706b', '\u661f\u7130', '\u661f\u7164', '\u5361\u66fc\u68ee', '\u7f8e\u7684',
                '\u8363\u4e8b\u8fbe', '\u5148\u79d1', '\u5fb7\u739b\u4ed5', '\u8001\u677f', '\u5c1a\u670b\u5802',
                '\u7855\u9ad8', '\u56fd\u7231', '\u4e5d\u7535', '\u71da\u9f99', '\u4e1c\u6d0b', '\u5185\u8299',
                '\u5bcc\u5f97\u83b1', '\u5fae\u81f4', '\u5fd7\u9ad8', '\u5965\u7530\u7f8e\u592a',
                '\u897f\u5c4b', '\u7ea2\u65e5', '\u4e07\u548c', '\u534a\u7403', '\u65b9\u592a',
                '\u82cf\u6cca\u5c14', '\u4e5d\u9633', '\u6d77\u5c14', '\u683c\u529b', '\u827e\u7f8e\u7279',
                '\u661f\u7164', '\u5bcc\u683c', '\u5e10\u58c1\u7089', '\u6d77\u68ee\u6d77\u7279',
                '\u6a31\u82b1', '\u5e05\u4e30', '\u7f8e\u5927', '\u68ee\u6b4c', '\u4ebf\u7530', '\u706b\u661f\u4eba'];
            for (var b = 0; b < brandList.length; b++) {
                if (title.indexOf(brandList[b]) > -1) { brand = brandList[b]; break; }
            }

            results.push({
                title: title,
                price: price,
                shop_name: shop,
                brand: brand,
                sales_text: sales,
                location: location,
                url: link,
                image_url: imgUrl,
                tags: tags.join(', ')
            });
        }

        return JSON.stringify(results);
    } catch(e) {
        return JSON.stringify({error: e.message});
    }
})();
"""


class TaobaoSpiderV4:
    def __init__(self):
        sys.path.insert(0, BASE_DIR)
        from cdp_browser import CDPBrowser
        self.CDPBrowser = CDPBrowser
        self.browser = None
        self.db = sqlite3.connect(DB_PATH)

    def setup_db(self):
        c = self.db.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT UNIQUE, platform TEXT, keyword TEXT,
            title TEXT, price REAL, original_price REAL,
            shop_name TEXT, brand TEXT, model TEXT,
            url TEXT, image_url TEXT,
            comment_count INTEGER DEFAULT 0, good_count INTEGER DEFAULT 0,
            general_count INTEGER DEFAULT 0, poor_count INTEGER DEFAULT 0,
            good_rate REAL, general_rate REAL, poor_rate REAL,
            sales_text TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT, platform TEXT, content TEXT,
            score INTEGER, nickname TEXT, review_date TEXT,
            variant TEXT, is_default INTEGER DEFAULT 0,
            images TEXT, created_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(product_id, content, nickname, review_date)
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS search_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT, page INTEGER, platform TEXT,
            result_count INTEGER, created_at TEXT DEFAULT (datetime('now','localtime'))
        )""")
        self.db.commit()

    def start_browser(self):
        ensure_chrome(9223)
        self.browser = self.CDPBrowser("127.0.0.1", 9223)
        self.browser.block_resources()
        print("[浏览器] Chrome已启动", flush=True)

    def scrape_search(self, keyword, page=1):
        url = f"https://s.taobao.com/search?q={keyword}&s={(page-1)*44}"
        print(f"\n[搜索] '{keyword}' 第{page}页", flush=True)
        self.browser.navigate(url, wait_sec=5)
        time.sleep(3)

        # 滚动触发懒加载
        for i in range(6):
            self.browser.evaluate(f"window.scrollTo(0, {600*(i+1)})")
            time.sleep(0.5)
        time.sleep(2)

        # 检查是否需要登录
        page_text = self.browser.evaluate("document.body.innerText") or ""
        if "请登录" in page_text or "登录后查看" in page_text:
            print("  [搜索] 需要登录，等待...", flush=True)
            self.browser.navigate("https://login.taobao.com/", wait_sec=3)
            for i in range(60):
                time.sleep(3)
                cur_url = self.browser.get_url() or ""
                if "login.taobao" not in cur_url:
                    print("  [登录] 成功！重新搜索", flush=True)
                    self.browser.navigate(url, wait_sec=5)
                    time.sleep(3)
                    for j in range(4):
                        self.browser.evaluate(f"window.scrollTo(0, {600*(j+1)})")
                        time.sleep(0.5)
                    time.sleep(2)
                    break
                if i % 5 == 0:
                    print(f"  [登录] 等待... ({i*3}s)", flush=True)

        # 提取商品
        result = self.browser.evaluate(EXTRACT_JS)
        if not result:
            print("  [搜索] 提取返回空", flush=True)
            return []

        try:
            data = json.loads(result)
        except:
            print("  [搜索] JSON解析失败", flush=True)
            return []

        if isinstance(data, dict) and "error" in data:
            print(f"  [搜索] JS错误: {data['error']}", flush=True)
            return []

        products = data if isinstance(data, list) else []
        print(f"  [搜索] 提取到 {len(products)} 个商品", flush=True)
        for p in products[:5]:
            print(f"    - {p['title'][:50]} ¥{p['price']} {p.get('sales_text','')}", flush=True)

        return products

    def save_product(self, product, keyword):
        c = self.db.cursor()
        url = product.get("url", "")
        product_id = ""
        if url:
            m = re.search(r'id=(\d+)', url)
            if m: product_id = "tb_" + m.group(1)
            else:
                m = re.search(r'(\d{10,})', url)
                if m: product_id = "tb_" + m.group(1)
        if not product_id:
            product_id = "tb_" + str(abs(hash(product.get("title", ""))) % 10**15)

        c.execute("""
            INSERT INTO products (product_id, platform, keyword, title, price,
                                   shop_name, brand, url, image_url, sales_text)
            VALUES (?, 'taobao', ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(product_id) DO UPDATE SET
                title=excluded.title, price=excluded.price,
                shop_name=COALESCE(NULLIF(shop_name,''), excluded.shop_name),
                sales_text=excluded.sales_text,
                updated_at=datetime('now','localtime')
        """, (product_id, keyword, product.get("title", ""),
              product.get("price", 0), product.get("shop_name", ""),
              product.get("brand", ""), product.get("url", ""),
              product.get("image_url", ""), product.get("sales_text", "")))
        self.db.commit()

    def log_search(self, keyword, page, count):
        c = self.db.cursor()
        c.execute("INSERT INTO search_log (keyword, page, platform, result_count) VALUES (?, ?, 'taobao', ?)",
                  (keyword, page, count))
        self.db.commit()

    def run(self):
        self.setup_db()
        self.start_browser()

        # 访问淘宝首页检查登录
        self.browser.navigate("https://www.taobao.com/", wait_sec=3)
        page_text = self.browser.evaluate("document.body.innerText") or ""
        if "请登录" in page_text or "亲，请登录" in page_text:
            print("\n[!] 需要登录淘宝，正在跳转登录页...", flush=True)
            self.browser.navigate("https://login.taobao.com/", wait_sec=3)
            print("  请在Chrome中登录淘宝...", flush=True)
            for i in range(100):
                time.sleep(3)
                cur_url = self.browser.get_url() or ""
                if "login.taobao" not in cur_url:
                    print("  [登录] 成功！开始采集", flush=True)
                    break
                if i % 5 == 0:
                    print(f"  [登录] 等待... ({i*3}s)", flush=True)

        total = 0
        for keyword in KEYWORDS:
            for page in range(1, PAGES_PER_KEYWORD + 1):
                products = self.scrape_search(keyword, page)
                if not products:
                    self.log_search(keyword, page, 0)
                    continue
                self.log_search(keyword, page, len(products))
                for p in products:
                    self.save_product(p, keyword)
                    total += 1
                print(f"  [保存] 累计: {total}", flush=True)
            time.sleep(2)

        print(f"\n{'='*50}", flush=True)
        print(f"  淘宝采集完成！总商品: {total}", flush=True)
        print(f"{'='*50}", flush=True)
        self.browser.close()
        self.db.close()


if __name__ == "__main__":
    spider = TaobaoSpiderV4()
    spider.run()
