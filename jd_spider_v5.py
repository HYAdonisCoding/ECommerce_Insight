#!/usr/bin/env python3
"""
京东电火灶爬虫 V5 - CDP浏览器自动化
- 检测登录页自动暂停，等用户手动登录后继续
- 屏蔽图片/视频/字体加速加载
- 搜索结果页完整提取商品数据（适配京东新版React搜索页）
- JS fetch评价API（同域调用绕过系统繁忙）
- 数据写入SQLite
"""
import json
import time
import sqlite3
import re
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "ecommerce.db")
DATA_DIR = os.path.join(BASE_DIR, "data")

KEYWORDS = [
    "电火灶",
    "电焰灶",
    "电燃灶",
    "电火灶 商用",
    "电火灶 家用",
    "电火灶 双灶",
]

PAGES_PER_KEYWORD = 3

# JS提取逻辑 - 适配京东新版React搜索页
EXTRACT_JS = r"""
(function() {
    try {
        var items = document.querySelectorAll('[data-sku]');
        var results = [];
        var seen = {};

        for (var i = 0; i < items.length; i++) {
            var el = items[i];
            var sku = el.getAttribute('data-sku') || '';
            if (!sku || seen[sku]) continue;
            seen[sku] = true;

            // 标题
            var title = '';
            var titleEl = el.querySelector('span[title]');
            if (titleEl) {
                title = titleEl.getAttribute('title') || titleEl.textContent.trim();
            }
            if (!title) {
                var spans = el.querySelectorAll('span');
                for (var j = 0; j < spans.length; j++) {
                    var t = spans[j].textContent.trim();
                    if (t.length > 10 && t.length < 200 && (t.indexOf('\u7535') > -1 || t.indexOf('\u7076') > -1)) {
                        if (t.length > title.length) title = t;
                    }
                }
            }
            if (!title) continue;

            // 价格: 找 ¥ 符号后面的数字
            var price = 0;
            var allEls = el.querySelectorAll('i, span, em');
            for (var k = 0; k < allEls.length; k++) {
                var txt = allEls[k].textContent.trim();
                if (txt === '\u00a5' || txt === '\uffe5') {
                    var next = allEls[k].nextElementSibling;
                    if (next) {
                        var p = parseFloat(next.textContent.replace(/[^0-9.]/g, ''));
                        if (p > 0) { price = p; break; }
                    }
                }
            }
            if (!price) {
                var numEls = el.querySelectorAll('span');
                for (var k = 0; k < numEls.length; k++) {
                    var t = numEls[k].textContent.trim();
                    if (/^\d{2,6}$/.test(t)) {
                        var p = parseFloat(t);
                        if (p > 100 && p < 100000) { price = p; break; }
                    }
                }
            }

            // 原价
            var origPrice = 0;
            var grayEl = el.querySelector('[class*=gray]');
            if (grayEl) {
                var m = grayEl.textContent.match(/(\d+)/);
                if (m) origPrice = parseFloat(m[1]);
            }

            // 店铺
            var shop = '';
            var shopLink = el.querySelector('a[href*="mall.jd.com"], a[href*="shop.jd.com"]');
            if (shopLink) shop = shopLink.textContent.trim();
            if (!shop) {
                var shopEls = el.querySelectorAll('span, div, a');
                for (var k = 0; k < shopEls.length; k++) {
                    var t = shopEls[k].textContent.trim();
                    if ((t.indexOf('\u81ea\u8425') > -1 || t.indexOf('\u65d7\u8230') > -1 || t.indexOf('\u4e13\u8425') > -1) && t.length < 30) {
                        shop = t; break;
                    }
                }
            }

            // 评论数
            var commentCount = 0;
            var commitText = '';
            var cmtEls = el.querySelectorAll('span, a, div');
            for (var k = 0; k < cmtEls.length; k++) {
                var t = cmtEls[k].textContent.trim();
                if (t.indexOf('\u8bc4\u4ef7') > -1 && t.length < 20) {
                    commitText = t;
                    var m = t.match(/(\d+)/);
                    if (m) commentCount = parseInt(m[1]);
                    if (t.indexOf('\u4e07') > -1) commentCount *= 10000;
                    break;
                }
            }

            // 图片
            var imgUrl = '';
            var imgEl = el.querySelector('img[data-src]');
            if (imgEl) {
                imgUrl = imgEl.getAttribute('data-src') || '';
                if (imgUrl.indexOf('//') === 0) imgUrl = 'https:' + imgUrl;
            }

            // 链接
            var link = 'https://item.jd.com/' + sku + '.html';
            var linkEl = el.querySelector('a[href*="item.jd.com"]');
            if (linkEl) link = linkEl.href;

            // 浏览量
            var viewText = '';
            var viewEls = el.querySelectorAll('span');
            for (var k = 0; k < viewEls.length; k++) {
                var t = viewEls[k].textContent.trim();
                if (t.indexOf('\u6d4f\u89c8') > -1) { viewText = t; break; }
            }

            results.push({
                sku: sku,
                title: title,
                price: price,
                original_price: origPrice,
                shop: shop,
                commit_count: commentCount,
                commit_text: commitText,
                image_url: imgUrl,
                url: link,
                view_text: viewText
            });
        }

        return JSON.stringify(results);
    } catch(e) {
        return JSON.stringify({error: e.message});
    }
})();
"""


class JDSpider:
    def __init__(self):
        from cdp_browser import CDPBrowser, ensure_chrome
        self.ensure_chrome = ensure_chrome
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
                platform    TEXT DEFAULT 'jd',
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
        self.ensure_chrome(9222)
        self.browser = self.CDPBrowser("127.0.0.1", 9222)
        self.browser.block_resources()
        print("[浏览器] 已启动，已屏蔽图片/视频/字体")

    def wait_for_login(self, max_wait=300):
        """检测登录页，等待用户手动登录"""
        url = self.browser.get_url() or ""
        title = self.browser.get_title() or ""

        if "login" in url.lower() or "passport" in url.lower() or "登录" in title:
            print("\n" + "=" * 60)
            print("  ⚠️  检测到登录页面！")
            print("  请在弹出的Chrome浏览器中手动登录京东")
            print("  登录成功后，脚本会自动检测并继续采集")
            print(f"  最多等待 {max_wait} 秒...")
            print("=" * 60 + "\n")

            start = time.time()
            while time.time() - start < max_wait:
                time.sleep(3)
                current_url = self.browser.get_url() or ""
                current_title = self.browser.get_title() or ""

                if "login" not in current_url.lower() and "passport" not in current_url.lower():
                    if "登录" not in current_title:
                        print("\n[登录] ✅ 检测到登录成功！继续采集...\n")
                        time.sleep(2)
                        return True
                    else:
                        elapsed = int(time.time() - start)
                        print(f"  [登录] 等待中... ({elapsed}s) 标题: {current_title}")
                else:
                    elapsed = int(time.time() - start)
                    print(f"  [登录] 等待中... ({elapsed}s)")

            print("\n[登录] ⏰ 等待超时，跳过当前步骤")
            return False
        return True

    def navigate_and_check_login(self, url, wait_sec=4):
        """导航到URL，如果跳转登录页则等待用户登录"""
        self.browser.navigate(url, wait_sec=wait_sec)

        if not self.wait_for_login():
            return False

        # 登录后可能需要重新导航
        current_url = self.browser.get_url() or ""
        if "login" not in current_url.lower() and "passport" not in current_url.lower():
            target_path = url.split("?")[0]
            current_path = current_url.split("?")[0]
            if target_path != current_path:
                self.browser.navigate(url, wait_sec=wait_sec)
                time.sleep(1)

        return True

    def scrape_search_page(self, keyword, page=1):
        """爬取搜索结果页"""
        page_param = 2 * page - 1
        url = f"https://search.jd.com/Search?keyword={keyword}&enc=utf-8&page={page_param}"

        print(f"\n[搜索] 关键词='{keyword}' 第{page}页")

        if not self.navigate_and_check_login(url, wait_sec=5):
            print("  [搜索] 登录失败，跳过")
            return []

        # 等待React渲染
        time.sleep(3)

        # 向下滚动触发懒加载
        for i in range(5):
            self.browser.evaluate(f"window.scrollTo(0, {500 * (i + 1)})")
            time.sleep(0.4)
        time.sleep(1)

        # 检查页面是否有商品
        sku_count = self.browser.evaluate("document.querySelectorAll('[data-sku]').length")
        print(f"  [搜索] 页面SKU数: {sku_count}")

        if not sku_count or sku_count == 0:
            # 可能需要登录或页面未加载
            url_now = self.browser.get_url() or ""
            if "login" in url_now.lower():
                print("  [搜索] 跳转登录页")
                self.wait_for_login()
                # 重新导航
                self.browser.navigate(url, wait_sec=5)
                time.sleep(3)
                sku_count = self.browser.evaluate("document.querySelectorAll('[data-sku]').length")
                print(f"  [搜索] 重新加载后SKU数: {sku_count}")
            if not sku_count:
                # 保存调试HTML
                debug_path = os.path.join(DATA_DIR, f"debug_{keyword}_p{page}.html")
                html = self.browser.get_html() or ""
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(html)
                print(f"  [搜索] 无商品，调试HTML: {debug_path}")
                return []

        # 提取商品
        products_json = self.browser.evaluate(EXTRACT_JS)

        if not products_json:
            print("  [搜索] evaluate返回空")
            debug_path = os.path.join(DATA_DIR, f"debug_{keyword}_p{page}.html")
            html = self.browser.get_html() or ""
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(html)
            return []

        try:
            data = json.loads(products_json)
        except:
            print(f"  [搜索] JSON解析失败: {products_json[:200]}")
            return []

        if isinstance(data, dict) and "error" in data:
            print(f"  [搜索] JS错误: {data['error']}")
            return []

        products = data if isinstance(data, list) else []

        print(f"  [搜索] 提取到 {len(products)} 个商品")
        for p in products[:5]:
            print(f"    - [{p['sku']}] {p['title'][:50]}")
            print(f"      ¥{p['price']} (原价¥{p.get('original_price',0)}) {p.get('shop','')} 评论:{p.get('commit_count',0)}")

        return products

    def fetch_review_summary(self, sku):
        """用JS fetch调评价摘要API"""
        result = self.browser.evaluate(f"""
            (async function() {{
                try {{
                    var resp = await fetch("https://club.jd.com/comment/productCommentSummaries.action?referenceIds={sku}", {{
                        credentials: "include",
                        headers: {{"Accept": "application/json"}}
                    }});
                    var text = await resp.text();
                    if (text.indexOf("\u7cfb\u7edf\u7e41\u5fd9") > -1) {{
                        return JSON.stringify({{error: "busy"}});
                    }}
                    var data = JSON.parse(text);
                    var info = (data.CommentsCount || [{{}}])[0];
                    return JSON.stringify({{
                        comment_count: info.CommentCount || 0,
                        good_count: info.GoodCount || 0,
                        general_count: info.GeneralCount || 0,
                        poor_count: info.PoorCount || 0,
                        good_rate: info.GoodRate || 0,
                        general_rate: info.GeneralRate || 0,
                        poor_rate: info.PoorRate || 0
                    }});
                }} catch(e) {{
                    return JSON.stringify({{error: e.message}});
                }}
            }})();
        """)

        try:
            return json.loads(result) if result else {}
        except:
            return {}

    def fetch_review_list(self, sku, page=0, page_size=10):
        """用JS fetch调评价列表API"""
        result = self.browser.evaluate(f"""
            (async function() {{
                try {{
                    var resp = await fetch("https://club.jd.com/comment/productPageComments.action?productId={sku}&score=0&sortType=5&page={page}&pageSize={page_size}", {{
                        credentials: "include",
                        headers: {{"Accept": "application/json"}}
                    }});
                    var text = await resp.text();
                    if (text.indexOf("\u7cfb\u7edf\u7e41\u5fd9") > -1) {{
                        return JSON.stringify({{error: "busy", comments: []}});
                    }}
                    var data = JSON.parse(text);
                    var comments = (data.comments || []).map(function(c) {{
                        return {{
                            content: c.content || '',
                            score: c.score || 5,
                            nickname: c.nickname || '',
                            date: c.creationTime || c.referenceTime || '',
                            variant: (c.productColor || '') + ' ' + (c.productSize || ''),
                            images: (c.images || []).map(function(i) {{ return i.imgUrl; }}).join(',')
                        }};
                    }});
                    return JSON.stringify({{comments: comments}});
                }} catch(e) {{
                    return JSON.stringify({{error: e.message, comments: []}});
                }}
            }})();
        """)

        try:
            return json.loads(result) if result else {"comments": []}
        except:
            return {"comments": []}

    def save_product(self, product, keyword):
        c = self.db.cursor()
        c.execute("""
            INSERT INTO products (product_id, platform, keyword, title, price, original_price,
                                   shop_name, brand, model, url, image_url, comment_count,
                                   good_count, general_count, poor_count, good_rate,
                                   general_rate, poor_rate, sales_text)
            VALUES (?, 'jd', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(product_id) DO UPDATE SET
                title=excluded.title, price=excluded.price,
                shop_name=excluded.shop_name,
                comment_count=excluded.comment_count,
                updated_at=datetime('now','localtime')
        """, (
            product.get("sku", ""),
            keyword,
            product.get("title", ""),
            product.get("price", 0),
            product.get("original_price", 0),
            product.get("shop", ""),
            product.get("brand", ""),
            product.get("model", ""),
            product.get("url", ""),
            product.get("image_url", ""),
            product.get("comment_count", 0),
            product.get("good_count", 0),
            product.get("general_count", 0),
            product.get("poor_count", 0),
            product.get("good_rate", 0),
            product.get("general_rate", 0),
            product.get("poor_rate", 0),
            product.get("commit_text", "") or product.get("view_text", ""),
        ))
        self.db.commit()

    def save_reviews(self, sku, reviews):
        c = self.db.cursor()
        for r in reviews:
            try:
                c.execute("""
                    INSERT OR IGNORE INTO reviews (product_id, platform, content, score,
                                                    nickname, review_date, variant, images)
                    VALUES (?, 'jd', ?, ?, ?, ?, ?, ?)
                """, (
                    sku,
                    r.get("content", ""),
                    r.get("score", 5),
                    r.get("nickname", ""),
                    r.get("date", ""),
                    r.get("variant", ""),
                    r.get("images", ""),
                ))
            except:
                pass
        self.db.commit()

    def log_search(self, keyword, page, count):
        c = self.db.cursor()
        c.execute("""
            INSERT INTO search_log (keyword, page, platform, result_count)
            VALUES (?, ?, 'jd', ?)
        """, (keyword, page, count))
        self.db.commit()

    def run(self):
        self.setup_db()
        self.start_browser()

        # Step 1: 访问京东首页
        print("\n[Step 1] 访问京东首页...")
        self.browser.navigate("https://www.jd.com/", wait_sec=3)
        if not self.wait_for_login():
            print("[!] 首页要求登录，请先登录再运行")
            return

        total_products = 0
        total_reviews = 0
        all_skus = set()

        # Step 2: 搜索采集
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
                    if p.get("sku") and p["sku"] not in all_skus:
                        all_skus.add(p["sku"])
                        self.save_product(p, keyword)
                        total_products += 1
                    elif p.get("sku"):
                        self.save_product(p, keyword)

                print(f"  [保存] 累计新增商品: {total_products}")

            time.sleep(2)

        # Step 3: 采集评价数据
        print(f"\n{'='*50}")
        print(f"[Step 3] 采集评价数据 (共{len(all_skus)}个商品)")
        print(f"{'='*50}")

        # 在京东域名下用JS fetch调API
        self.browser.navigate("https://www.jd.com/", wait_sec=2)

        for i, sku in enumerate(all_skus):
            print(f"\n  [{i+1}/{len(all_skus)}] SKU: {sku}")

            # 评价摘要
            summary = self.fetch_review_summary(sku)
            if summary and "error" not in summary:
                print(f"    评价: {summary.get('comment_count', 0)}条 | "
                      f"好评率: {summary.get('good_rate', 0)}% | "
                      f"好评: {summary.get('good_count', 0)} 差评: {summary.get('poor_count', 0)}")

                c = self.db.cursor()
                c.execute("""
                    UPDATE products SET
                        comment_count=?, good_count=?, general_count=?, poor_count=?,
                        good_rate=?, general_rate=?, poor_rate=?,
                        updated_at=datetime('now','localtime')
                    WHERE product_id=?
                """, (
                    summary.get("comment_count", 0),
                    summary.get("good_count", 0),
                    summary.get("general_count", 0),
                    summary.get("poor_count", 0),
                    summary.get("good_rate", 0),
                    summary.get("general_rate", 0),
                    summary.get("poor_rate", 0),
                    sku,
                ))
                self.db.commit()
            else:
                err = summary.get("error", "unknown") if summary else "no data"
                print(f"    评价API: {err}")

            # 评价内容（前3页）
            for page in range(3):
                review_data = self.fetch_review_list(sku, page=page, page_size=10)
                comments = review_data.get("comments", [])

                if not comments:
                    break

                self.save_reviews(sku, comments)
                total_reviews += len(comments)
                print(f"    第{page+1}页: {len(comments)}条评价")

                time.sleep(0.5)

            time.sleep(1)

        # 汇总
        print(f"\n{'='*50}")
        print(f"  采集完成！")
        print(f"  总商品数: {total_products}")
        print(f"  总评价数: {total_reviews}")
        print(f"  数据库: {DB_PATH}")
        print(f"{'='*50}")

        self.browser.close()
        self.db.close()


if __name__ == "__main__":
    spider = JDSpider()
    spider.run()
