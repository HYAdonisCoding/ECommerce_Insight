#!/usr/bin/env python3
"""
京东电火灶爬虫 V3 - DrissionPage + 资源屏蔽 + JS深度提取
改进:
  1. 屏蔽图片/视频/字体, 极速加载
  2. JS提取搜索页所有字段
  3. 商品详情页提取品牌/型号/规格
  4. 评价页HTML解析(不依赖被封锁的API)
  5. 评价摘要从商品页内嵌数据提取
"""
import sqlite3
import json
import re
import time
import os
import random
from DrissionPage import ChromiumPage, ChromiumOptions

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ecommerce.db")

KEYWORDS = [
    "电火灶", "电焰灶", "电燃灶",
    "电火灶 家用", "电火灶 商用", "电焰灶 双灶",
    "华火电火灶", "星焰电火灶",
]
MAX_PAGES = 3


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_browser():
    """初始化浏览器 - 屏蔽图片/视频/字体"""
    co = ChromiumOptions()
    co.set_browser_path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    co.set_argument("--no-first-run")
    co.set_argument("--no-default-browser-check")
    co.set_argument("--disable-blink-features=AutomationControlled")
    co.set_argument("--window-size=1920,1080")
    co.set_argument("--disable-gpu")
    # 屏蔽图片
    co.set_pref("profile.managed_default_content_settings.images", 2)
    co.set_pref("profile.managed_default_content_settings.media_stream", 2)
    co.set_pref("profile.default_content_setting_values.notifications", 2)
    co.set_pref("profile.managed_default_content_settings.plugins", 2)
    co.auto_port()
    page = ChromiumPage(co)

    # 通过CDP屏蔽资源
    try:
        page.run_cdp("Network.setBlockedURLs", urls=[
            "*.jpg", "*.jpeg", "*.png", "*.gif", "*.webp", "*.svg", "*.ico", "*.bmp",
            "*.mp4", "*.webm", "*.avi", "*.mov", "*.flv", "*.m3u8", "*.ts",
            "*.mp3", "*.wav", "*.ogg", "*.aac", "*.m4a",
            "*.woff", "*.woff2", "*.ttf", "*.eot",
            "*://*.jd.com/ddimg.jd.com/*",
            "*://img*.jd.com/*",
            "*://m.360buyimg.com/*",
        ])
        print("  [OK] 资源屏蔽已启用 (图片/视频/字体)")
    except Exception as e:
        print(f"  [WARN] CDP屏蔽失败: {e}, 使用pref屏蔽")

    return page


# ==================== 搜索页提取 ====================

SEARCH_JS = """
(function() {
    var products = [];
    // 多选择器适配京东不同版本页面
    var items = document.querySelectorAll('[data-sku], li.gl-item, .J_goodsList li, [class*="gl-item"]');
    if (items.length === 0) {
        // 备用: 找所有含item.jd.com链接的容器
        items = document.querySelectorAll('a[href*="item.jd.com"]');
        var seen = {};
        items = Array.from(items).filter(function(a) {
            var p = a.closest('li, div[class*="item"], div[class*="card"]');
            if (!p) return false;
            var key = p.textContent.substring(0, 50);
            if (seen[key]) return false;
            seen[key] = true;
            return true;
        });
    }

    items.forEach(function(item) {
        try {
            var sku = item.getAttribute ? (item.getAttribute('data-sku') || item.getAttribute('data-pid') || '') : '';
            if (!sku && item.querySelector) {
                var link = item.querySelector('a[href*="item.jd.com"]');
                if (link) {
                    var m = (link.href || '').match(/item\\.jd\\.com\\/(\\d+)/);
                    if (m) sku = m[1];
                }
            }
            if (!sku && item.href) {
                var m2 = item.href.match(/item\\.jd\\.com\\/(\\d+)/);
                if (m2) sku = m2[1];
            }
            if (!sku) return;

            var title = '';
            var titleEl = item.querySelector ? item.querySelector('.p-name em, .p-name a, .p-name, [class*="title"] a, [class*="Title"] a, a[href*="item.jd.com"]') : null;
            if (titleEl) title = titleEl.textContent.trim();
            // 如果title是链接本身
            if (!title && item.textContent) title = item.textContent.trim().substring(0, 100);

            var price = 0;
            var priceEls = item.querySelectorAll ? item.querySelectorAll('.p-price i, .p-price strong i, .p-price, [class*="price"]') : [];
            for (var pe of priceEls) {
                var pm = (pe.textContent || '').match(/[\\d.]+/);
                if (pm && parseFloat(pm[0]) > 0) { price = parseFloat(pm[0]); break; }
            }

            var origPrice = 0;
            var origEl = item.querySelector ? item.querySelector('.p-price del, [class*="origin"]') : null;
            if (origEl) {
                var om = (origEl.textContent || '').match(/[\\d.]+/);
                if (om) origPrice = parseFloat(om[0]);
            }

            var shop = '';
            var shopEl = item.querySelector ? item.querySelector('.p-shop a, .p-shop, [class*="shop"] a, [class*="Shop"]') : null;
            if (shopEl) shop = shopEl.textContent.trim();

            var commentCount = 0;
            var commentEl = item.querySelector ? item.querySelector('.p-commit a, .p-commit strong a, .p-commit, [class*="comment"], [class*="Comment"]') : null;
            if (commentEl) {
                var ct = commentEl.textContent || '';
                var cm = ct.match(/([\\d.]+)\\s*万?/);
                if (cm) {
                    commentCount = ct.includes('万') ? parseInt(parseFloat(cm[1]) * 10000) : parseInt(cm[1]);
                }
            }

            var img = '';
            var imgEl = item.querySelector ? item.querySelector('img') : null;
            if (imgEl) img = imgEl.getAttribute('data-lazy-img') || imgEl.src || '';

            products.push({
                sku: sku, title: title, price: price,
                origPrice: origPrice, shop: shop,
                commentCount: commentCount, img: img,
                url: 'https://item.jd.com/' + sku + '.html'
            });
        } catch(e) {}
    });
    return JSON.stringify(products);
})();
"""


def search_jd(page, keyword, page_num):
    """搜索京东, 返回商品列表"""
    url = f"https://search.jd.com/Search?keyword={keyword}&enc=utf-8&page={2*page_num - 1}"
    print(f"  -> {url}")
    page.get(url)
    time.sleep(1.5)

    # 检测是否被拦截
    html = page.html
    if "验证" in html[:2000] or "系统繁忙" in html[:2000]:
        print("  [!] 检测到验证页面, 尝试等待...")
        time.sleep(5)
        # 再试一次
        page.get(url)
        time.sleep(2)

    # 滚动加载
    page.scroll.to_bottom()
    time.sleep(0.5)
    page.scroll.to_top()
    time.sleep(0.3)

    # JS提取
    products = []
    try:
        result = page.run_js(SEARCH_JS)
        if result:
            data = json.loads(result)
            print(f"  JS提取到 {len(data)} 个商品")
            for item in data:
                products.append({
                    "product_id": item.get("sku", ""),
                    "title": item.get("title", ""),
                    "price": item.get("price", 0),
                    "original_price": item.get("origPrice", 0) or None,
                    "shop_name": item.get("shop", ""),
                    "review_count": item.get("commentCount", 0),
                    "image_url": item.get("img", ""),
                    "url": item.get("url", ""),
                    "search_keyword": keyword,
                })
    except Exception as e:
        print(f"  JS提取失败: {e}")

    # 备用: 正则提取
    if not products:
        print("  JS无结果, 尝试正则...")
        html = page.html
        skus = re.findall(r'data-sku="(\d+)"', html)
        skus = list(dict.fromkeys(skus))  # 去重保序
        for sku in skus:
            products.append({
                "product_id": sku,
                "title": "", "price": 0, "shop_name": "",
                "url": f"https://item.jd.com/{sku}.html",
                "search_keyword": keyword,
            })
        print(f"  正则提取到 {len(products)} 个SKU")

    log_search(keyword, "jd", page_num, len(products))
    return products


# ==================== 商品详情页 ====================

DETAIL_JS = """
(function() {
    var data = {};

    // 标题
    var titleEl = document.querySelector('.sku-name, #name, .itemInfo-wrap .sku-name, [class*="sku-name"]');
    if (titleEl) data.title = titleEl.textContent.trim();
    if (!data.title) {
        var t = document.querySelector('title');
        if (t) data.title = t.textContent.replace(/-京东.*$/, '').trim();
    }

    // 价格
    var priceEls = document.querySelectorAll('.summary-price .price, .p-price .price, .price.J-p-' + window.skuId + ' .price, [class*="summary"] [class*="price"]');
    for (var p of priceEls) {
        var m = (p.textContent || '').match(/[\\d.]+/);
        if (m && parseFloat(m[0]) > 0) { data.price = parseFloat(m[0]); break; }
    }

    // 原价
    var origEl = document.querySelector('.origin-price .price, .p-price del, [class*="origin"] del');
    if (origEl) {
        var m2 = (origEl.textContent || '').match(/[\\d.]+/);
        if (m2) data.originalPrice = parseFloat(m2[0]);
    }

    // 品牌 - 从面包屑
    var crumbEls = document.querySelectorAll('#crumb-wrap .ellipsis a, .breadcrumb a, [class*="crumb"] a, [class*="Crumb"] a');
    for (var c of crumbEls) {
        var t = c.textContent.trim();
        if (t && t.length < 20 && t !== '首页') { data.brand = t; break; }
    }

    // 店铺
    var shopEls = document.querySelectorAll('.J-hove-wrap .item a, .popstore-name a, .shop-name a, [class*="shop"] a, [class*="Store"] a, #popbox a');
    for (var s of shopEls) {
        var t = s.textContent.trim();
        if (t && t.length < 30 && t !== '进店逛逛') { data.shop = t; break; }
    }

    // 型号和品牌 - 从参数列表
    var params = document.querySelectorAll('.parameter2 li, .Ptable-item li, [class*="param"] li, [class*="Param"] li, .detail-attr li');
    params.forEach(function(p) {
        var text = (p.textContent || '').trim();
        if (/型号/.test(text)) data.model = text.replace(/.*型号[：:]?\\s*/, '').trim();
        if (/品牌/.test(text) && !data.brand) data.brand = text.replace(/.*品牌[：:]?\\s*/, '').trim();
        if (/商品名称/.test(text) && !data.model) data.model = text.replace(/.*商品名称[：:]?\\s*/, '').trim();
    });

    // 评价统计 - 从页面内嵌数据
    var scripts = document.querySelectorAll('script');
    scripts.forEach(function(s) {
        var t = s.textContent || '';
        // 尝试从 pageData 或其他内嵌数据提取评价统计
        if (t.indexOf('commentCount') > -1 || t.indexOf('goodRate') > -1) {
            var cm = t.match(/commentCount['"]?\\s*[:=]\\s*['"]?(\\d+)/);
            if (cm) data.commentCount = parseInt(cm[1]);
            var grm = t.match(/goodRate['"]?\\s*[:=]\\s*['"]?([\\d.]+)/);
            if (grm) data.goodRate = parseFloat(grm[1]);
        }
    });

    return JSON.stringify(data);
})();
"""


def fetch_product_detail(page, sku):
    """从商品详情页获取品牌/型号/价格等"""
    url = f"https://item.jd.com/{sku}.html"
    try:
        page.get(url)
        time.sleep(1.0)

        result = page.run_js(DETAIL_JS)
        if result:
            data = json.loads(result)
            print(f"    详情: {data.get('brand', '?')} | ¥{data.get('price', '?')} | {data.get('shop', '?')[:15]}")
            return data
    except Exception as e:
        print(f"    详情获取失败: {e}")
    return {}


# ==================== 评价页HTML解析 ====================

REVIEW_JS = """
(function() {
    var result = { stats: {}, reviews: [] };

    // 评价统计
    var statEls = document.querySelectorAll('.percent-con, [class*="percent"], [class*="Percent"]');
    statEls.forEach(function(el) {
        var t = el.textContent.trim();
        if (t.indexOf('%') > -1) {
            if (!result.stats.goodRate) result.stats.goodRate = t;
        }
    });

    // 评价数量
    var countEls = document.querySelectorAll('[class*="comment-count"], [class*="CommentCount"], .filter .line');
    countEls.forEach(function(el) {
        var t = el.textContent.trim();
        var m = t.match(/(\\d+)\\s*万?/);
        if (m) {
            var n = t.includes('万') ? parseInt(parseFloat(m[1]) * 10000) : parseInt(m[1]);
            if (t.indexOf('好') > -1) result.stats.goodCount = n;
            else if (t.indexOf('中') > -1) result.stats.neutralCount = n;
            else if (t.indexOf('差') > -1) result.stats.poorCount = n;
            else if (!result.stats.totalCount) result.stats.totalCount = n;
        }
    });

    // 好中差评率
    var rateEls = document.querySelectorAll('[class*="rate"], [class*="Rate"]');
    rateEls.forEach(function(el) {
        var t = el.textContent.trim();
        if (t.indexOf('%') > -1) {
            if (t.indexOf('好') > -1) result.stats.goodRate = t.replace(/.*?(\\d+\\.?\\d*)%/, '$1');
            else if (t.indexOf('中') > -1) result.stats.neutralRate = t.replace(/.*?(\\d+\\.?\\d*)%/, '$1');
            else if (t.indexOf('差') > -1) result.stats.poorRate = t.replace(/.*?(\\d+\\.?\\d*)%/, '$1');
        }
    });

    // 评价列表
    var reviewEls = document.querySelectorAll('.comment-item, [class*="comment-item"], [class*="CommentItem"], [class*="comment"] dl, .comment-list .comment-item');
    reviewEls.forEach(function(el) {
        try {
            var review = {};

            // 星级
            var starEl = el.querySelector('[class*="star"], .star, .comment-star');
            if (starEl) {
                var starClass = starEl.className || '';
                var sm = starClass.match(/star(\\d)/) || starClass.match(/(\\d)星/);
                if (sm) review.rating = parseInt(sm[1]);
            }

            // 内容
            var contentEl = el.querySelector('.comment-content, [class*="content"], p');
            if (contentEl) review.content = contentEl.textContent.trim();

            // 作者
            var authorEl = el.querySelector('.user-info, .user-column, [class*="user"], [class*="User"]');
            if (authorEl) review.author = authorEl.textContent.trim();

            // 日期
            var dateEl = el.querySelector('.comment-date, .date, [class*="date"], [class*="Date"]');
            if (dateEl) review.date = dateEl.textContent.trim();

            // 规格
            var tagEl = el.querySelector('.comment-message .tag, [class*="tag"], [class*="sku-info"]');
            if (tagEl) review.variant = tagEl.textContent.trim();

            // 是否有图
            var imgEls = el.querySelectorAll('img, [class*="photo"], [class*="image"]');
            review.hasImage = imgEls.length > 0 ? 1 : 0;

            if (review.content || review.rating) {
                review.reviewId = 'r_' + Math.random().toString(36).substr(2, 9);
                result.reviews.push(review);
            }
        } catch(e) {}
    });

    return JSON.stringify(result);
})();
"""


def fetch_reviews_from_page(page, sku, max_pages=3):
    """从评价页HTML获取评价数据(不用API)"""
    all_reviews = []
    stats = {}

    for p in range(1, max_pages + 1):
        url = f"https://club.jd.com/review/{sku}-3-{p}.html"
        try:
            page.get(url)
            time.sleep(0.8)

            result = page.run_js(REVIEW_JS)
            if result:
                data = json.loads(result)
                if p == 1:
                    stats = data.get("stats", {})

                reviews = data.get("reviews", [])
                if not reviews:
                    break
                all_reviews.extend(reviews)
                print(f"      评价页{p}: {len(reviews)}条")
            else:
                # 检查页面状态
                html = page.html
                if "系统繁忙" in html:
                    print(f"      评价页{p}: 系统繁忙, 跳过")
                    break
                if "暂无评价" in html:
                    print(f"      评价页{p}: 暂无评价")
                    break
                break
        except Exception as e:
            print(f"      评价页{p}失败: {e}")
            break
        time.sleep(random.uniform(0.3, 0.8))

    return stats, all_reviews


# ==================== 评价API备用 ====================

def fetch_comment_summary_api(page, sku):
    """尝试API获取评价摘要(可能被封锁)"""
    url = f"https://club.jd.com/comment/productCommentSummaries.action?referenceIds={sku}"
    try:
        page.get(url)
        time.sleep(0.5)
        text = page.html
        if "系统繁忙" in text or "错误" in text:
            return None
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            info = data.get("CommentsCount", [{}])[0]
            return {
                "review_count": info.get("CommentCount", 0),
                "good_count": info.get("GoodCount", 0),
                "neutral_count": info.get("GeneralCount", 0),
                "poor_count": info.get("PoorCount", 0),
                "good_rate": info.get("GoodRate", 0),
                "neutral_rate": info.get("GeneralRate", 0),
                "poor_rate": info.get("PoorRate", 0),
            }
    except Exception:
        pass
    return None


# ==================== 数据库操作 ====================

def log_search(keyword, platform, page_num, count):
    conn = get_db()
    conn.execute("INSERT INTO search_log (keyword, platform, page, result_count) VALUES (?,?,?,?)",
                 (keyword, platform, page_num, count))
    conn.commit()
    conn.close()


def save_product(product, detail=None, platform="jd"):
    """保存/更新商品"""
    conn = get_db()
    p = product
    d = detail or {}

    conn.execute("""
        INSERT OR REPLACE INTO products
        (platform, product_id, title, price, original_price, shop_name, brand,
         model, url, review_count, image_url, search_keyword)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        platform,
        p.get("product_id", ""),
        d.get("title", "") or p.get("title", ""),
        d.get("price", 0) or p.get("price", 0),
        d.get("originalPrice") or p.get("original_price"),
        d.get("shop", "") or p.get("shop_name", ""),
        d.get("brand", ""),
        d.get("model", ""),
        p.get("url", ""),
        p.get("review_count", 0),
        p.get("image_url", ""),
        p.get("search_keyword", ""),
    ))
    conn.commit()
    conn.close()


def update_product_review_stats(sku, stats):
    """更新评价统计"""
    if not stats:
        return
    conn = get_db()
    fields = []
    values = []
    mapping = {
        "review_count": "totalCount",
        "good_count": "goodCount",
        "neutral_count": "neutralCount",
        "poor_count": "poorCount",
        "good_rate": "goodRate",
        "neutral_rate": "neutralRate",
        "poor_rate": "poorRate",
    }
    for db_field, stats_key in mapping.items():
        if stats_key in stats and stats[stats_key] is not None:
            val = stats[stats_key]
            # 处理百分比字符串
            if isinstance(val, str):
                m = re.search(r'[\d.]+', val)
                val = float(m.group()) if m else 0
            fields.append(f"{db_field} = ?")
            values.append(val)

    if fields:
        values.append(sku)
        conn.execute(f"UPDATE products SET {', '.join(fields)} WHERE platform='jd' AND product_id=?", values)
        conn.commit()
    conn.close()


def save_reviews(sku, reviews, platform="jd"):
    """保存评价"""
    conn = get_db()
    for r in reviews:
        rating = r.get("rating", 0)
        if not rating:
            rating = 5  # 默认5星
        sentiment = "positive" if rating >= 4 else ("negative" if rating <= 2 else "neutral")

        conn.execute("""
            INSERT OR IGNORE INTO reviews
            (platform, product_id, review_id, rating, content, author, date,
             variant, has_image, sentiment)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            platform, sku, r.get("reviewId", f"r_{random.randint(1,9999999)}"),
            rating, r.get("content", ""), r.get("author", ""),
            r.get("date", ""), r.get("variant", ""),
            r.get("hasImage", 0), sentiment,
        ))
    conn.commit()
    conn.close()


# ==================== 主程序 ====================

def main():
    print("=" * 60)
    print("京东电火灶爬虫 V3 (DrissionPage + 资源屏蔽)")
    print("=" * 60)

    print("\n[1] 启动浏览器...")
    page = init_browser()

    print("[2] 访问京东首页获取Cookie...")
    page.get("https://www.jd.com/")
    time.sleep(2)

    total_products = 0
    total_reviews = 0
    seen_skus = set()

    for keyword in KEYWORDS:
        print(f"\n{'='*50}")
        print(f"关键词: {keyword}")
        print(f"{'='*50}")

        for page_num in range(1, MAX_PAGES + 1):
            print(f"\n  --- 第{page_num}页 ---")
            products = search_jd(page, keyword, page_num)

            if not products:
                print(f"  无结果, 跳过")
                break

            new_count = 0
            for idx, product in enumerate(products):
                sku = product.get("product_id", "")
                if not sku or sku in seen_skus:
                    continue
                seen_skus.add(sku)
                new_count += 1

                print(f"\n  [{idx+1}/{len(products)}] SKU={sku}")
                print(f"    搜索: {product.get('title','')[:40]} | ¥{product.get('price',0)} | {product.get('shop_name','')[:15]}")

                # 获取商品详情
                detail = fetch_product_detail(page, sku)
                save_product(product, detail)
                total_products += 1

                # 获取评价摘要 - 先试API, 失败则用评价页
                print(f"    获取评价...")
                stats = fetch_comment_summary_api(page, sku)
                if stats:
                    print(f"    API: 评价{stats['review_count']} | 好评率{stats['good_rate']:.1f}%")
                    update_product_review_stats(sku, stats)

                    # API通了, 继续用API获取评价
                    reviews = fetch_reviews_api(page, sku, max_pages=3)
                else:
                    # API不通, 从评价页HTML提取
                    print(f"    API被封锁, 改用评价页...")
                    stats2, reviews = fetch_reviews_from_page(page, sku, max_pages=3)
                    if stats2:
                        update_product_review_stats(sku, stats2)

                if reviews:
                    print(f"    保存 {len(reviews)} 条评价")
                    save_reviews(sku, reviews)
                    total_reviews += len(reviews)
                else:
                    print(f"    无评价数据")

                time.sleep(random.uniform(0.5, 1.0))

            print(f"\n  本页新增商品: {new_count}")
            time.sleep(random.uniform(1, 2))

    # 统计
    print(f"\n{'='*60}")
    print(f"京东爬虫完成!")
    print(f"  采集商品: {total_products}")
    print(f"  采集评价: {total_reviews}")

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM products WHERE platform='jd'")
    print(f"  数据库商品: {c.fetchone()[0]}")
    c.execute("SELECT COUNT(*) FROM reviews WHERE platform='jd'")
    print(f"  数据库评价: {c.fetchone()[0]}")
    c.execute("SELECT brand, COUNT(*) FROM products WHERE platform='jd' AND brand IS NOT NULL GROUP BY brand ORDER BY COUNT(*) DESC LIMIT 5")
    brands = c.fetchall()
    if brands:
        print(f"  品牌分布: {brands}")
    c.execute("SELECT COUNT(*) FROM products WHERE title != '' AND price > 0")
    print(f"  完整记录: {c.fetchone()[0]}")
    conn.close()
    print(f"{'='*60}")

    try:
        page.quit()
    except Exception:
        pass


def fetch_reviews_api(page, sku, max_pages=3):
    """API方式获取评价(可能被封锁)"""
    all_reviews = []
    for p in range(max_pages):
        url = (f"https://club.jd.com/comment/productPageComments.action?"
               f"productId={sku}&score=0&sortType=5&page={p}&pageSize=10")
        try:
            page.get(url)
            time.sleep(0.4)
            text = page.html
            if "系统繁忙" in text:
                break
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                comments = data.get("comments", [])
                if not comments:
                    break
                for c in comments:
                    all_reviews.append({
                        "reviewId": str(c.get("id", "")),
                        "rating": c.get("score", 5),
                        "content": c.get("content", ""),
                        "author": c.get("nickname", ""),
                        "date": c.get("creationTime", ""),
                        "variant": (c.get("productColor", "") + " " + c.get("productSize", "")).strip(),
                        "hasImage": 1 if c.get("images") else 0,
                    })
                print(f"      API第{p+1}页: {len(comments)}条")
            else:
                break
        except Exception:
            break
        time.sleep(random.uniform(0.3, 0.6))
    return all_reviews


if __name__ == "__main__":
    main()
