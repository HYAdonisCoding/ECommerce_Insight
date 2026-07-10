#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
京东电火灶数据爬虫
爬取商品搜索结果 + 评价摘要 + 用户评价内容
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

# 模拟浏览器请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.jd.com/",
}

COMMENT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://item.jd.com/",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

session = requests.Session()
session.headers.update(HEADERS)


def sleep_random(min_s=0.5, max_s=1.5):
    """随机休眠，避免请求过于频繁"""
    time.sleep(random.uniform(min_s, max_s))


def search_jd_products(keyword, max_pages=5):
    """搜索京东商品列表"""
    products = []
    for page in range(1, max_pages + 1):
        url = f"https://search.jd.com/Search?keyword={keyword}&enc=utf-8&page={page}"
        print(f"  [JD搜索] 第 {page} 页: {url}")
        try:
            resp = session.get(url, timeout=15)
            resp.encoding = "utf-8"
            if resp.status_code != 200:
                print(f"    状态码: {resp.status_code}, 跳过")
                continue

            soup = BeautifulSoup(resp.text, "lxml")
            items = soup.select("li.gl-item")

            if not items:
                # 尝试备用选择器
                items = soup.select("[data-sku]")
                print(f"    备用选择器找到 {len(items)} 个商品")

            for item in items:
                try:
                    # 商品ID
                    sku = item.get("data-sku") or ""
                    if not sku:
                        sku_tag = item.select_one("[data-sku]")
                        if sku_tag:
                            sku = sku_tag.get("data-sku", "")

                    # 标题
                    title_tag = item.select_one("div.p-name a em") or item.select_one(".p-name em")
                    title = title_tag.get_text(strip=True) if title_tag else ""

                    # 链接
                    link_tag = item.select_one("div.p-name a")
                    link = link_tag.get("href", "") if link_tag else ""
                    if link and not link.startswith("http"):
                        link = "https:" + link

                    # 价格
                    price_tag = item.select_one("div.p-price strong i") or item.select_one(".p-price i")
                    price = price_tag.get_text(strip=True) if price_tag else ""

                    # 店铺名
                    shop_tag = item.select_one("div.p-shop a") or item.select_one(".p-shop a")
                    shop = shop_tag.get_text(strip=True) if shop_tag else ""

                    # 评论数（搜索页显示的）
                    commit_tag = item.select_one("div.p-commit strong a")
                    commit_text = commit_tag.get_text(strip=True) if commit_tag else ""

                    # 自营标识
                    self_tag = item.select_one("div.p-icons i.goods-icons-JD")
                    is_self = "是" if self_tag else "否"

                    if sku and title:
                        products.append({
                            "platform": "京东",
                            "product_id": sku,
                            "title": title,
                            "price": price,
                            "shop": shop,
                            "is_self_run": is_self,
                            "commit_count_text": commit_text,
                            "url": link,
                            "page": page,
                        })
                except Exception as e:
                    print(f"    解析商品出错: {e}")
                    continue

            print(f"    找到 {len(items)} 个商品，累计 {len(products)} 个")
            sleep_random(1, 2)

        except Exception as e:
            print(f"    请求出错: {e}")
            continue

    return products


def get_comment_summary(product_id):
    """获取商品评价摘要（好评率、评价数等）"""
    url = f"https://club.jd.com/comment/productCommentSummaries.action?referenceIds={product_id}"
    try:
        resp = session.get(url, headers=COMMENT_HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            summaries = data.get("CommentsCount", [])
            if summaries and len(summaries) > 0:
                s = summaries[0]
                return {
                    "comment_count": s.get("CommentCount", 0),          # 总评价数
                    "good_count": s.get("GoodCount", 0),                # 好评数
                    "general_count": s.get("GeneralCount", 0),          # 中评数
                    "poor_count": s.get("PoorCount", 0),                # 差评数
                    "good_rate": s.get("GoodRate", 0),                  # 好评率
                    "general_rate": s.get("GeneralRate", 0),            # 中评率
                    "poor_rate": s.get("PoorRate", 0),                  # 差评率
                    "show_count": s.get("ShowCount", 0),               # 晒图数
                    "video_count": s.get("VideoCount", 0),             # 视频评价数
                    "after_count": s.get("AfterCount", 0),             # 追评数
                }
    except Exception as e:
        print(f"    评价摘要获取失败 [{product_id}]: {e}")
    return None


def get_product_comments(product_id, max_pages=3):
    """获取商品用户评价内容"""
    comments = []
    for page in range(0, max_pages):
        url = (f"https://club.jd.com/comment/productPageComments.action?"
               f"productId={product_id}&score=0&sortType=5&page={page}&pageSize=10")
        try:
            resp = session.get(url, headers=COMMENT_HEADERS, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                item_comments = data.get("comments", [])
                if not item_comments:
                    break
                for c in item_comments:
                    comments.append({
                        "product_id": product_id,
                        "platform": "京东",
                        "comment_id": c.get("id", ""),
                        "content": c.get("content", "").strip(),
                        "score": c.get("score", 0),                    # 1-5星
                        "nickname": c.get("nickname", ""),
                        "creation_time": c.get("creationTime", ""),
                        "reference_time": c.get("referenceTime", ""),
                        "images_count": len(c.get("images", [])),
                        "videos_count": len(c.get("videos", [])),
                        "after_comment": (c.get("afterUserComment") or {}).get("content", "").strip() if c.get("afterUserComment") else "",
                        "product_color": c.get("productColor", ""),
                        "product_size": c.get("productSize", ""),
                    })
                print(f"      评价第 {page+1} 页: {len(item_comments)} 条")
                sleep_random(0.5, 1)
            else:
                break
        except Exception as e:
            print(f"      评价获取出错 [{product_id}]: {e}")
            break
    return comments


def run_jd_scraper():
    """主流程：搜索 -> 评价摘要 -> 评价内容"""
    print("=" * 60)
    print(f"京东电火灶爬虫启动 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 搜索商品
    print("\n[步骤1] 搜索京东商品...")
    products = search_jd_products(KEYWORD, max_pages=5)
    print(f"\n共找到 {len(products)} 个商品")

    if not products:
        print("未找到商品，尝试备用方案...")
        return None, None

    # 2. 获取评价摘要
    print("\n[步骤2] 获取评价摘要（好评率/差评率等）...")
    for i, p in enumerate(products):
        print(f"  [{i+1}/{len(products)}] {p['title'][:30]}... (SKU: {p['product_id']})")
        summary = get_comment_summary(p["product_id"])
        if summary:
            p.update(summary)
        else:
            p.update({
                "comment_count": 0, "good_count": 0, "general_count": 0,
                "poor_count": 0, "good_rate": 0, "general_rate": 0,
                "poor_rate": 0, "show_count": 0, "video_count": 0, "after_count": 0,
            })
        sleep_random(0.5, 1)

    # 3. 获取评价内容（取前20个有评价的商品）
    print("\n[步骤3] 获取用户评价内容（取前20个商品）...")
    all_comments = []
    products_with_comments = [p for p in products if p.get("comment_count", 0) > 0][:20]
    for i, p in enumerate(products_with_comments):
        print(f"  [{i+1}/{len(products_with_comments)}] {p['title'][:30]}... (评价数: {p.get('comment_count', 0)})")
        comments = get_product_comments(p["product_id"], max_pages=3)
        all_comments.extend(comments)
        sleep_random(1, 2)

    # 4. 保存数据
    print("\n[步骤4] 保存数据...")
    products_file = os.path.join(DATA_DIR, "jd_products.json")
    comments_file = os.path.join(DATA_DIR, "jd_comments.json")

    with open(products_file, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    print(f"  商品数据: {products_file} ({len(products)} 条)")

    with open(comments_file, "w", encoding="utf-8") as f:
        json.dump(all_comments, f, ensure_ascii=False, indent=2)
    print(f"  评价数据: {comments_file} ({len(all_comments)} 条)")

    print(f"\n京东爬虫完成！商品 {len(products)} 个，评价 {len(all_comments)} 条")
    return products, all_comments


if __name__ == "__main__":
    run_jd_scraper()
