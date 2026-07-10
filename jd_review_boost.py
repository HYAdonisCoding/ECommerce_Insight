#!/usr/bin/env python3
"""
京东评价数据补全 - 多策略采集
1. 从已有的sales_text字段解析评价数和好评率
2. 用WebFetch采集商品页评价摘要
3. 用CDP浏览器采集评价文本内容
"""
import sqlite3
import re
import os
import json
import time
import sys

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ecommerce.db")


def parse_sales_text():
    """从sales_text解析评价数和好评率"""
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()

    c.execute("SELECT product_id, sales_text FROM products WHERE sales_text IS NOT NULL AND sales_text != ''")
    rows = c.fetchall()

    updated = 0
    for pid, text in rows:
        comment_count = 0
        good_rate = 0

        # 匹配 "56条评价" 或 "66条评价"
        m = re.search(r'(\d+)\s*条评价', text)
        if m:
            comment_count = int(m.group(1))

        # 匹配 "100%好评" 或 "98%好评"
        m = re.search(r'(\d+(?:\.\d+)?)\s*%\s*好评', text)
        if m:
            good_rate = float(m.group(1))

        if comment_count > 0 or good_rate > 0:
            c.execute("UPDATE products SET comment_count=COALESCE(NULLIF(comment_count,0),?), good_rate=COALESCE(NULLIF(good_rate,0),?) WHERE product_id=?",
                      (comment_count, good_rate, pid))
            updated += 1

    db.commit()
    db.close()
    print(f"[sales_text解析] 更新了 {updated} 个商品的评价数据")
    return updated


def fetch_reviews_via_webfetch():
    """用WebFetch获取商品页面评价信息"""
    # This will be called from the main agent context using WebFetch tool
    pass


def collect_reviews_via_cdp():
    """用CDP浏览器逐个访问商品页面，提取评价摘要和评价文本"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    db = sqlite3.connect(DB_PATH)
    c = db.cursor()

    # 获取需要采集的商品（没有评价数据的）
    c.execute("SELECT product_id, title FROM products WHERE comment_count = 0 ORDER BY id LIMIT 60")
    pending = c.fetchall()

    if not pending:
        print("[CDP采集] 所有商品已有评价数据")
        db.close()
        return

    print(f"[CDP采集] 待采集: {len(pending)} 个商品")

    from cdp_browser import CDPBrowser, ensure_chrome

    ensure_chrome(9222)
    browser = CDPBrowser("127.0.0.1", 9222)
    browser.block_resources()

    # 先访问京东首页
    browser.navigate("https://www.jd.com/", wait_sec=3)

    # 检查是否需要登录
    cur_url = browser.get_url() or ""
    if "login" in cur_url.lower() or "passport" in cur_url.lower():
        print("[CDP采集] 需要登录！请在Chrome中手动登录京东...")
        for i in range(60):
            time.sleep(3)
            cur_url = browser.get_url() or ""
            if "login" not in cur_url.lower() and "passport" not in cur_url.lower():
                print("[CDP采集] 登录成功！")
                break
            if i % 5 == 0:
                print(f"  等待登录... ({i*3}s)")

    # 评价摘要提取JS - 从商品页面DOM提取
    SUMMARY_JS = r"""
    (function() {
        try {
            var result = {comment_count: 0, good_rate: 0, good_count: 0, poor_count: 0, review_texts: []};

            // 方法1: 从评价区域提取评价数
            var cmtEls = document.querySelectorAll('a, span, div, em, li');
            for (var i = 0; i < cmtEls.length; i++) {
                var t = cmtEls[i].textContent.trim();
                if (t.indexOf('\u8bc4\u4ef7') > -1 && t.length < 30) {
                    var m = t.match(/(\d+)/);
                    if (m) {
                        result.comment_count = parseInt(m[1]);
                        if (t.indexOf('\u4e07') > -1) result.comment_count *= 10000;
                        break;
                    }
                }
            }

            // 方法2: 从好评率提取
            var rateEls = document.querySelectorAll('span, div, em');
            for (var i = 0; i < rateEls.length; i++) {
                var t = rateEls[i].textContent.trim();
                if (t.indexOf('\u597d\u8bc4') > -1 && t.indexOf('%') > -1 && t.length < 30) {
                    var m = t.match(/(\d+(?:\.\d+)?)\s*%/);
                    if (m) { result.good_rate = parseFloat(m[1]); break; }
                }
            }

            // 方法3: 提取评价文本内容
            var reviewEls = document.querySelectorAll('[class*="comment-item"], [class*="Comment"], [class*="review"], div.comment-item, dd.comment');
            for (var i = 0; i < reviewEls.length && i < 10; i++) {
                var el = reviewEls[i];
                var contentEl = el.querySelector('[class*="content"], p, [class*="Content"]');
                var content = contentEl ? contentEl.textContent.trim() : el.textContent.trim();
                if (content && content.length > 5 && content.length < 500) {
                    var nickEl = el.querySelector('[class*="user"], [class*="User"], [class*="name"]');
                    var nick = nickEl ? nickEl.textContent.trim() : '';
                    result.review_texts.push({content: content.substring(0, 300), nickname: nick});
                }
            }

            // 方法4: 从搜索结果页样式的评价数提取
            if (result.comment_count === 0) {
                var allText = document.body.innerText;
                var m = allText.match(/(\d+)\s*\u4e07?\s*\u6761\u8bc4\u4ef7/);
                if (m) {
                    result.comment_count = parseInt(m[1]);
                    if (m[0].indexOf('\u4e07') > -1) result.comment_count *= 10000;
                }
            }

            return JSON.stringify(result);
        } catch(e) { return JSON.stringify({error: e.message}); }
    })();
    """

    # 评价文本提取JS - 滚动到评价区域后提取
    REVIEW_TEXT_JS = r"""
    (function() {
        try {
            var reviews = [];

            // 京东新版评价区域选择器
            var selectors = [
                '.comment-item',
                '[class*="CommentItem"]',
                '[class*="comment-content"]',
                '[class*="Comment_"]',
                'div[class*="comment"]',
                '.comments-list > div',
                '[data-testid*="comment"]'
            ];

            for (var s = 0; s < selectors.length; s++) {
                var els = document.querySelectorAll(selectors[s]);
                if (els.length > 0) {
                    for (var i = 0; i < els.length && i < 15; i++) {
                        var el = els[i];
                        var content = '';
                        var contentEls = el.querySelectorAll('p, span, div');
                        for (var j = 0; j < contentEls.length; j++) {
                            var t = contentEls[j].textContent.trim();
                            if (t.length > 10 && t.length < 500 && t.indexOf('\u8bc4\u4ef7') === -1) {
                                content = t;
                                break;
                            }
                        }
                        if (!content) content = el.textContent.trim().substring(0, 300);

                        var nick = '';
                        var nickEls = el.querySelectorAll('[class*="user"], [class*="User"], [class*="name"], [class*="Name"]');
                        for (var j = 0; j < nickEls.length; j++) {
                            var t = nickEls[j].textContent.trim();
                            if (t.length > 0 && t.length < 20) { nick = t; break; }
                        }

                        if (content && content.length > 5) {
                            reviews.push({content: content, nickname: nick});
                        }
                    }
                    if (reviews.length > 0) break;
                }
            }

            return JSON.stringify(reviews);
        } catch(e) { return JSON.stringify([]); }
    })();
    """

    success = 0
    fail = 0
    reviews_collected = 0

    for i, (sku, title) in enumerate(pending):
        try:
            url = f"https://item.jd.com/{sku}.html"
            browser.navigate(url, wait_sec=3)

            cur_url = browser.get_url() or ""
            if "login" in cur_url.lower() or "passport" in cur_url.lower():
                print(f"  [{i+1}/{len(pending)}] {sku}: 登录页跳过")
                fail += 1
                continue

            # 滚动到页面中部和底部，触发评价区域加载
            browser.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5)")
            time.sleep(0.5)
            browser.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.8)")
            time.sleep(0.5)

            result = browser.evaluate(SUMMARY_JS)
            if result:
                try:
                    data = json.loads(result)
                    cc = data.get("comment_count", 0)
                    gr = data.get("good_rate", 0)
                    gc = data.get("good_count", 0)
                    pc = data.get("poor_count", 0)
                    review_texts = data.get("review_texts", [])

                    if cc > 0 or gr > 0:
                        c.execute("""UPDATE products SET
                            comment_count=COALESCE(NULLIF(comment_count,0),?),
                            good_rate=COALESCE(NULLIF(good_rate,0),?),
                            good_count=?,
                            poor_count=?,
                            updated_at=datetime('now','localtime')
                            WHERE product_id=?""",
                            (cc, gr, gc, pc, sku))
                        db.commit()
                        success += 1

                        # 保存评价文本
                        for rt in review_texts:
                            try:
                                c.execute("""INSERT OR IGNORE INTO reviews
                                    (product_id, platform, content, nickname)
                                    VALUES (?, 'jd', ?, ?)""",
                                    (sku, rt.get("content", ""), rt.get("nickname", "")))
                                reviews_collected += 1
                            except:
                                pass
                        db.commit()

                        if (i+1) % 5 == 0 or cc > 50:
                            n_reviews = len(review_texts)
                            print(f"  [{i+1}/{len(pending)}] {sku}: 评价{cc}条 好评率{gr}% 文本{n_reviews}条")
                    else:
                        fail += 1
                except Exception as e:
                    fail += 1
            else:
                fail += 1

            # 尝试点击评价tab，获取更多评价文本
            browser.evaluate("""
                (function() {
                    var tabs = document.querySelectorAll('a, li, span, div');
                    for (var i = 0; i < tabs.length; i++) {
                        var t = tabs[i].textContent.trim();
                        if (t === '\u8bc4\u4ef7' || t === '\u53e3\u7891' || t.indexOf('\u8bc4\u4ef7(') > -1) {
                            tabs[i].click();
                            return true;
                        }
                    }
                    return false;
                })();
            """)
            time.sleep(1)

            review_result = browser.evaluate(REVIEW_TEXT_JS)
            if review_result:
                try:
                    texts = json.loads(review_result)
                    for rt in texts:
                        try:
                            c.execute("""INSERT OR IGNORE INTO reviews
                                (product_id, platform, content, nickname)
                                VALUES (?, 'jd', ?, ?)""",
                                (sku, rt.get("content", ""), rt.get("nickname", "")))
                            reviews_collected += 1
                        except:
                            pass
                    db.commit()
                except:
                    pass

        except Exception as e:
            print(f"  [{i+1}/{len(pending)}] {sku}: 错误 {e}")
            fail += 1

        time.sleep(0.3)

    browser.close()
    db.close()
    print(f"\n[CDP采集] 完成! 成功: {success} 失败: {fail} 评价文本: {reviews_collected}条")


if __name__ == "__main__":
    print("=" * 50)
    print("京东评价数据补全")
    print("=" * 50)

    # Step 1: 从sales_text解析
    parse_sales_text()

    # Step 2: CDP浏览器采集
    collect_reviews_via_cdp()
