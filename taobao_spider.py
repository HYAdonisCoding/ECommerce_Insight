#!/usr/bin/env python3
"""
淘宝电火灶爬虫 - DrissionPage浏览器模式
需要用户扫码登录后自动采集
"""
import sqlite3
import json
import re
import time
import os
import random
from DrissionPage import ChromiumPage, ChromiumOptions

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ecommerce.db")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

KEYWORDS = [
    "电火灶",
    "电焰灶",
    "电燃灶",
    "电火灶 家用 双灶",
    "电火灶 商用",
    "华火电火灶",
    "电焰灶 明火",
    "电火灶 大火力",
]

MAX_PAGES = 3


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_browser():
    """初始化浏览器"""
    co = ChromiumOptions()
    co.set_argument("--no-first-run")
    co.set_argument("--disable-blink-features=AutomationControlled")
    co.set_argument("--window-size=1920,1080")
    page = ChromiumPage(co)
    return page


def wait_for_login(page):
    """等待用户扫码登录淘宝"""
    print("\n" + "=" * 50)
    print("需要登录淘宝!")
    print("请在弹出的浏览器中扫码登录")
    print("登录成功后脚本会自动继续...")
    print("=" * 50 + "\n")

    page.get("https://login.taobao.com/")
    time.sleep(3)

    # 等待登录成功 - 检测页面是否跳转或出现用户名
    max_wait = 120  # 最多等2分钟
    for i in range(max_wait):
        try:
            url = page.url
            # 登录成功后通常会跳转到首页或my.taobao.com
            if "login" not in url and "taobao.com" in url:
                # 再确认一下
                time.sleep(2)
                if "login" not in page.url:
                    print("登录成功!")
                    return True
        except Exception:
            pass
        time.sleep(1)
        if i % 10 == 0 and i > 0:
            print(f"  等待登录中... ({i}s)")

    print("登录超时, 尝试继续...")
    return False


def search_taobao(page, keyword, page_num):
    """搜索淘宝商品"""
    url = f"https://s.taobao.com/search?q={keyword}&sort=sale-desc&page={page_num}"
    print(f"  访问: {url}")
    page.get(url)
    time.sleep(3)

    # 滚动加载
    for _ in range(3):
        page.scroll.to_bottom()
        time.sleep(0.8)
    page.scroll.to_top()
    time.sleep(0.5)

    products = []

    # 方法1: 从页面JS中提取 g_page_config 或其他内嵌JSON
    try:
        # 淘宝搜索结果通常内嵌在script标签中
        js_code = """
        try {
            // 尝试多种方式获取商品数据
            var items = [];
            var cards = document.querySelectorAll('[class*="Content--"] [class*="Card--"]');
            if (cards.length === 0) {
                cards = document.querySelectorAll('.m-itemlistlist .items .item');
            }
            if (cards.length === 0) {
                cards = document.querySelectorAll('[data-spm="dlist"]');
            }

            cards.forEach(function(card) {
                try {
                    var title = '';
                    var price = '';
                    var sales = '';
                    var shop = '';
                    var link = '';
                    var img = '';
                    var itemId = '';

                    // 标题
                    var titleEl = card.querySelector('[class*="Title--"] a, .title a, .J_ClickStat, a[class*="title"]');
                    if (titleEl) {
                        title = titleEl.textContent.trim();
                        link = titleEl.href || '';
                        var m = link.match(/id=(\\d+)/);
                        if (m) itemId = m[1];
                    }

                    // 价格
                    var priceEl = card.querySelector('[class*="Price--"], .price strong, .price');
                    if (priceEl) price = priceEl.textContent.trim();

                    // 销量
                    var salesEl = card.querySelector('[class*="Deal--"], .deal-cnt, [class*="sale"]');
                    if (salesEl) sales = salesEl.textContent.trim();

                    // 店铺
                    var shopEl = card.querySelector('[class*="Shop--"], .shop, .shopname');
                    if (shopEl) shop = shopEl.textContent.trim();

                    // 图片
                    var imgEl = card.querySelector('img');
                    if (imgEl) img = imgEl.src || imgEl.getAttribute('data-src') || '';

                    // 商品ID
                    if (!itemId) {
                        var allLinks = card.querySelectorAll('a');
                        for (var a of allLinks) {
                            var m2 = (a.href || '').match(/id=(\\d+)/);
                            if (m2) { itemId = m2[1]; break; }
                        }
                    }

                    if (title || itemId) {
                        items.push({
                            title: title,
                            price: price,
                            sales: sales,
                            shop: shop,
                            link: link,
                            img: img,
                            itemId: itemId
                        });
                    }
                } catch(e) {}
            });

            return JSON.stringify(items);
        } catch(e) {
            return JSON.stringify({error: e.message, items: []});
        }
        """
        result = page.run_js(js_code)
        if result:
            data = json.loads(result)
            if isinstance(data, list):
                for item in data:
                    if item.get("itemId") or item.get("title"):
                        product = {
                            "product_id": item.get("itemId", ""),
                            "title": item.get("title", ""),
                            "price_str": item.get("price", ""),
                            "sales_volume": item.get("sales", ""),
                            "shop_name": item.get("shop", ""),
                            "url": item.get("link", ""),
                            "image_url": item.get("img", ""),
                            "search_keyword": keyword,
                        }
                        # 解析价格
                        price_match = re.search(r'[\d.]+', product["price_str"])
                        product["price"] = float(price_match.group()) if price_match else 0.0

                        # 解析销量
                        product["sales_count"] = parse_sales(product["sales_volume"])

                        products.append(product)

                print(f"  JS提取到 {len(products)} 个商品")
    except Exception as e:
        print(f"  JS提取失败: {e}")

    # 方法2: 如果JS没提取到, 尝试用DOM选择器
    if not products:
        try:
            items = page.eles('css:[class*="Content--"] [class*="Card--"]')
            if not items:
                items = page.eles('css:.m-itemlistlist .item')
            if not items:
                items = page.eles('css:div[data-spm="dlist"]')

            print(f"  DOM选择器找到 {len(items)} 个元素")

            for item in items:
                try:
                    product = {}

                    # 标题和链接
                    title_el = item.ele('css:[class*="Title--"] a', timeout=0.5) or \
                               item.ele('css:.title a', timeout=0.5) or \
                               item.ele('css:a.J_ClickStat', timeout=0.5)
                    if title_el:
                        product["title"] = title_el.text.strip()
                        href = title_el.attr("href") or ""
                        m = re.search(r'id=(\d+)', href)
                        if m:
                            product["product_id"] = m.group(1)
                            product["url"] = href

                    if not product.get("product_id"):
                        continue

                    # 价格
                    price_el = item.ele('css:[class*="Price--"]', timeout=0.5) or \
                               item.ele('css:.price strong', timeout=0.5)
                    if price_el:
                        price_match = re.search(r'[\d.]+', price_el.text)
                        product["price"] = float(price_match.group()) if price_match else 0.0

                    # 销量
                    sales_el = item.ele('css:[class*="Deal--"]', timeout=0.5) or \
                               item.ele('css:.deal-cnt', timeout=0.5)
                    if sales_el:
                        product["sales_volume"] = sales_el.text.strip()
                        product["sales_count"] = parse_sales(product["sales_volume"])

                    # 店铺
                    shop_el = item.ele('css:[class*="Shop--"]', timeout=0.5) or \
                              item.ele('css:.shop', timeout=0.5)
                    if shop_el:
                        product["shop_name"] = shop_el.text.strip()

                    # 图片
                    img_el = item.ele('css:img', timeout=0.5)
                    if img_el:
                        product["image_url"] = img_el.attr("src") or img_el.attr("data-src") or ""

                    product["search_keyword"] = keyword
                    if not product.get("url"):
                        product["url"] = f"https://item.taobao.com/item.htm?id={product['product_id']}"

                    products.append(product)
                except Exception:
                    continue
        except Exception as e:
            print(f"  DOM提取失败: {e}")

    # 方法3: 从HTML正则提取
    if not products:
        html = page.html
        # 尝试提取nid
        nids = re.findall(r'"nid"\s*:\s*"?(\d+)"?', html)
        titles = re.findall(r'"raw_title"\s*:\s*"([^"]*)"', html)
        prices = re.findall(r'"view_price"\s*:\s*"([\d.]+)"', html)
        sales = re.findall(r'"view_sales"\s*:\s*"([^"]*)"', html)
        nicks = re.findall(r'"nick"\s*:\s*"([^"]*)"', html)
        detail_urls = re.findall(r'"detail_url"\s*:\s*"([^"]*)"', html)

        print(f"  正则提取: nid={len(nids)} title={len(titles)} price={len(prices)}")

        for i in range(min(len(nids), len(titles))):
            product = {
                "product_id": nids[i],
                "title": titles[i],
                "price": float(prices[i]) if i < len(prices) else 0.0,
                "sales_volume": sales[i] if i < len(sales) else "",
                "sales_count": parse_sales(sales[i]) if i < len(sales) else 0,
                "shop_name": nicks[i] if i < len(nicks) else "",
                "url": detail_urls[i].replace("\\", "") if i < len(detail_urls) else f"https://item.taobao.com/item.htm?id={nids[i]}",
                "search_keyword": keyword,
            }
            products.append(product)

    # 检查是否需要登录
    if not products:
        html = page.html
        if "请登录" in html or "login" in page.url:
            print("  >>> 需要登录, 等待用户扫码...")
            wait_for_login(page)
            # 重新搜索
            page.get(url)
            time.sleep(3)
            # 简单重试一次JS提取
            try:
                result = page.run_js(js_code)
                if result:
                    data = json.loads(result)
                    if isinstance(data, list):
                        for item in data:
                            if item.get("itemId") or item.get("title"):
                                product = {
                                    "product_id": item.get("itemId", ""),
                                    "title": item.get("title", ""),
                                    "price_str": item.get("price", ""),
                                    "sales_volume": item.get("sales", ""),
                                    "shop_name": item.get("shop", ""),
                                    "url": item.get("link", ""),
                                    "image_url": item.get("img", ""),
                                    "search_keyword": keyword,
                                }
                                price_match = re.search(r'[\d.]+', product["price_str"])
                                product["price"] = float(price_match.group()) if price_match else 0.0
                                product["sales_count"] = parse_sales(product["sales_volume"])
                                products.append(product)
            except Exception:
                pass

    log_search(keyword, "taobao", page_num, len(products))
    return products


def parse_sales(text):
    """解析'月销1000+'这种文本为数字"""
    if not text:
        return 0
    text = text.replace("月销", "").replace("人收货", "").replace("人付款", "").replace("付款", "").replace("+", "").strip()
    if "万" in text:
        try:
            return int(float(text.replace("万", "")) * 10000)
        except ValueError:
            return 0
    if "千" in text:
        try:
            return int(float(text.replace("千", "")) * 1000)
        except ValueError:
            return 0
    try:
        return int(text)
    except ValueError:
        return 0


def log_search(keyword, platform, page_num, count):
    conn = get_db()
    conn.execute(
        "INSERT INTO search_log (keyword, platform, page, result_count) VALUES (?,?,?,?)",
        (keyword, platform, page_num, count),
    )
    conn.commit()
    conn.close()


def save_product(product, platform="taobao"):
    """保存商品到数据库"""
    conn = get_db()
    conn.execute("""
        INSERT OR REPLACE INTO products
        (platform, product_id, title, price, shop_name, url,
         sales_volume, sales_count, image_url, search_keyword)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (
        platform,
        product.get("product_id", ""),
        product.get("title", ""),
        product.get("price", 0),
        product.get("shop_name", ""),
        product.get("url", ""),
        product.get("sales_volume", ""),
        product.get("sales_count", 0),
        product.get("image_url", ""),
        product.get("search_keyword", ""),
    ))
    conn.commit()
    conn.close()


def fetch_taobao_reviews(page, item_id, max_pages=3):
    """获取淘宝商品评价"""
    all_reviews = []

    for p in range(1, max_pages + 1):
        # 淘宝评价API (H5)
        url = (f"https://h5api.m.taobao.com/h5/mtop.taobao.rate.detaillist.get/6.0/?"
               f"data=%7B%22auctionNumId%22%3A%22{item_id}%22%2C%22currentPageNum%22%3A{p}%2C%22pageSize%22%3A20%7D")

        try:
            page.get(url)
            time.sleep(1)
            text = page.html
            # 从响应中提取JSON
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                rate_list = data.get("data", {}).get("rateList", [])
                if not rate_list:
                    break

                for r in rate_list:
                    review = {
                        "review_id": str(r.get("rateId", "")),
                        "rating": r.get("grade", 5),
                        "content": r.get("content", ""),
                        "author": r.get("userNick", ""),
                        "date": r.get("date", ""),
                        "variant": r.get("auctionSku", ""),
                        "has_image": 1 if r.get("pics") else 0,
                        "has_video": 1 if r.get("video") else 0,
                        "is_append": 1 if r.get("appendContent") else 0,
                        "useful_count": 0,
                    }
                    all_reviews.append(review)

                print(f"      第{p}页: {len(rate_list)}条评价")
        except Exception as e:
            print(f"      评价获取失败(第{p}页): {e}")
            break
        time.sleep(random.uniform(0.5, 1))

    return all_reviews


def save_reviews(item_id, reviews, platform="taobao"):
    """保存评价到数据库"""
    conn = get_db()
    for r in reviews:
        sentiment = "neutral"
        if r["rating"] >= 4:
            sentiment = "positive"
        elif r["rating"] <= 2:
            sentiment = "negative"

        conn.execute("""
            INSERT OR IGNORE INTO reviews
            (platform, product_id, review_id, rating, content, author, date,
             variant, has_image, has_video, is_append, useful_count, sentiment)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            platform, item_id, r["review_id"], r["rating"], r["content"],
            r["author"], r["date"], r["variant"],
            r["has_image"], r["has_video"], r["is_append"], r["useful_count"],
            sentiment,
        ))
    conn.commit()
    conn.close()


def main():
    print("=" * 60)
    print("淘宝电火灶爬虫启动 (DrissionPage)")
    print("=" * 60)

    # 初始化数据库
    os.system(f'"{"/Users/adam/envs/py_arm64/bin/python"}" "{os.path.join(BASE_DIR, "db_init.py")}"')

    # 启动浏览器
    print("\n[1] 启动浏览器...")
    page = init_browser()

    # 先访问淘宝, 检查是否需要登录
    print("[2] 访问淘宝首页...")
    page.get("https://www.taobao.com/")
    time.sleep(2)

    # 检查登录状态
    html = page.html
    if "请登录" in html or "亲，请登录" in html:
        wait_for_login(page)
    else:
        # 尝试搜索, 如果跳转登录页再处理
        pass

    total_products = 0
    total_reviews = 0

    for keyword in KEYWORDS:
        print(f"\n{'='*40}")
        print(f"搜索关键词: {keyword}")
        print(f"{'='*40}")

        for page_num in range(1, MAX_PAGES + 1):
            print(f"\n  --- 第{page_num}页 ---")
            products = search_taobao(page, keyword, page_num)

            if not products:
                print(f"  第{page_num}页无结果")
                if page_num == 1:
                    print(f"  跳过此关键词")
                break

            print(f"  本页获取 {len(products)} 个商品")

            for idx, product in enumerate(products):
                if not product.get("product_id"):
                    continue

                item_id = product["product_id"]
                print(f"\n  [{idx+1}/{len(products)}] ID={item_id}")
                print(f"    标题: {product.get('title', '')[:50]}")
                print(f"    价格: ¥{product.get('price', 0)} | 销量: {product.get('sales_volume', '')}")

                # 保存商品
                save_product(product)
                total_products += 1

                # 获取评价 (前30个商品)
                if idx < 30:
                    print(f"    获取评价...")
                    reviews = fetch_taobao_reviews(page, item_id, max_pages=2)
                    if reviews:
                        print(f"    保存 {len(reviews)} 条评价")
                        save_reviews(item_id, reviews)
                        total_reviews += len(reviews)

                time.sleep(random.uniform(0.5, 1.5))

            time.sleep(random.uniform(2, 3))

    # 统计
    print(f"\n{'='*60}")
    print(f"淘宝爬虫完成!")
    print(f"  采集商品: {total_products}")
    print(f"  采集评价: {total_reviews}")

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM products WHERE platform='taobao'")
    db_products = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM reviews WHERE platform='taobao'")
    db_reviews = c.fetchone()[0]
    conn.close()

    print(f"  数据库商品数: {db_products}")
    print(f"  数据库评价数: {db_reviews}")
    print(f"{'='*60}")

    page.quit()


if __name__ == "__main__":
    main()
