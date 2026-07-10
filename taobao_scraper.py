#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
淘宝/天猫电火灶数据爬虫
注意：淘宝有较强反爬机制，需要处理cookie和动态参数
"""

import requests
import re
import json
import time
import random
import os
from bs4 import BeautifulSoup
from datetime import datetime

# ========== 配置 ==========
KEYWORD = "电火灶"
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(OUTPUT_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

session = requests.Session()
session.headers.update(HEADERS)


def sleep_random(min_s=0.5, max_s=1.5):
    time.sleep(random.uniform(min_s, max_s))


def init_taobao_session():
    """初始化淘宝session，获取必要cookie"""
    print("  [初始化] 获取淘宝Cookie...")
    try:
        # 先访问首页获取基础cookie
        resp = session.get("https://www.taobao.com/", timeout=15)
        print(f"    首页状态: {resp.status_code}")
        sleep_random(1, 2)

        # 访问搜索页获取更多cookie
        resp = session.get(f"https://s.taobao.com/search?q={KEYWORD}", timeout=15)
        print(f"    搜索页状态: {resp.status_code}")

        # 检查cookie
        cookies = session.cookies.get_dict()
        print(f"    获取Cookie: {len(cookies)} 个")

        return True
    except Exception as e:
        print(f"    初始化失败: {e}")
        return False


def search_taobao_products(keyword, max_pages=3):
    """搜索淘宝商品"""
    products = []
    for page in range(1, max_pages + 1):
        # 淘宝搜索URL，s=44*(page-1)
        s = 44 * (page - 1)
        url = f"https://s.taobao.com/search?q={keyword}&s={s}&sort=sale-desc"
        print(f"  [淘宝搜索] 第 {page} 页: {url}")

        try:
            resp = session.get(url, timeout=15)
            resp.encoding = "utf-8"

            if resp.status_code != 200:
                print(f"    状态码: {resp.status_code}")
                continue

            html = resp.text

            # 淘宝搜索结果嵌在页面的JSON中，通常在 script 标签里
            # 尝试多种正则匹配方式

            # 方式1: 查找 g_page_config 变量
            match = re.search(r'g_page_config\s*=\s*(\{.*?\});\s*</script>', html, re.DOTALL)
            if match:
                try:
                    page_config = json.loads(match.group(1))
                    auctions = page_config.get("mods", {}).get("itemlist", {}).get("data", {}).get("auctions", [])
                    print(f"    g_page_config 找到 {len(auctions)} 个商品")
                    for a in auctions:
                        products.append(parse_taobao_item(a, page))
                    continue
                except json.JSONDecodeError:
                    print("    g_page_config JSON解析失败")

            # 方式2: 查找 auctions JSON（新版淘宝页面结构）
            matches = re.findall(r'"auctions":\s*(\[.*?\])\s*[,}]', html, re.DOTALL)
            for m in matches:
                try:
                    auctions = json.loads(m)
                    print(f"    auctions数组找到 {len(auctions)} 个商品")
                    for a in auctions:
                        products.append(parse_taobao_item(a, page))
                except json.JSONDecodeError:
                    continue

            # 方式3: 查找内嵌的JSON数据
            # 搜索 "raw_title" 或 "nid" 字段
            items_raw = re.findall(r'"nid":"(\d+)".*?"raw_title":"(.*?)".*?"view_price":"([\d.]+)".*?"view_sales":"(.*?)".*?"nick":"(.*?)"', html)
            if items_raw:
                print(f"    正则匹配找到 {len(items_raw)} 个商品")
                for nid, title, price, sales, nick in items_raw:
                    products.append({
                        "platform": "淘宝",
                        "product_id": nid,
                        "title": title,
                        "price": price,
                        "shop": nick,
                        "sales_text": sales,
                        "url": f"https://item.taobao.com/item.htm?id={nid}",
                        "page": page,
                    })

            # 方式4: 查找itemlist模块
            match2 = re.search(r'"itemlist".*?"auctions":(\[.*?\])', html, re.DOTALL)
            if match2 and not products:
                try:
                    auctions = json.loads(match2.group(1))
                    print(f"    itemlist匹配找到 {len(auctions)} 个商品")
                    for a in auctions:
                        products.append(parse_taobao_item(a, page))
                except:
                    pass

            if not products and page == 1:
                print("    未找到商品数据，可能需要登录或遇到验证码")
                # 保存原始HTML供调试
                debug_file = os.path.join(DATA_DIR, "taobao_debug.html")
                with open(debug_file, "w", encoding="utf-8") as f:
                    f.write(html)
                print(f"    原始HTML已保存到 {debug_file}")

            sleep_random(1.5, 2.5)

        except Exception as e:
            print(f"    请求出错: {e}")
            continue

    return products


def parse_taobao_item(auction, page):
    """解析单个淘宝商品数据"""
    return {
        "platform": "淘宝",
        "product_id": auction.get("nid", auction.get("item_id", "")),
        "title": auction.get("raw_title", auction.get("title", "")),
        "price": auction.get("view_price", auction.get("price", "")),
        "shop": auction.get("nick", auction.get("shop_name", "")),
        "sales_text": auction.get("view_sales", auction.get("month_sales", auction.get("sales", ""))),
        "comment_count": auction.get("comment_count", ""),
        "comment_url": auction.get("comment_url", ""),
        "item_loc": auction.get("item_loc", auction.get("loc", "")),  # 发货地
        "is_tmall": "是" if (auction.get("shopcard", {}) or auction.get("isTmall")) else "否",
        "url": f"https://item.taobao.com/item.htm?id={auction.get('nid', auction.get('item_id', ''))}",
        "page": page,
        "pic_url": auction.get("pic_url", ""),
    }


def search_taobao_h5(keyword, page=1):
    """通过淘宝H5移动端搜索（备用方案）"""
    url = "https://h5api.m.taobao.com/h5/mtop.taobao.pcdetail.data.search/1.0/"
    params = {
        "q": keyword,
        "page": page,
        "sort": "_sale",
    }
    try:
        resp = session.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("data", {}).get("itemsArray", [])
    except Exception as e:
        print(f"    H5搜索出错: {e}")
    return []


def search_tmall_products(keyword, max_pages=3):
    """搜索天猫商品（淘宝子站，反爬略弱）"""
    products = []
    for page in range(1, max_pages + 1):
        url = f"https://list.tmall.com/search_product.htm?q={keyword}&sort=s&style=g&page={page}"
        print(f"  [天猫搜索] 第 {page} 页: {url}")
        try:
            resp = session.get(url, timeout=15)
            resp.encoding = "utf-8"
            if resp.status_code != 200:
                print(f"    状态码: {resp.status_code}")
                continue

            soup = BeautifulSoup(resp.text, "lxml")
            items = soup.select("div.product-iWrap")
            print(f"    找到 {len(items)} 个天猫商品")

            for item in items:
                try:
                    # 标题
                    title_tag = item.select_one("p.productTitle a")
                    title = title_tag.get_text(strip=True) if title_tag else ""
                    link = title_tag.get("href", "") if title_tag else ""
                    if link and not link.startswith("http"):
                        link = "https:" + link

                    # 商品ID
                    nid = ""
                    nid_match = re.search(r'id=(\d+)', link)
                    if nid_match:
                        nid = nid_match.group(1)

                    # 价格
                    price_tag = item.select_one("em.productTitle-emu") or item.select_one(".productPrice em")
                    price = price_tag.get_text(strip=True) if price_tag else ""

                    # 销量
                    sales_tag = item.select_one("span.productTitle-sales") or item.select_one(".productSales")
                    sales = sales_tag.get_text(strip=True) if sales_tag else ""

                    # 店铺
                    shop_tag = item.select_one("a.productShop-name") or item.select_one(".productShop")
                    shop = shop_tag.get_text(strip=True) if shop_tag else ""

                    # 评论数
                    comment_tag = item.select_one("a.productComment")
                    comment_count = comment_tag.get_text(strip=True) if comment_tag else ""

                    if nid and title:
                        products.append({
                            "platform": "天猫",
                            "product_id": nid,
                            "title": title,
                            "price": price,
                            "shop": shop,
                            "sales_text": sales,
                            "comment_count_text": comment_count,
                            "url": link,
                            "page": page,
                        })
                except Exception as e:
                    continue

            sleep_random(1, 2)

        except Exception as e:
            print(f"    天猫请求出错: {e}")
            continue

    return products


def run_taobao_scraper():
    """主流程"""
    print("=" * 60)
    print(f"淘宝/天猫电火灶爬虫启动 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 初始化session
    init_taobao_session()
    sleep_random(1, 2)

    # 搜索淘宝
    print("\n[步骤1] 搜索淘宝商品...")
    products = search_taobao_products(KEYWORD, max_pages=3)
    print(f"\n淘宝搜索找到 {len(products)} 个商品")

    # 如果淘宝搜索失败，尝试天猫
    if not products:
        print("\n[步骤2] 淘宝搜索无结果，尝试天猫...")
        products = search_tmall_products(KEYWORD, max_pages=3)
        print(f"天猫搜索找到 {len(products)} 个商品")

    # 去重
    seen_ids = set()
    unique_products = []
    for p in products:
        pid = p.get("product_id", "")
        if pid and pid not in seen_ids:
            seen_ids.add(pid)
            unique_products.append(p)
    print(f"去重后商品数: {len(unique_products)}")

    # 保存数据
    if unique_products:
        products_file = os.path.join(DATA_DIR, "taobao_products.json")
        with open(products_file, "w", encoding="utf-8") as f:
            json.dump(unique_products, f, ensure_ascii=False, indent=2)
        print(f"\n商品数据已保存: {products_file}")

    print(f"\n淘宝/天猫爬虫完成！商品 {len(unique_products)} 个")
    return unique_products


if __name__ == "__main__":
    run_taobao_scraper()
