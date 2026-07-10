#!/usr/bin/env python3
"""
京东电火灶爬虫 V4 - CDP直连 + 多策略采集
策略:
  1. 分类页获取商品ID列表(无需登录)
  2. 商品详情页提取 标题/价格/品牌/型号/店铺
  3. JS fetch调评价API(带页面cookie, 绕过系统繁忙)
  4. 评价页HTML备用解析
  5. 全部写入SQLite
"""
import sqlite3
import json
import re
import time
import os
import random
from cdp_browser import CDPBrowser, ensure_chrome

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ecommerce.db")

# 搜索关键词 - 用于商品标题过滤
FILTER_KEYWORDS = ["电火灶", "电焰灶", "电燃灶", "电燃炉", "电焰炉", "明火电"]
# 分类页URL(电燃气灶分类, 包含电火灶商品)
CATEGORY_URLS = [
    "https://www.jd.com/chanpin/2708369.html",
    "https://www.jd.com/chanpin/2708369.html?page=2",
    "https://www.jd.com/chanpin/2708369.html?page=3",
]
# 已知电火灶商品ID
KNOWN_SKUS = [
    "10209470415667", "10204701688923", "10133878654696",
    "10209453821199", "10214948855231", "10184348436524",
    "10216473779863",
]
MAX_COMMENT_PAGES = 5


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ==================== 策略1: 分类页获取商品ID ====================

CATEGORY_JS = """
(function() {
    var products = [];
    var links = document.querySelectorAll("a[href*='item.jd.com']");
    var seen = {};
    links.forEach(function(a) {
        var m = (a.href || '').match(/item\\.jd\\.com\\/(\\d+)/);
        if (!m) return;
        var sku = m[1];
        if (seen[sku]) return;
        seen[sku] = true;

        // 获取标题 - 从链接文本或父容器
        var title = a.textContent.trim();
        if (!title || title.length < 5) {
            var parent = a.closest('li, div[class*="item"], div[class*="card"], div[class*="product"]');
            if (parent) {
                var t = parent.querySelector('.p-name em, .p-name a, [class*="title"], [class*="Title"]');
                if (t) title = t.textContent.trim();
            }
        }

        // 获取价格
        var price = 0;
        var parent = a.closest('li, div[class*="item"], div[class*="card"], div[class*="product"]');
        if (parent) {
            var pe = parent.querySelector('.p-price i, .p-price strong i, .p-price, [class*="price"]');
            if (pe) {
                var pm = (pe.textContent || '').match(/[\\d.]+/);
                if (pm) price = parseFloat(pm[0]);
            }
        }

        // 获取店铺
        var shop = '';
        if (parent) {
            var se = parent.querySelector('.p-shop a, .p-shop, [class*="shop"], [class*="Shop"]');
            if (se) shop = se.textContent.trim();
        }

        // 获取评价数
        var commentCount = 0;
        if (parent) {
            var ce = parent.querySelector('.p-commit a, .p-commit, [class*="comment"], [class*="Comment"]');
            if (ce) {
                var ct = ce.textContent || '';
                var cm = ct.match(/([\\d.]+)\\s*万?/);
                if (cm) {
                    commentCount = ct.includes('万') ? parseInt(parseFloat(cm[1]) * 10000) : parseInt(cm[1]);
                }
            }
        }

        if (title || price > 0) {
            products.push({
                sku: sku, title: title, price: price,
                shop: shop, commentCount: commentCount,
                url: 'https://item.jd.com/' + sku + '.html'
            });
        }
    });
    return JSON.stringify(products);
})();
"""


def fetch_products_from_category(browser):
    """从分类页获取商品列表"""
    all_products = []
    for url in CATEGORY_URLS:
        print(f"  分类页: {url}")
        browser.navigate(url, wait_sec=2)
        browser.scroll_down()
        time.sleep(0.5)
        browser.scroll_up()

        result = browser.evaluate(CATEGORY_JS)
        if result:
            try:
                products = json.loads(result)
                print(f"    提取到 {len(products)} 个商品")
                all_products.extend(products)
            except json.JSONDecodeError:
                print(f"    JSON解析失败")

        time.sleep(1)

    # 去重
    seen = set()
    unique = []
    for p in all_products:
        if p["sku"] not in seen:
            seen.add(p["sku"])
            unique.append(p)

    return unique


def filter_electric_stove(products):
    """过滤电火灶商品"""
    filtered = []
    for p in products:
        title = p.get("title", "")
        if any(kw in title for kw in FILTER_KEYWORDS):
            filtered.append(p)
    return filtered


# ==================== 策略2: 商品详情页 ====================

DETAIL_JS = """
(async function() {
    var data = {};

    // 标题
    var titleEl = document.querySelector('.sku-name, #name, .itemInfo-wrap .sku-name');
    if (titleEl) data.title = titleEl.textContent.trim();
    if (!data.title) {
        var t = document.querySelector('title');
        if (t) data.title = t.textContent.replace(/-京东.*$/, '').replace(/\\(.*?\\)/g, '').trim();
    }

    // 价格 - 多种选择器
    var priceSelectors = ['.summary-price .price', '.p-price .price', '.price.J-p-' + (window.skuId||'') + ' .price', '[class*="summary"] [class*="price"]', '#jd-price'];
    for (var sel of priceSelectors) {
        var el = document.querySelector(sel);
        if (el) {
            var m = (el.textContent || '').match(/[\\d.]+/);
            if (m && parseFloat(m[0]) > 0) { data.price = parseFloat(m[0]); break; }
        }
    }

    // 原价
    var origEl = document.querySelector('.origin-price .price, .p-price del, [class*="origin"] del, del[class*="price"]');
    if (origEl) {
        var m2 = (origEl.textContent || '').match(/[\\d.]+/);
        if (m2) data.originalPrice = parseFloat(m2[0]);
    }

    // 品牌 - 从面包屑
    var crumbEls = document.querySelectorAll('#crumb-wrap .ellipsis a, .breadcrumb a, [class*="crumb"] a');
    for (var c of crumbEls) {
        var t = c.textContent.trim();
        if (t && t.length > 0 && t.length < 20 && t !== '首页' && !/查看更多/.test(t)) {
            data.brand = t;
            break;
        }
    }

    // 店铺
    var shopEls = document.querySelectorAll('.J-hove-wrap .item a, .popstore-name a, .shop-name a, [class*="shop"] a, [class*="Store"] a, #popbox a, .seller a');
    for (var s of shopEls) {
        var t = s.textContent.trim();
        if (t && t.length > 0 && t.length < 30 && !/进店|收藏|关注|客服/.test(t)) {
            data.shop = t;
            break;
        }
    }

    // 型号和品牌 - 从参数列表
    var paramSelectors = '.parameter2 li, .Ptable-item li, [class*="param"] li, [class*="Param"] li, .detail-attr li, .Ptable .Ptable-item li';
    var params = document.querySelectorAll(paramSelectors);
    params.forEach(function(p) {
        var text = (p.textContent || '').trim();
        if (/型号|商品名称|产品型号/.test(text) && !data.model) {
            data.model = text.replace(/.*(?:型号|商品名称|产品型号)[：:]?\\s*/, '').trim();
        }
        if (/品牌/.test(text) && !data.brand) {
            data.brand = text.replace(/.*品牌[：:]?\\s*/, '').trim();
        }
    });

    // 评价统计 - 从script内嵌数据
    var scripts = document.querySelectorAll('script');
    for (var s of scripts) {
        var t = s.textContent || '';
        if (t.indexOf('commentCount') > -1 || t.indexOf('goodRate') > -1) {
            var cm = t.match(/commentCount['"]?\\s*[:=]\\s*['"]?(\\d+)/);
            if (cm) data.commentCount = parseInt(cm[1]);
            var gr = t.match(/goodRate['"]?\\s*[:=]\\s*['"]?([\\d.]+)/);
            if (gr) data.goodRate = parseFloat(gr[1]);
        }
        // 从 venderId 提取
        if (t.indexOf('venderId') > -1 && !data.venderId) {
            var vm = t.match(/venderId['"]?\\s*[:=]\\s*['"]?(\\d+)/);
            if (vm) data.venderId = vm[1];
        }
    }

    return JSON.stringify(data);
})();
"""


def fetch_product_detail(browser, sku):
    """从商品详情页获取完整信息"""
    url = f"https://item.jd.com/{sku}.html"
    browser.navigate(url, wait_sec=1.5)
    browser.scroll_down()
    time.sleep(0.3)

    result = browser.evaluate(DETAIL_JS)
    if result:
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            pass
    return {}


# ==================== 策略3: JS fetch调评价API ====================

COMMENT_SUMMARY_JS = """
(async function() {
    try {
        var resp = await fetch('https://club.jd.com/comment/productCommentSummaries.action?referenceIds=' + '%s', {
            credentials: 'include',
            headers: {'Accept': 'application/json'}
        });
        var text = await resp.text();
        if (text.indexOf('系统繁忙') > -1 || text.indexOf('错误') > -1) return JSON.stringify({error: 'busy'});
        var data = JSON.parse(text);
        var info = (data.CommentsCount || [{}])[0];
        return JSON.stringify({
            reviewCount: info.CommentCount || 0,
            goodCount: info.GoodCount || 0,
            neutralCount: info.GeneralCount || 0,
            poorCount: info.PoorCount || 0,
            goodRate: info.GoodRate || 0,
            neutralRate: info.GeneralRate || 0,
            poorRate: info.PoorRate || 0,
            showCount: info.ShowCount || 0,
            videoCount: info.VideoCount || 0,
            appendCount: info.AppendCount || 0
        });
    } catch(e) {
        return JSON.stringify({error: e.message});
    }
})();
"""


COMMENT_LIST_JS = """
(async function() {
    try {
        var page = %d;
        var resp = await fetch('https://club.jd.com/comment/productPageComments.action?productId=' + '%s' + '&score=0&sortType=5&page=' + page + '&pageSize=10', {
            credentials: 'include',
            headers: {'Accept': 'application/json'}
        });
        var text = await resp.text();
        if (text.indexOf('系统繁忙') > -1) return JSON.stringify({error: 'busy', comments: []});
        var data = JSON.parse(text);
        var comments = (data.comments || []).map(function(c) {
            return {
                id: String(c.id || ''),
                score: c.score || 5,
                content: c.content || '',
                nickname: c.nickname || '',
                date: c.creationTime || '',
                variant: ((c.productColor || '') + ' ' + (c.productSize || '')).trim(),
                images: c.images ? c.images.length : 0,
                videos: c.videos ? c.videos.length : 0,
                usefulVoteCount: c.usefulVoteCount || 0
            };
        });
        return JSON.stringify({comments: comments});
    } catch(e) {
        return JSON.stringify({error: e.message, comments: []});
    }
})();
"""


def fetch_comment_summary(browser, sku):
    """用JS fetch获取评价摘要(带页面cookie)"""
    js = COMMENT_SUMMARY_JS % sku
    result = browser.evaluate(js)
    if result:
        try:
            data = json.loads(result)
            if "error" not in data:
                return data
        except json.JSONDecodeError:
            pass
    return None


def fetch_comment_list(browser, sku, max_pages=5):
    """用JS fetch获取评价列表"""
    all_comments = []
    for p in range(max_pages):
        js = COMMENT_LIST_JS % (p, sku)
        result = browser.evaluate(js)
        if result:
            try:
                data = json.loads(result)
                comments = data.get("comments", [])
                if not comments:
                    break
                all_comments.extend(comments)
                print(f"      评价API第{p+1}页: {len(comments)}条")
            except json.JSONDecodeError:
                break
        else:
            break
        time.sleep(random.uniform(0.3, 0.6))
    return all_comments


# ==================== 策略4: 评价页HTML解析(备用) ====================

REVIEW_PAGE_JS = """
(function() {
    var result = {stats: {}, reviews: []};

    // 评价数量统计
    var filterEls = document.querySelectorAll('.filter li, [class*="filter"] li, .rate-list .filter a');
    filterEls.forEach(function(el) {
        var t = el.textContent.trim();
        var m = t.match(/(\\d+)\\s*万?/);
        if (m) {
            var n = t.includes('万') ? parseInt(parseFloat(m[1]) * 10000) : parseInt(m[1]);
            if (/好/.test(t)) result.stats.goodCount = n;
            else if (/中/.test(t)) result.stats.neutralCount = n;
            else if (/差/.test(t)) result.stats.poorCount = n;
            else if (/全部|所有/.test(t)) result.stats.totalCount = n;
        }
        var pm = t.match(/([\\d.]+)%/);
        if (pm) {
            if (/好/.test(t)) result.stats.goodRate = parseFloat(pm[1]);
            else if (/中/.test(t)) result.stats.neutralRate = parseFloat(pm[1]);
            else if (/差/.test(t)) result.stats.poorRate = parseFloat(pm[1]);
        }
    });

    // 评价列表
    var reviewEls = document.querySelectorAll('.comment-item, [class*="CommentItem"], [class*="comment-item"]');
    reviewEls.forEach(function(el) {
        try {
            var review = {};
            var starEl = el.querySelector('[class*="star"], .star');
            if (starEl) {
                var sc = starEl.className || '';
                var sm = sc.match(/star(\\d)/) || sc.match(/(\\d)星/);
                if (sm) review.score = parseInt(sm[1]);
            }
            var contentEl = el.querySelector('.comment-content, [class*="content"], p');
            if (contentEl) review.content = contentEl.textContent.trim();
            var authorEl = el.querySelector('.user-info, [class*="user"], [class*="User"]');
            if (authorEl) review.nickname = authorEl.textContent.trim();
            var dateEl = el.querySelector('.comment-date, [class*="date"], [class*="Date"]');
            if (dateEl) review.date = dateEl.textContent.trim();
            var imgEls = el.querySelectorAll('img');
            review.images = imgEls.length;
            if (review.content || review.score) {
                review.id = 'rp_' + Math.random().toString(36).substr(2, 9);
                result.reviews.push(review);
            }
        } catch(e) {}
    });

    return JSON.stringify(result);
})();
"""


def fetch_reviews_from_review_page(browser, sku, max_pages=3):
    """从评价HTML页获取评价(备用方案)"""
    all_reviews = []
    stats = {}

    for p in range(1, max_pages + 1):
        url = f"https://club.jd.com/review/{sku}-3-{p}.html"
        browser.navigate(url, wait_sec=1)
        result = browser.evaluate(REVIEW_PAGE_JS)
        if result:
            try:
                data = json.loads(result)
                if p == 1:
                    stats = data.get("stats", {})
                reviews = data.get("reviews", [])
                if not reviews:
                    break
                all_reviews.extend(reviews)
                print(f"      评价页{p}: {len(reviews)}条")
            except json.JSONDecodeError:
                break
        else:
            break
        time.sleep(random.uniform(0.3, 0.5))

    return stats, all_reviews


# ==================== 数据库操作 ====================

def save_product(sku, search_data, detail, platform="jd"):
    """保存商品到数据库"""
    conn = get_db()
    s = search_data or {}
    d = detail or {}

    conn.execute("""
        INSERT OR REPLACE INTO products
        (platform, product_id, title, price, original_price, shop_name, brand,
         model, url, review_count, image_url, search_keyword)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        platform, sku,
        d.get("title", "") or s.get("title", ""),
        d.get("price", 0) or s.get("price", 0),
        d.get("originalPrice"),
        d.get("shop", "") or s.get("shop", ""),
        d.get("brand", ""),
        d.get("model", ""),
        s.get("url", f"https://item.jd.com/{sku}.html"),
        s.get("commentCount", 0) or d.get("commentCount", 0),
        s.get("img", ""),
        s.get("search_keyword", "chanpin"),
    ))
    conn.commit()
    conn.close()


def update_review_stats(sku, stats):
    """更新评价统计"""
    if not stats:
        return
    conn = get_db()
    fields = []
    values = []
    mapping = {
        "review_count": "reviewCount", "good_count": "goodCount",
        "neutral_count": "neutralCount", "poor_count": "poorCount",
        "good_rate": "goodRate", "neutral_rate": "neutralRate",
        "poor_rate": "poorRate",
    }
    for db_f, stats_k in mapping.items():
        if stats_k in stats and stats[stats_k] is not None:
            fields.append(f"{db_f} = ?")
            values.append(stats[stats_k])
    if fields:
        values.append(sku)
        conn.execute(f"UPDATE products SET {', '.join(fields)} WHERE platform='jd' AND product_id=?", values)
        conn.commit()
    conn.close()


def save_reviews(sku, comments, platform="jd"):
    """保存评价"""
    conn = get_db()
    for c in comments:
        score = c.get("score", 5)
        sentiment = "positive" if score >= 4 else ("negative" if score <= 2 else "neutral")
        conn.execute("""
            INSERT OR IGNORE INTO reviews
            (platform, product_id, review_id, rating, content, author, date,
             variant, has_image, has_video, useful_count, sentiment)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            platform, sku, c.get("id", f"r_{random.randint(1,9999999)}"),
            score, c.get("content", ""), c.get("nickname", ""),
            c.get("date", ""), c.get("variant", ""),
            1 if c.get("images", 0) > 0 else 0,
            1 if c.get("videos", 0) > 0 else 0,
            c.get("usefulVoteCount", 0), sentiment,
        ))
    conn.commit()
    conn.close()


# ==================== 主程序 ====================

def main():
    print("=" * 60)
    print("京东电火灶爬虫 V4 (CDP直连 + JS fetch)")
    print("=" * 60)

    # 启动浏览器
    print("\n[1] 启动Chrome...")
    ensure_chrome(9222)
    browser = CDPBrowser("127.0.0.1", 9222)
    browser.block_resources()

    # 访问京东首页获取cookie
    print("[2] 访问京东首页...")
    browser.navigate("https://www.jd.com/", wait_sec=2)
    print(f"  标题: {browser.get_title()}")

    # 策略1: 从分类页获取商品
    print("\n[3] 从分类页获取商品...")
    category_products = fetch_products_from_category(browser)
    print(f"  分类页商品总数: {len(category_products)}")

    # 合并已知SKU
    all_skus = set()
    products_map = {}

    for p in category_products:
        all_skus.add(p["sku"])
        products_map[p["sku"]] = p

    for sku in KNOWN_SKUS:
        if sku not in products_map:
            products_map[sku] = {"sku": sku, "title": "", "url": f"https://item.jd.com/{sku}.html"}
            all_skus.add(sku)

    # 过滤电火灶商品
    electric_products = filter_electric_stove(list(products_map.values()))
    print(f"  电火灶商品: {len(electric_products)}")
    for p in electric_products:
        print(f"    - {p['sku']}: {p.get('title','')[:50]}")

    # 也加入已知SKU(即使标题为空, 后面从详情页获取)
    target_skus = set(p["sku"] for p in electric_products)
    target_skus.update(KNOWN_SKUS)

    print(f"\n  目标商品总数: {len(target_skus)}")

    # 策略2+3+4: 逐个采集详情和评价
    print(f"\n[4] 采集商品详情和评价...")
    total_reviews = 0

    for idx, sku in enumerate(target_skus):
        search_data = products_map.get(sku, {})
        print(f"\n  [{idx+1}/{len(target_skus)}] SKU={sku}")

        # 获取商品详情
        print(f"    获取详情...")
        detail = fetch_product_detail(browser, sku)
        title = detail.get("title", "") or search_data.get("title", "")
        brand = detail.get("brand", "")
        price = detail.get("price", 0) or search_data.get("price", 0)
        shop = detail.get("shop", "") or search_data.get("shop", "")
        model = detail.get("model", "")
        print(f"    标题: {title[:50]}")
        print(f"    品牌: {brand} | 价格: ¥{price} | 店铺: {shop[:15]} | 型号: {model}")

        # 保存商品
        save_product(sku, search_data, detail)

        # 获取评价摘要 - JS fetch方式
        print(f"    获取评价(JS fetch)...")
        # 确保在JD域名下执行fetch
        if "jd.com" not in (browser.get_url() or ""):
            browser.navigate(f"https://item.jd.com/{sku}.html", wait_sec=1)

        stats = fetch_comment_summary(browser, sku)
        if stats and "error" not in stats:
            print(f"    评价: {stats['reviewCount']} | 好评率: {stats['goodRate']:.1f}% | 差评: {stats['poorCount']}")
            update_review_stats(sku, stats)

            # 获取评价列表
            if stats["reviewCount"] > 0:
                print(f"    获取评价列表...")
                comments = fetch_comment_list(browser, sku, MAX_COMMENT_PAGES)
                if comments:
                    print(f"    保存 {len(comments)} 条评价")
                    save_reviews(sku, comments)
                    total_reviews += len(comments)
                else:
                    print(f"    评价列表为空")
        else:
            print(f"    API返回: {stats.get('error', '未知') if stats else '无响应'}")
            # 备用: 评价页HTML
            print(f"    尝试评价页HTML...")
            stats2, reviews = fetch_reviews_from_review_page(browser, sku, max_pages=3)
            if stats2:
                update_review_stats(sku, stats2)
            if reviews:
                print(f"    评价页获取 {len(reviews)} 条评价")
                save_reviews(sku, reviews)
                total_reviews += len(reviews)

        time.sleep(random.uniform(0.5, 1.0))

    # 统计
    print(f"\n{'='*60}")
    print(f"京东爬虫完成!")
    print(f"  评价总数: {total_reviews}")

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM products WHERE platform='jd'")
    print(f"  数据库商品: {c.fetchone()[0]}")
    c.execute("SELECT COUNT(*) FROM reviews WHERE platform='jd'")
    print(f"  数据库评价: {c.fetchone()[0]}")
    c.execute("SELECT COUNT(*) FROM products WHERE platform='jd' AND title != ''")
    print(f"  有标题: {c.fetchone()[0]}")
    c.execute("SELECT COUNT(*) FROM products WHERE platform='jd' AND brand IS NOT NULL AND brand != ''")
    print(f"  有品牌: {c.fetchone()[0]}")
    c.execute("SELECT COUNT(*) FROM products WHERE platform='jd' AND price > 0")
    print(f"  有价格: {c.fetchone()[0]}")
    c.execute("SELECT COUNT(*) FROM products WHERE platform='jd' AND shop_name != ''")
    print(f"  有店铺: {c.fetchone()[0]}")
    c.execute("SELECT brand, COUNT(*) as cnt FROM products WHERE platform='jd' AND brand != '' GROUP BY brand ORDER BY cnt DESC LIMIT 5")
    for row in c.fetchall():
        print(f"    品牌: {row[0]} ({row[1]}个商品)")
    conn.close()
    print(f"{'='*60}")

    browser.close()


if __name__ == "__main__":
    main()
