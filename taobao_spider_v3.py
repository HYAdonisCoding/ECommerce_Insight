#!/usr/bin/env python3
"""
淘宝电火灶爬虫 v3 - 先登录后搜索
解决淘宝不跳转登录页直接返回空结果的问题
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
            print(f"  [Chrome] 端口 {port} 已就绪")
            return True
    except Exception:
        pass

    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if not os.path.exists(chrome_path):
        print("  [Chrome] 未找到Chrome!")
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

    for _ in range(15):
        time.sleep(1)
        try:
            resp = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=2)
            if resp.status_code == 200:
                print(f"  [Chrome] 端口 {port} 已启动")
                return True
        except Exception:
            pass

    print("  [Chrome] 启动失败!")
    return False


# 淘宝搜索结果提取JS - 更全面的选择器
EXTRACT_JS = r"""
(function() {
    try {
        var results = [];
        var seen = {};

        // 策略1: 淘宝新版搜索结果 (Content--contentInner 等 hashed class)
        var cardSelectors = [
            '[class*="Content--contentInner"]',
            '[class*="Card--doubleCard"]',
            '[class*="Card--singleCard"]',
            '[class*="m-itemlist"] div.items .item',
            '[class*="SearchItem"]',
            '[class*="offer-list"] [class*="offer-card"]',
            '[class*="search-content"] [class*="item"]',
            'div[data-spm*="dlist"]',
            '.J_TItems .item',
            'div[class*="DoubleCardWrapper"]'
        ];

        var cards = [];
        for (var s = 0; s < cardSelectors.length; s++) {
            var found = document.querySelectorAll(cardSelectors[s]);
            if (found.length > 0) {
                cards = found;
                console.log('Found with selector: ' + cardSelectors[s] + ' count=' + found.length);
                break;
            }
        }

        // 策略2: 如果没找到卡片，用通用方法找包含价格和标题的容器
        if (cards.length === 0) {
            var allDivs = document.querySelectorAll('div');
            for (var i = 0; i < allDivs.length && cards.length < 100; i++) {
                var d = allDivs[i];
                var children = d.children;
                if (children.length >= 2 && children.length <= 12) {
                    var hasPrice = false;
                    var hasTitle = false;
                    for (var j = 0; j < children.length; j++) {
                        var t = children[j].textContent || '';
                        if (t.match(/\d+\.\d{2}/) && t.length < 20) hasPrice = true;
                        if (t.length > 10 && t.length < 200) hasTitle = true;
                    }
                    if (hasPrice && hasTitle) {
                        cards.push(d);
                    }
                }
            }
        }

        // 策略3: 查找所有带链接的元素，看是否是商品
        if (cards.length === 0) {
            var links = document.querySelectorAll('a[href*="item.taobao"], a[href*="detail.tmall"], a[href*="chaoshi.detail"], a[href*="a.m.taobao"]');
            for (var i = 0; i < links.length; i++) {
                var parent = links[i].closest('div, li, article');
                if (parent && parent.textContent.length > 10) {
                    cards.push(parent);
                }
            }
        }

        for (var i = 0; i < cards.length && i < 80; i++) {
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
                        var cls = priceEls[j].className || '';
                        if (cls.indexOf('price') > -1 || cls.indexOf('Price') > -1 ||
                            t.indexOf('\u00a5') > -1 || t.indexOf('\uffe5') > -1) {
                            price = p;
                            break;
                        }
                    }
                }
            }
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
            var shopEls = card.querySelectorAll('a, span, div, [class*="shop"], [class*="Shop"], [class*="store"], [class*="Store"], [class*="nick"]');
            for (var j = 0; j < shopEls.length; j++) {
                var t = shopEls[j].textContent.trim();
                if (t.length > 1 && t.length < 30 &&
                    (t.indexOf('\u5e97') > -1 || t.indexOf('\u65d7\u8230') > -1 || t.indexOf('\u4e13\u8425') > -1)) {
                    shop = t;
                    break;
                }
            }

            // 提取销量
            var sales = '';
            var salesEls = card.querySelectorAll('span, div, [class*="sale"], [class*="Sale"], [class*="deal"], [class*="Deal"], [class*="realSales"]');
            for (var j = 0; j < salesEls.length; j++) {
                var t = salesEls[j].textContent.trim();
                if ((t.indexOf('\u4ed8') > -1 || t.indexOf('\u4ef6') > -1 || t.indexOf('\u4eba') > -1 || t.indexOf('\u8d2d\u4e70') > -1 || t.indexOf('\u6708\u9500') > -1) && t.length < 30) {
                    sales = t;
                    break;
                }
            }

            // 提取链接
            var link = '';
            var linkEl = card.querySelector('a[href*="item.taobao"], a[href*="detail.tmall"], a[href*="chaoshi.detail"], a[href*="a.m.taobao"]');
            if (linkEl) link = linkEl.href;
            if (!link) {
                var anyLink = card.querySelector('a[href]');
                if (anyLink) link = anyLink.href;
            }

            // 提取位置
            var location = '';
            var locEls = card.querySelectorAll('span, div, [class*="location"], [class*="Location"], [class*="area"], [class*="ship"]');
            for (var j = 0; j < locEls.length; j++) {
                var t = locEls[j].textContent.trim();
                if (t.length >= 2 && t.length <= 10 && /^[\u4e00-\u9fa5]+$/.test(t) &&
                    t.indexOf('\u5e97') === -1 && t.indexOf('\u4ef7') === -1) {
                    location = t;
                    break;
                }
            }

            // 提取图片URL
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


class TaobaoSpiderV3:
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
        self.db.commit()

    def start_browser(self):
        ensure_chrome(9223)
        self.browser = self.CDPBrowser("127.0.0.1", 9223)
        self.browser.block_resources()
        print("[浏览器] Chrome已启动 (端口9223)", flush=True)

    def wait_for_login(self, max_wait=300):
        """强制导航到淘宝登录页，等待用户登录"""
        print("\n" + "=" * 60, flush=True)
        print("  请在Chrome浏览器中登录淘宝/天猫", flush=True)
        print("  支持扫码登录或账号密码登录", flush=True)
        print("  登录成功后脚本自动继续", flush=True)
        print(f"  最多等待 {max_wait} 秒", flush=True)
        print("=" * 60 + "\n", flush=True)

        # 导航到登录页
        self.browser.navigate("https://login.taobao.com/", wait_sec=3)

        start = time.time()
        logged_in = False
        while time.time() - start < max_wait:
            time.sleep(3)
            current_url = self.browser.get_url() or ""
            current_title = self.browser.get_title() or ""

            # 检测是否已离开登录页
            if "login.taobao" not in current_url and "login.tmall" not in current_url:
                if "login" not in current_title.lower() and "登录" not in current_title:
                    # 再验证一下：访问淘宝首页看是否已登录
                    self.browser.navigate("https://www.taobao.com/", wait_sec=2)
                    page_text = self.browser.evaluate("document.body.innerText") or ""
                    # 检查是否有登录后的元素（如"我的淘宝"、用户名等）
                    if "我的淘宝" in page_text or "已登录" in page_text or "购物车" in page_text:
                        print("[登录] 检测到登录成功！继续采集...\n", flush=True)
                        logged_in = True
                        break
                    else:
                        # 可能还是未登录，继续等
                        elapsed = int(time.time() - start)
                        print(f"  [登录] 等待中... ({elapsed}s) URL: {current_url[:50]}", flush=True)
                else:
                    elapsed = int(time.time() - start)
                    print(f"  [登录] 等待中... ({elapsed}s)", flush=True)
            else:
                elapsed = int(time.time() - start)
                print(f"  [登录] 等待中... ({elapsed}s)", flush=True)

        if not logged_in:
            print("[登录] 超时，尝试直接搜索（可能只能看到部分结果）", flush=True)

        return logged_in

    def scrape_search_page(self, keyword, page=1):
        """爬取淘宝搜索结果页"""
        url = f"https://s.taobao.com/search?q={keyword}&s={(page-1)*44}"

        print(f"\n[搜索] 关键词='{keyword}' 第{page}页", flush=True)
        self.browser.navigate(url, wait_sec=5)

        # 等待页面渲染
        time.sleep(3)

        # 滚动触发懒加载
        for i in range(6):
            self.browser.evaluate(f"window.scrollTo(0, {600 * (i + 1)})")
            time.sleep(0.5)
        time.sleep(2)

        # 检查页面内容
        page_text = self.browser.evaluate("document.body.innerText") or ""
        if len(page_text) < 100:
            print("  [搜索] 页面内容过少，可能未加载", flush=True)
            # 保存调试HTML
            debug_path = os.path.join(BASE_DIR, "data", f"taobao_debug_{keyword}_p{page}.html")
            html = self.browser.get_html() or ""
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  [调试] HTML已保存: {debug_path}", flush=True)
            return []

        # 检查是否需要登录
        if "请登录" in page_text or "登录后查看" in page_text or "你还没有登录" in page_text:
            print("  [搜索] 检测到需要登录！请先登录", flush=True)
            self.wait_for_login(180)
            # 重新搜索
            self.browser.navigate(url, wait_sec=5)
            time.sleep(3)
            for i in range(4):
                self.browser.evaluate(f"window.scrollTo(0, {600 * (i + 1)})")
                time.sleep(0.5)
            time.sleep(2)

        # 提取商品
        products_json = self.browser.evaluate(EXTRACT_JS)

        if not products_json:
            print("  [搜索] evaluate返回空", flush=True)
            # 保存调试HTML
            debug_path = os.path.join(BASE_DIR, "data", f"taobao_debug_{keyword}_p{page}.html")
            html = self.browser.get_html() or ""
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(html)
            return []

        try:
            data = json.loads(products_json)
        except:
            print(f"  [搜索] JSON解析失败", flush=True)
            return []

        if isinstance(data, dict) and "error" in data:
            print(f"  [搜索] JS错误: {data['error']}", flush=True)
            return []

        products = data if isinstance(data, list) else []
        print(f"  [搜索] 提取到 {len(products)} 个商品", flush=True)

        for p in products[:5]:
            print(f"    - {p['title'][:50]}", flush=True)
            print(f"      ¥{p['price']} {p.get('shop_name','')} {p.get('sales_text','')}", flush=True)

        return products

    def save_product(self, product, keyword):
        c = self.db.cursor()

        url = product.get("url", "")
        product_id = ""
        if url:
            m = re.search(r'id=(\d+)', url)
            if m:
                product_id = "tb_" + m.group(1)
            else:
                m = re.search(r'(\d{10,})', url)
                if m:
                    product_id = "tb_" + m.group(1)
        if not product_id:
            product_id = "tb_" + str(abs(hash(product.get("title", ""))) % 10**15)

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
                  "苏泊尔", "九阳", "海尔", "格力", "艾美特", "万喜", "樱花",
                  "帅丰", "美大", "森歌", "亿田", "火星人", "金利集成"]
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

        # Step 1: 强制登录
        print("\n[Step 1] 登录淘宝...", flush=True)
        self.wait_for_login(300)

        total_products = 0

        # Step 2: 搜索采集
        for keyword in KEYWORDS:
            for page in range(1, PAGES_PER_KEYWORD + 1):
                print(f"\n{'='*50}", flush=True)
                print(f"[Step 2] 搜索: '{keyword}' 第{page}/{PAGES_PER_KEYWORD}页", flush=True)
                print(f"{'='*50}", flush=True)

                products = self.scrape_search_page(keyword, page)

                if not products:
                    self.log_search(keyword, page, 0)
                    # 如果第一个关键词第一页就没结果，可能登录有问题
                    if keyword == KEYWORDS[0] and page == 1:
                        print("  [警告] 第一个关键词无结果，可能登录失败", flush=True)
                        print("  [警告] 保存页面HTML用于调试...", flush=True)
                        debug_path = os.path.join(BASE_DIR, "data", "taobao_search_debug.html")
                        html = self.browser.get_html() or ""
                        with open(debug_path, "w", encoding="utf-8") as f:
                            f.write(html)
                        print(f"  [调试] 已保存: {debug_path}", flush=True)
                    continue

                self.log_search(keyword, page, len(products))

                for p in products:
                    self.save_product(p, keyword)
                    total_products += 1

                print(f"  [保存] 累计商品: {total_products}", flush=True)

            time.sleep(2)

        # 汇总
        print(f"\n{'='*50}", flush=True)
        print(f"  淘宝采集完成！", flush=True)
        print(f"  总商品数: {total_products}", flush=True)
        print(f"  数据库: {DB_PATH}", flush=True)
        print(f"{'='*50}", flush=True)

        self.browser.close()
        self.db.close()


if __name__ == "__main__":
    spider = TaobaoSpiderV3()
    spider.run()
