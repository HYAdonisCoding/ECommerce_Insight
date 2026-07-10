#!/usr/bin/env python3
"""
京东评价采集器 - 从商品页提取评价数据
- 逐个访问商品页，提取评价摘要和评价内容
- 尝试在item.jd.com域名下fetch评价API
- 数据写入SQLite reviews表
"""
import json
import time
import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "ecommerce.db")

# 评价摘要提取JS
REVIEW_SUMMARY_JS = r"""
(function() {
    try {
        var data = {};

        // 评价数 - 多种选择器
        var commentCount = 0;
        var countEls = document.querySelectorAll('a, span, div, em');
        for (var i = 0; i < countEls.length; i++) {
            var t = countEls[i].textContent.trim();
            // "全部评价(123)" 或 "123万+评价"
            if (t.indexOf('\u8bc4\u4ef7') > -1 && t.length < 30) {
                var m = t.match(/(\d+)/);
                if (m) {
                    commentCount = parseInt(m[1]);
                    if (t.indexOf('\u4e07') > -1) commentCount *= 10000;
                    break;
                }
            }
        }
        data.comment_count = commentCount;

        // 好评率
        var goodRate = 0;
        var rateEls = document.querySelectorAll('span, div, em');
        for (var i = 0; i < rateEls.length; i++) {
            var t = rateEls[i].textContent.trim();
            if (t.indexOf('\u597d\u8bc4') > -1 && t.indexOf('%') > -1 && t.length < 30) {
                var m = t.match(/(\d+(?:\.\d+)?)\s*%/);
                if (m) { goodRate = parseFloat(m[1]); break; }
            }
            // 也可能是 "97%" 格式
            if (/^\d{1,2}(\.\d+)?%$/.test(t) && t !== '100%') {
                goodRate = parseFloat(t);
            }
        }
        data.good_rate = goodRate;

        // 从评价区域提取
        var commentSection = document.querySelector('#comment, .comment-list, [class*="comment"], [class*="Comment"], #comment-0');
        if (commentSection) {
            // 好评/中评/差评数量
            var tagEls = commentSection.querySelectorAll('a, span, li, div');
            for (var i = 0; i < tagEls.length; i++) {
                var t = tagEls[i].textContent.trim();
                if (t.indexOf('\u597d\u8bc4') > -1) {
                    var m = t.match(/(\d+)/);
                    if (m) data.good_count = parseInt(m[1]);
                }
                if (t.indexOf('\u4e2d\u8bc4') > -1) {
                    var m = t.match(/(\d+)/);
                    if (m) data.general_count = parseInt(m[1]);
                }
                if (t.indexOf('\u5dee\u8bc4') > -1) {
                    var m = t.match(/(\d+)/);
                    if (m) data.poor_count = parseInt(m[1]);
                }
            }
        }

        // 提取评价标签
        var tags = [];
        var tagEls = document.querySelectorAll('[class*="tag"] span, [class*="Tag"] span, .comment-tag, .tag-item');
        for (var i = 0; i < tagEls.length; i++) {
            var t = tagEls[i].textContent.trim();
            if (t.length > 1 && t.length < 20) tags.push(t);
        }
        data.tags = tags.slice(0, 10);

        // 提取可见评价内容
        var reviews = [];
        var commentItems = document.querySelectorAll('[class*="comment-item"], [class*="CommentItem"], .comment-con, .comment-item');
        for (var i = 0; i < Math.min(10, commentItems.length); i++) {
            var item = commentItems[i];
            var content = '';
            var conEl = item.querySelector('[class*="content"], .comment-con, p, div');
            if (conEl) content = conEl.textContent.trim();

            var score = 5;
            var starEl = item.querySelector('[class*="star"], [class*="Star"]');
            if (starEl) {
                var starClass = starEl.className || '';
                var m = starClass.match(/(\d)/);
                if (m) score = parseInt(m[1]);
            }

            var nickname = '';
            var userEl = item.querySelector('[class*="user"], [class*="User"], [class*="name"]');
            if (userEl) nickname = userEl.textContent.trim();

            var date = '';
            var dateEl = item.querySelector('[class*="date"], [class*="Date"], [class*="time"]');
            if (dateEl) date = dateEl.textContent.trim();

            var variant = '';
            var variantEl = item.querySelector('[class*="color"], [class*="version"], [class*="sku"]');
            if (variantEl) variant = variantEl.textContent.trim();

            if (content && content.length > 5) {
                reviews.push({
                    content: content.substring(0, 500),
                    score: score,
                    nickname: nickname,
                    date: date,
                    variant: variant
                });
            }
        }
        data.reviews = reviews;

        return JSON.stringify(data);
    } catch(e) {
        return JSON.stringify({error: e.message});
    }
})();
"""


class JDReviewCrawler:
    def __init__(self):
        from cdp_browser import CDPBrowser, ensure_chrome
        self.ensure_chrome = ensure_chrome
        self.CDPBrowser = CDPBrowser
        self.browser = None
        self.db = sqlite3.connect(DB_PATH)

    def start(self):
        self.ensure_chrome(9222)
        self.browser = self.CDPBrowser("127.0.0.1", 9222)
        self.browser.block_resources()
        print("[评价采集] 浏览器已启动")

    def wait_for_login(self, max_wait=300):
        url = self.browser.get_url() or ""
        title = self.browser.get_title() or ""
        if "login" in url.lower() or "passport" in url.lower() or "登录" in title:
            print("\n" + "=" * 60)
            print("  ⚠️  检测到登录页面！请在Chrome中手动登录京东")
            print("  登录后脚本会自动继续")
            print("=" * 60 + "\n")
            start = time.time()
            while time.time() - start < max_wait:
                time.sleep(3)
                cur_url = self.browser.get_url() or ""
                cur_title = self.browser.get_title() or ""
                if "login" not in cur_url.lower() and "passport" not in cur_url.lower() and "登录" not in cur_title:
                    print("[登录] ✅ 登录成功！继续...\n")
                    time.sleep(2)
                    return True
                print(f"  [登录] 等待中... ({int(time.time()-start)}s)")
            return False
        return True

    def crawl_product_reviews(self, sku):
        """访问商品页，提取评价数据"""
        url = f"https://item.jd.com/{sku}.html"
        self.browser.navigate(url, wait_sec=4)

        # 检查登录
        if not self.wait_for_login():
            return None

        # 等待页面渲染
        time.sleep(2)

        # 滚动到评价区域
        self.browser.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.6)")
        time.sleep(1)
        self.browser.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.8)")
        time.sleep(1)

        # 提取评价摘要
        result = self.browser.evaluate(REVIEW_SUMMARY_JS)
        if not result:
            return None

        try:
            data = json.loads(result)
        except:
            return None

        if "error" in data:
            return None

        # 尝试在item.jd.com域名下fetch评价API
        api_data = self.fetch_review_api(sku)
        if api_data:
            # API数据优先
            for key in ["comment_count", "good_count", "general_count", "poor_count", "good_rate"]:
                if api_data.get(key):
                    data[key] = api_data[key]
            if api_data.get("reviews"):
                data["reviews"] = api_data["reviews"]

        return data

    def fetch_review_api(self, sku):
        """在item.jd.com域名下fetch评价API"""
        # 评价摘要API
        summary_result = self.browser.evaluate(f"""
            (async function() {{
                try {{
                    var resp = await fetch("https://club.jd.com/comment/productCommentSummaries.action?referenceIds={sku}", {{
                        credentials: "include",
                        headers: {{"Accept": "application/json"}}
                    }});
                    var text = await resp.text();
                    if (text.indexOf("\u7cfb\u7edf\u7e41\u5fd9") > -1) return null;
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
                    return null;
                }}
            }})();
        """)

        summary = {}
        if summary_result:
            try:
                summary = json.loads(summary_result)
            except:
                pass

        # 评价列表API
        list_result = self.browser.evaluate(f"""
            (async function() {{
                try {{
                    var resp = await fetch("https://club.jd.com/comment/productPageComments.action?productId={sku}&score=0&sortType=5&page=0&pageSize=10", {{
                        credentials: "include",
                        headers: {{"Accept": "application/json"}}
                    }});
                    var text = await resp.text();
                    if (text.indexOf("\u7cfb\u7edf\u7e41\u5fd9") > -1) return JSON.stringify({{reviews: []}});
                    var data = JSON.parse(text);
                    var comments = (data.comments || []).map(function(c) {{
                        return {{
                            content: (c.content || '').substring(0, 500),
                            score: c.score || 5,
                            nickname: c.nickname || '',
                            date: c.creationTime || c.referenceTime || '',
                            variant: (c.productColor || '') + ' ' + (c.productSize || '')
                        }};
                    }});
                    return JSON.stringify({{reviews: comments}});
                }} catch(e) {{
                    return JSON.stringify({{reviews: []}});
                }}
            }})();
        """)

        reviews = []
        if list_result:
            try:
                list_data = json.loads(list_result)
                reviews = list_data.get("reviews", [])
            except:
                pass

        if summary or reviews:
            summary["reviews"] = reviews
            return summary
        return None

    def save_review_data(self, sku, data):
        """保存评价数据到数据库"""
        c = self.db.cursor()

        # 更新商品表的评价摘要
        c.execute("""
            UPDATE products SET
                comment_count=?,
                good_count=?,
                general_count=?,
                poor_count=?,
                good_rate=?,
                updated_at=datetime('now','localtime')
            WHERE product_id=?
        """, (
            data.get("comment_count", 0),
            data.get("good_count", 0),
            data.get("general_count", 0),
            data.get("poor_count", 0),
            data.get("good_rate", 0),
            sku,
        ))

        # 保存评价内容
        for r in data.get("reviews", []):
            try:
                c.execute("""
                    INSERT OR IGNORE INTO reviews (product_id, platform, content, score,
                                                    nickname, review_date, variant)
                    VALUES (?, 'jd', ?, ?, ?, ?, ?)
                """, (
                    sku,
                    r.get("content", ""),
                    r.get("score", 5),
                    r.get("nickname", ""),
                    r.get("date", ""),
                    r.get("variant", ""),
                ))
            except:
                pass

        self.db.commit()

    def run(self):
        self.start()

        # 获取所有商品ID
        c = self.db.cursor()
        c.execute("SELECT product_id FROM products ORDER BY id")
        skus = [r[0] for r in c.fetchall()]
        print(f"[评价采集] 共 {len(skus)} 个商品待采集")

        # 先访问京东首页
        self.browser.navigate("https://www.jd.com/", wait_sec=2)
        self.wait_for_login()

        success = 0
        fail = 0
        total_reviews = 0

        for i, sku in enumerate(skus):
            print(f"\n  [{i+1}/{len(skus)}] SKU: {sku}")

            data = self.crawl_product_reviews(sku)

            if data and (data.get("comment_count", 0) > 0 or len(data.get("reviews", [])) > 0):
                self.save_review_data(sku, data)
                success += 1
                rv_count = len(data.get("reviews", []))
                total_reviews += rv_count
                print(f"    ✅ 评价:{data.get('comment_count', 0)}条 "
                      f"好评率:{data.get('good_rate', 0)}% "
                      f"评价内容:{rv_count}条")
            else:
                fail += 1
                print(f"    ❌ 无评价数据")

            time.sleep(1)

        print(f"\n{'='*50}")
        print(f"  评价采集完成！")
        print(f"  成功: {success} 失败: {fail}")
        print(f"  总评价内容: {total_reviews}条")
        print(f"{'='*50}")

        self.browser.close()
        self.db.close()


if __name__ == "__main__":
    crawler = JDReviewCrawler()
    crawler.run()
