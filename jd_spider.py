#!/usr/bin/env python3
"""
京东电火灶爬虫 - DrissionPage浏览器模式
采集: 商品列表(多关键词多页) + 评价摘要 + 评价详情
写入: SQLite数据库
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

# 搜索关键词
KEYWORDS = [
    "电火灶",
    "电焰灶",
    "电燃灶",
    "电火灶 家用",
    "电火灶 商用",
    "电焰灶 双灶",
    "华火电火灶",
    "星焰电火灶",
]

MAX_PAGES = 3  # 每个关键词最多爬3页


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_browser():
    """初始化浏览器"""
    co = ChromiumOptions()
    co.set_browser_path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    co.set_argument("--no-first-run")
    co.set_argument("--no-default-browser-check")
    co.set_argument("--disable-blink-features=AutomationControlled")
    co.set_argument("--window-size=1920,1080")
    co.set_argument("--disable-gpu")
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-dev-shm-usage")
    co.auto_port()  # 自动分配端口, 避免冲突
    page = ChromiumPage(co)
    return page


def search_jd(page, keyword, page_num):
    """搜索京东商品, 返回商品列表"""
    url = f"https://search.jd.com/Search?keyword={keyword}&enc=utf-8&page={2*page_num - 1}"
    print(f"  访问: {url}")
    page.get(url)
    time.sleep(2)

    # 滚动页面加载懒加载内容
    for _ in range(3):
        page.scroll.to_bottom()
        time.sleep(0.5)
    page.scroll.to_top()
    time.sleep(0.5)

    # 获取页面HTML
    html = page.html

    # 解析商品 - 京东搜索页商品在 <li class="gl-item" data-sku="xxx">
    products = []

    # 方法1: 用DrissionPage的ele找元素
    items = page.eles("css:li.gl-item")
    if not items:
        # 备用: 尝试其他选择器
        items = page.eles("css:div.gl-i-wrap")
    if not items:
        # 再备用: 从HTML正则提取
        skus = re.findall(r'data-sku="(\d+)"', html)
        print(f"  DOM元素未找到, HTML中data-sku数量: {len(skus)}")
        for sku in skus:
            products.append({"product_id": sku, "source": "regex"})
        # 记录搜索日志
        log_search(keyword, "jd", page_num, len(products))
        return products

    print(f"  找到 {len(items)} 个商品元素")

    for item in items:
        try:
            product = {}

            # 商品ID
            sku = item.attr("data-sku") or item.attr("data-pid") or ""
            if not sku:
                # 从内部链接提取
                link_el = item.ele("css:.p-name a", timeout=1)
                if link_el:
                    href = link_el.attr("href") or ""
                    m = re.search(r"item\.jd\.com/(\d+)", href)
                    if m:
                        sku = m.group(1)
            if not sku:
                continue
            product["product_id"] = sku

            # 标题
            title_el = item.ele("css:.p-name em", timeout=1) or item.ele("css:.p-name a", timeout=1)
            product["title"] = title_el.text.strip() if title_el else ""

            # 价格
            price_el = item.ele("css:.p-price i", timeout=1) or item.ele("css:.p-price strong i", timeout=1)
            price_str = price_el.text.strip() if price_el else "0"
            try:
                product["price"] = float(price_str)
            except ValueError:
                product["price"] = 0.0

            # 原价
            orig_el = item.ele("css:.p-price del", timeout=1)
            if orig_el:
                try:
                    product["original_price"] = float(orig_el.text.strip())
                except ValueError:
                    pass

            # 店铺
            shop_el = item.ele("css:.p-shop a", timeout=1) or item.ele("css:.p-shop", timeout=1)
            product["shop_name"] = shop_el.text.strip() if shop_el else ""

            # 评价数
            commit_el = item.ele("css:.p-commit a", timeout=1) or item.ele("css:.p-commit strong a", timeout=1)
            commit_text = commit_el.text.strip() if commit_el else "0"
            product["review_count_text"] = commit_text
            product["review_count"] = parse_count(commit_text)

            # 图片
            img_el = item.ele("css:.p-img img", timeout=1)
            if img_el:
                product["image_url"] = img_el.attr("data-lazy-img") or img_el.attr("src") or ""

            product["url"] = f"https://item.jd.com/{sku}.html"
            product["search_keyword"] = keyword
            products.append(product)

        except Exception as e:
            continue

    # 记录搜索日志
    log_search(keyword, "jd", page_num, len(products))
    return products


def parse_count(text):
    """解析"1.2万+评价"这种文本为数字"""
    if not text:
        return 0
    text = text.replace("+", "").replace("评价", "").replace("评论", "").strip()
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


def save_product(product, platform="jd"):
    """保存商品到数据库"""
    conn = get_db()
    conn.execute("""
        INSERT OR REPLACE INTO products
        (platform, product_id, title, price, original_price, shop_name, url,
         review_count, image_url, search_keyword)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (
        platform,
        product.get("product_id", ""),
        product.get("title", ""),
        product.get("price", 0),
        product.get("original_price"),
        product.get("shop_name", ""),
        product.get("url", ""),
        product.get("review_count", 0),
        product.get("image_url", ""),
        product.get("search_keyword", ""),
    ))
    conn.commit()
    conn.close()


def fetch_comment_summary(page, sku):
    """获取商品评价摘要(好评率等)"""
    url = f"https://club.jd.com/comment/productCommentSummaries.action?referenceIds={sku}"
    try:
        page.get(url)
        time.sleep(0.5)
        text = page.html
        # 从HTML中提取JSON
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            comments_info = data.get("CommentsCount", [])
            if comments_info:
                info = comments_info[0]
                return {
                    "review_count": info.get("CommentCount", 0),
                    "good_count": info.get("GoodCount", 0),
                    "neutral_count": info.get("GeneralCount", 0),
                    "poor_count": info.get("PoorCount", 0),
                    "good_rate": info.get("GoodRate", 0),
                    "neutral_rate": info.get("GeneralRate", 0),
                    "poor_rate": info.get("PoorRate", 0),
                    "show_count": info.get("ShowCount", 0),
                }
    except Exception as e:
        print(f"    评价摘要获取失败 {sku}: {e}")
    return None


def fetch_comments(page, sku, max_pages=5):
    """获取商品评价详情"""
    all_comments = []
    for p in range(max_pages):
        url = (f"https://club.jd.com/comment/productPageComments.action?"
               f"productId={sku}&score=0&sortType=5&page={p}&pageSize=10")
        try:
            page.get(url)
            time.sleep(0.5)
            text = page.html
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                comments = data.get("comments", [])
                if not comments:
                    break
                for c in comments:
                    comment = {
                        "review_id": str(c.get("id", "")),
                        "rating": c.get("score", 0),
                        "content": c.get("content", ""),
                        "author": c.get("nickname", ""),
                        "date": c.get("creationTime", ""),
                        "variant": c.get("productColor", "") + " " + c.get("productSize", ""),
                        "has_image": 1 if c.get("images") else 0,
                        "has_video": 1 if c.get("videos") else 0,
                        "is_append": 1 if c.get("afterUserComment") else 0,
                        "useful_count": c.get("usefulVoteCount", 0),
                    }
                    all_comments.append(comment)
                print(f"      第{p+1}页: {len(comments)}条评价")
            else:
                break
        except Exception as e:
            print(f"      评价获取失败(第{p+1}页): {e}")
            break
        time.sleep(random.uniform(0.5, 1.5))
    return all_comments


def fetch_product_detail(page, sku):
    """从商品详情页获取更多信息(品牌等)"""
    url = f"https://item.jd.com/{sku}.html"
    try:
        page.get(url)
        time.sleep(1.5)

        detail = {}

        # 品牌 - 从面包屑导航获取
        brand_el = page.ele("css:#crumb-wrap .ellipsis a", timeout=2)
        if brand_el:
            detail["brand"] = brand_el.text.strip()

        # 标题
        title_el = page.ele("css:.sku-name", timeout=2)
        if title_el:
            detail["title"] = title_el.text.strip()

        # 价格
        price_el = page.ele("css:.price J-p-{} .price".format(sku), timeout=1)
        if not price_el:
            price_el = page.ele("css:.summary-price .price", timeout=1)
        if price_el:
            try:
                detail["price"] = float(re.search(r'[\d.]+', price_el.text).group())
            except (AttributeError, ValueError):
                pass

        # 店铺
        shop_el = page.ele("css:.J-hove-wrap .item a", timeout=1) or page.ele("css:.popstore-name a", timeout=1)
        if shop_el:
            detail["shop_name"] = shop_el.text.strip()

        return detail
    except Exception as e:
        print(f"    详情页获取失败: {e}")
        return {}


def update_product_stats(sku, stats):
    """更新商品评价统计"""
    conn = get_db()
    conn.execute("""
        UPDATE products SET
            review_count = ?,
            good_count = ?,
            neutral_count = ?,
            poor_count = ?,
            good_rate = ?,
            neutral_rate = ?,
            poor_rate = ?
        WHERE platform = 'jd' AND product_id = ?
    """, (
        stats["review_count"],
        stats["good_count"],
        stats["neutral_count"],
        stats["poor_count"],
        stats["good_rate"],
        stats["neutral_rate"],
        stats["poor_rate"],
        sku,
    ))
    conn.commit()
    conn.close()


def save_comments(sku, comments, platform="jd"):
    """保存评价到数据库"""
    conn = get_db()
    for c in comments:
        # 判断情感
        sentiment = "neutral"
        if c["rating"] >= 4:
            sentiment = "positive"
        elif c["rating"] <= 2:
            sentiment = "negative"

        conn.execute("""
            INSERT OR IGNORE INTO reviews
            (platform, product_id, review_id, rating, content, author, date,
             variant, has_image, has_video, is_append, useful_count, sentiment)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            platform, sku, c["review_id"], c["rating"], c["content"],
            c["author"], c["date"], c["variant"].strip(),
            c["has_image"], c["has_video"], c["is_append"], c["useful_count"],
            sentiment,
        ))
    conn.commit()
    conn.close()


def update_product_detail(sku, detail):
    """更新商品详情(品牌等)"""
    conn = get_db()
    fields = []
    values = []
    for k in ["brand", "title", "price", "shop_name"]:
        if k in detail and detail[k]:
            fields.append(f"{k} = ?")
            values.append(detail[k])
    if fields:
        values.append(sku)
        conn.execute(f"""
            UPDATE products SET {', '.join(fields)}
            WHERE platform = 'jd' AND product_id = ?
        """, values)
        conn.commit()
    conn.close()


def main():
    print("=" * 60)
    print("京东电火灶爬虫启动 (DrissionPage)")
    print("=" * 60)

    # 初始化数据库
    os.system(f'"{"/Users/adam/envs/py_arm64/bin/python"}" "{os.path.join(BASE_DIR, "db_init.py")}"')

    # 启动浏览器
    print("\n[1] 启动浏览器...")
    page = init_browser()

    # 先访问京东首页获取cookie
    print("[2] 访问京东首页...")
    page.get("https://www.jd.com/")
    time.sleep(2)

    total_products = 0
    total_reviews = 0

    for keyword in KEYWORDS:
        print(f"\n{'='*40}")
        print(f"搜索关键词: {keyword}")
        print(f"{'='*40}")

        for page_num in range(1, MAX_PAGES + 1):
            print(f"\n  --- 第{page_num}页 ---")
            products = search_jd(page, keyword, page_num)

            if not products:
                print(f"  第{page_num}页无结果, 跳过后续页")
                break

            for idx, product in enumerate(products):
                if not product.get("product_id"):
                    continue

                sku = product["product_id"]
                print(f"\n  [{idx+1}/{len(products)}] SKU={sku}")
                print(f"    标题: {product.get('title', '')[:50]}")

                # 保存商品基础信息
                save_product(product)

                # 获取评价摘要
                print(f"    获取评价摘要...")
                stats = fetch_comment_summary(page, sku)
                if stats:
                    print(f"    评价: {stats['review_count']} | "
                          f"好评率: {stats['good_rate']:.1f}% | "
                          f"差评: {stats['poor_count']}")
                    update_product_stats(sku, stats)
                    total_reviews += stats["review_count"]

                # 获取评价详情(有评价的才爬)
                if stats and stats["review_count"] > 0:
                    print(f"    获取评价详情...")
                    comments = fetch_comments(page, sku, max_pages=3)
                    if comments:
                        print(f"    保存 {len(comments)} 条评价")
                        save_comments(sku, comments)

                # 获取商品详情(品牌等) - 每5个商品获取一次详情, 避免太慢
                if idx % 5 == 0:
                    print(f"    获取商品详情...")
                    detail = fetch_product_detail(page, sku)
                    if detail:
                        update_product_detail(sku, detail)
                        if detail.get("brand"):
                            print(f"    品牌: {detail['brand']}")

                total_products += 1
                time.sleep(random.uniform(1, 2))

            time.sleep(random.uniform(2, 3))

    # 统计
    print(f"\n{'='*60}")
    print(f"京东爬虫完成!")
    print(f"  采集商品: {total_products}")
    print(f"  评价总数: {total_reviews}")

    # 数据库统计
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM products WHERE platform='jd'")
    db_products = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM reviews WHERE platform='jd'")
    db_reviews = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT search_keyword) FROM products WHERE platform='jd'")
    db_keywords = c.fetchone()[0]
    conn.close()

    print(f"  数据库商品数: {db_products}")
    print(f"  数据库评价数: {db_reviews}")
    print(f"  搜索关键词数: {db_keywords}")
    print(f"{'='*60}")

    page.quit()


if __name__ == "__main__":
    main()
