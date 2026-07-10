#!/usr/bin/env python3
"""
淘宝电火灶爬虫 - CDP浏览器自动化
- 使用独立Chrome实例（端口9223）
- 等待用户手动登录淘宝
- 搜索关键词：电火灶、电焰灶、电燃灶
- 提取商品数据：标题、价格、店铺、销量、URL
- 数据写入SQLite (platform='taobao')
"""
import json
import time
import sqlite3
import re
import os
import sys
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "ecommerce.db")

KEYWORDS = ["电火灶", "电焰灶", "电燃灶", "电火灶 商用", "电火灶 家用", "电火灶 双灶"]
PAGES_PER_KEYWORD = 2

# Taobao搜索结果提取JS
EXTRACT_JS = r"""
(function() {
    try {
        var results = [];
        var seen = {};

        // 淘宝搜索结果卡片选择器（多种可能）
        var selectors = [
            '[class*="Content--content"]',
            '[class*="Card--doubleCardWrapper"]',
            'div[class*="m-itemlist"] div.items',
            '[data-spm*="dlist"]',
            '.J_TItems .item',
            '[class*="offer-list"] [class*="offer-card"]',
            'div[class*="SearchItem"]',
            '[class*="search-content"] [class*="item"]'
        ];

        var cards = [];
        for (var s = 0; s < selectors.length; s++) {
            var found = document.querySelectorAll(selectors[s]);
            if (found.length > 0) {
                cards = found;
                break;
            }
        }

        // 如果没找到，用通用方法搜索包含价格和标题的容器
        if (cards.length === 0) {
            var allDivs = document.querySelectorAll('div');
            for (var i = 0; i < allDivs.length; i++) {
                var d = allDivs[i];
                var hasPrice = false;
                var hasTitle = false;
                var children = d.children;
                if (children.length > 1 && children.length < 10) {
                    for (var j = 0; j < children.length; j++) {
                        var t = children[j].textContent;
                        if (t && t.match(/\d+\.\d{2}/) && t.length < 20) hasPrice = true;
                        if (t && t.length > 10 && t.length < 200) hasTitle = true;
                    }
                    if (hasPrice && hasTitle) {
                        cards.push(d);
                    }
                }
            }
        }

        for (var i = 0; i < cards.length && i < 60; i++) {
            var card = cards[i];
            var cardText = card.textContent || '';

            // 跳过不含关键词的卡片
            if (cardText.indexOf('\u7535') === -1 && cardText.indexOf('\u7076') === -1 && cardText.indexOf('\u7130') === -1) continue;

            // 提取标题
            var title = '';
            var titleEls = card.querySelectorAll('a, span, div, p, [class*="title"], [class*="Title"]');
            for (var j = 0; j < titleEls.length; j++) {
                var t = titleEls[j].textContent.trim();
                if (t.length > 8 && t.length < 200 &&
                    (t.indexOf('\u7535') > -1 || t.indexOf('\u7076') > -1 || t.indexOf('\u7130') > -1) &&
                    t.indexOf('\u00a5') === -1 && t.indexOf('\uffe5') === -1) {
                    if (t.length > title.length) title = t;
                }
            }

            if (!title || title.length < 5) continue;

            // 去重
            var titleKey = title.substring(0, 30);
            if (seen[titleKey]) continue;
            seen[titleKey] = true;

            // 提取价格
            var price = 0;
            var priceEls = card.querySelectorAll('span, em, strong, div, [class*="price"], [class*="Price"]');
            for (var j = 0; j < priceEls.length; j++) {
                var t = priceEls[j].textContent.trim();
                var m = t.match(/(\d+(?:\.\d{1,2})?)/);
                if (m && t.length < 15) {
                    var p = parseFloat(m[1]);
                    if (p > 50 && p < 100000) {
                        // 检查是否是价格（前面有¥或￥符号，或在price class中）
                        var cls = priceEls[j].className || '';
                        var prevText = priceEls[j].previousElementSibling ? priceEls[j].previousElementSibling.textContent : '';
                        if (cls.indexOf('price') > -1 || cls.indexOf('Price') > -1 ||
                            prevText.indexOf('\u00a5') > -1 || prevText.indexOf('\uffe5') > -1 ||
                            t.indexOf('\u00a5') > -1 || t.indexOf('\uffe5') > -1) {
                            price = p;
                            break;
                        }
                    }
                }
            }
            // 如果没找到价格，尝试找最大的数字（可能是价格）
            if (!price) {
                for (var j = 0; j < priceEls.length; j++) {
                    var t = priceEls[j].textContent.trim();
                    var m = t.match(/^(\d+(?:\.\d{1,2})?)$/);
                    if (m) {
                        var p = parseFloat(m[1]);
                        if (p > 100 && p < 100000) { price = p; break; }
                    }
                }
            }

            // 提取店铺名
            var shop = '';
            var shopEls = card.querySelectorAll('a, span, div, [class*="shop"], [class*="Shop"], [class*="store"], [class*="Store"]');
            for (var j = 0; j < shopEls.length; j++) {
                var t = shopEls[j].textContent.trim();
                if (t.indexOf('\u5e97') > -1 && t.length < 30) {
                    shop = t;
                    break;
                }
            }

            // 提取销量
            var sales = '';
            var salesEls = card.querySelectorAll('span, div, [class*="sale"], [class*="Sale"], [class*="deal"], [class*="Deal"]');
            for (var j = 0; j < salesEls.length; j++) {
                var t = salesEls[j].textContent.trim();
                if ((t.indexOf('\u4ed8') > -1 || t.indexOf('\u4ef6') > -1 || t.indexOf('\u4eba') > -1 || t.indexOf('\u8d2d\u4e70') > -1) && t.length < 30) {
                    sales = t;
                    break;
                }
            }

            // 提取链接
            var link = '';
            var linkEl = card.querySelector('a[href*="item.taobao"], a[href*="detail.tmall"], a[href*="chaoshi.detail"]');
            if (linkEl) link = linkEl.href;
            if (!link) {
                var anyLink = card.querySelector('a[href]');
                if (anyLink) link = anyLink.href;
            }

            // 提取位置/地域
            var location = '';
            var locEls = card.querySelectorAll('span, div, [class*="location"], [class*="Location"], [class*="area"]');
            for (var j = 0; j < locEls.length; j++) {
                var t = locEls[j].textContent.trim();
                if (t.length >= 2 && t.length <= 10 && /^[\u4e00-\u9fa5]+$/.test(t) &&
                    t.indexOf('\u5e97') === -1 && t.indexOf('\u4ef7') === -1) {
                    location = t;
                    break;
                }
            }

            // 提取商品图片URL
            var imgUrl = '';
            var imgEl = card.querySelector('img[src], img[data-src]');
            if (imgEl) {
                imgUrl = imgEl.getAttribute('src') || imgEl.getAttribute('data-src') || '';
                if (imgUrl.indexOf('//') === 0) imgUrl = 'https:' + imgUrl;
            }

            results.push({
                title: title,
                price: price,
                shop_name: shop,
                sales_text: sales,
                location: location,
                url: link,
                image_url: imgUrl
            });
        }

        return JSON.stringify(results);
    } catch(e) {
        return JSON.stringify({error: e.message});
    }
})();
"""


def ensure_chrome_taobao(port=9223):
    """启动独立Chrome实例用于淘宝采集"""
    try:
        resp = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=2)
        if resp.status_code == 200:
            print(f"  [Chrome-Taobao] 调试端口 {port} 已就绪")
            return True
    except Exception:
        pass

    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if not os.path.exists(chrome_path):
        print("  [Chrome-Taobao] 未找到Chrome!")
        return False

    subprocess.Popen([
        chrome_path,
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--no-sandbox",
        "--disable-gpu",
        "--user-data-dir=/tmp/chrome_taobao",
        "--window-size=1920,1080",
        "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    import requests as req
    for _ in range(10):
        time.sleep(1)
        try:
            resp = req.get(f"http://127.0.0.1:{port}/json/version", timeout=2)
            if resp.status_code == 200:
                print(f"  [Chrome-Taobao] 调试端口 {port} 已启动")
                return True
        except Exception:
            pass

    print("  [Chrome-Taobao] 启动失败!")
    return False


class TaobaoSpider:
    def __init__(self):
        sys.path.insert(0, BASE_DIR)
        from cdp_browser import CDPBrowser
        self.CDPBrowser = CDPBrowser
        self.browser = None
        self.db = sqlite3.connect(DB_PATH)
        self.db.row_factory = sqlite3.Row

    def setup_db(self):
        c = self.db.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id     TEXT UNIQUE,
                platform       TEXT,
                keyword        TEXT,
                title          TEXT,
                price          REAL,
                original_price REAL,
                shop_name      TEXT,
                brand          TEXT,
                model          TEXT,
                url            TEXT,
                image_url      TEXT,
                comment_count  INTEGER DEFAULT 0,
                good_count     INTEGER DEFAULT 0,
                general_count  INTEGER DEFAULT 0,
                poor_count     INTEGER DEFAULT 0,
                good_rate      REAL,
                general_rate   REAL,
                poor_rate      REAL,
                sales_text     TEXT,
                created_at     TEXT DEFAULT (datetime('now', 'localtime')),
                updated_at     TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id  TEXT,
                platform    TEXT,
                content     TEXT,
                score       INTEGER,
                nickname    TEXT,
                review_date TEXT,
                variant     TEXT,
                is_default  INTEGER DEFAULT 0,
                images      TEXT,
                created_at  TEXT DEFAULT (datetime('now', 'localtime')),
                UNIQUE(product_id, content, nickname, review_date)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS search_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword     TEXT,
                page        INTEGER,
                platform    TEXT,
                result_count INTEGER,
                created_at  TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        self.db.commit()

    def start_browser(self):
        ensure_chrome_taobao(9223)
        self.browser = self.CDPBrowser("127.0.0.1", 9223)
        self.browser.block_resources()
        print("[浏览器] 淘宝采集Chrome已启动 (端口9223)")

    def wait_for_login(self, max_wait=300):
        """检测淘宝登录页，等待用户手动登录"""
        url = self.browser.get_url() or ""
        title = self.browser.get_title() or ""

        if "login" in url.lower() or "登录" in title or "login.taobao" in url:
            print("\n" + "=" * 60)
            print("  ⚠️  检测到淘宝登录页面！")
            print("  请在弹出的Chrome浏览器中手动登录淘宝/天猫")
            print("  支持扫码登录或账号密码登录")
            print("  登录成功后，脚本会自动检测并继续采集")
            print(f"  最多等待 {max_wait} 秒...")
            print("=" * 60 + "\n")

            start = time.time()
            while time.time() - start < max_wait:
                time.sleep(3)
                current_url = self.browser.get_url() or ""
                current_title = self.browser.get_title() or ""

                if "login" not in current_url.lower() and "login.taobao" not in current_url:
                    if "登录" not in current_title:
                        print("\n[登录] ✅ 检测到登录成功！继续采集...\n")
                        time.sleep(2)
                        return True
                    else:
                        elapsed = int(time.time() - start)
                        print(f"  [登录] 等待中... ({elapsed}s)")
                else:
                    elapsed = int(time.time() - start)
                    print(f"  [登录] 等待中... ({elapsed}s)")

            print("\n[登录] ⏰ 等待超时，跳过")
            return False
        return True

    def scrape_search_page(self, keyword, page=1):
        """爬取淘宝搜索结果页"""
        url = f"https://s.taobao.com/search?q={keyword}&s={(page-1)*44}"

        print(f"\n[搜索] 关键词='{keyword}' 第{page}页")
        self.browser.navigate(url, wait_sec=5)

        # 检查登录
        if not self.wait_for_login():
            return []

        # 等待页面渲染
        time.sleep(3)

        # 滚动触发懒加载
        for i in range(5):
            self.browser.evaluate(f"window.scrollTo(0, {800 * (i + 1)})")
            time.sleep(0.5)
        time.sleep(1)

        # 检查是否有商品
        page_text = self.browser.evaluate("document.body.innerText") or ""
        if len(page_text) < 100:
            print("  [搜索] 页面内容过少，可能未加载")
            debug_path = os.path.join(BASE_DIR, "data", f"taobao_debug_{keyword}_p{page}.html")
            html = self.browser.get_html() or ""
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(html)
            return []

        # 提取商品
        products_json = self.browser.evaluate(EXTRACT_JS)

        if not products_json:
            print("  [搜索] evaluate返回空")
            return []

        try:
            data = json.loads(products_json)
        except:
            print(f"  [搜索] JSON解析失败")
            return []

        if isinstance(data, dict) and "error" in data:
            print(f"  [搜索] JS错误: {data['error']}")
            return []

        products = data if isinstance(data, list) else []
        print(f"  [搜索] 提取到 {len(products)} 个商品")

        for p in products[:5]:
            print(f"    - {p['title'][:50]}")
            print(f"      ¥{p['price']} {p.get('shop_name','')} {p.get('sales_text','')}")

        return products

    def save_product(self, product, keyword):
        c = self.db.cursor()

        # 生成唯一product_id
        url = product.get("url", "")
        product_id = ""
        if url:
            m = re.search(r'id=(\d+)', url)
            if m:
                product_id = "tb_" + m.group(1)
            else:
                product_id = "tb_" + str(hash(url) % 10**15)
        if not product_id:
            product_id = "tb_" + str(hash(product.get("title", "")) % 10**15)

        # 从标题提取品牌
        brand = self._extract_brand(product.get("title", ""))

        c.execute("""
            INSERT INTO products (product_id, platform, keyword, title, price,
                                   shop_name, brand, url, image_url, sales_text)
            VALUES (?, 'taobao', ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(product_id) DO UPDATE SET
                title=excluded.title, price=excluded.price,
                shop_name=excluded.shop_name, sales_text=excluded.sales_text,
                updated_at=datetime('now','localtime')
        """, (
            product_id,
            keyword,
            product.get("title", ""),
            product.get("price", 0),
            product.get("shop_name", ""),
            brand,
            product.get("url", ""),
            product.get("image_url", ""),
            product.get("sales_text", ""),
        ))
        self.db.commit()

    def _extract_brand(self, title):
        brands = ["华火", "星焰", "星煜", "卡曼森", "美的", "荣事达", "先科",
                  "德玛仕", "老板", "尚朋堂", "硕高", "国爱", "九电", "燚龙",
                  "东洋", "内芙", "富得莱", "微致", "德克士", "志高", "欢度",
                  "奥田美太", "西屋", "TINME", "红日", "万和", "半球", "方太",
                  "苏泊尔", "九阳", "海尔", "格力", "艾美特"]
        for b in brands:
            if b in title:
                return b
        return ""

    def log_search(self, keyword, page, count):
        c = self.db.cursor()
        c.execute("""
            INSERT INTO search_log (keyword, page, platform, result_count)
            VALUES (?, ?, 'taobao', ?)
        """, (keyword, page, count))
        self.db.commit()

    def run(self):
        self.setup_db()
        self.start_browser()

        # 访问淘宝首页
        print("\n[Step 1] 访问淘宝首页...")
        self.browser.navigate("https://www.taobao.com/", wait_sec=3)
        if not self.wait_for_login():
            print("[!] 淘宝要求登录，请先登录再运行")
            return

        total_products = 0

        # 搜索采集
        for keyword in KEYWORDS:
            for page in range(1, PAGES_PER_KEYWORD + 1):
                print(f"\n{'='*50}")
                print(f"[Step 2] 搜索: '{keyword}' 第{page}/{PAGES_PER_KEYWORD}页")
                print(f"{'='*50}")

                products = self.scrape_search_page(keyword, page)

                if not products:
                    self.log_search(keyword, page, 0)
                    continue

                self.log_search(keyword, page, len(products))

                for p in products:
                    self.save_product(p, keyword)
                    total_products += 1

                print(f"  [保存] 累计商品: {total_products}")

            time.sleep(2)

        # 汇总
        print(f"\n{'='*50}")
        print(f"  淘宝采集完成！")
        print(f"  总商品数: {total_products}")
        print(f"  数据库: {DB_PATH}")
        print(f"{'='*50}")

        self.browser.close()
        self.db.close()


if __name__ == "__main__":
    spider = TaobaoSpider()
    spider.run()
