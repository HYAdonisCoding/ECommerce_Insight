#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
京东电火灶商品数据爬虫 V2
通过百度/分类页获取的商品ID，直接调用京东评价API获取数据
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
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(OUTPUT_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# 通过WebFetch从京东分类页获取的电火灶相关商品ID
JD_PRODUCT_IDS = [
    # 电火灶/电焰灶 专门商品
    "10209470415667",   # 华火电火灶新款3000W电燃灶电焰灶
    "10204701688923",   # 星焰电火电焰灶不用燃煤气料3000W
    "10133878654696",   # 星焰电火灶纯电明火灶
    "10209453821199",   # 华火新能源u7升级款电火焰灶
]

# 更多可能的电火灶商品ID（从百度搜索结果提取）
# 会动态补充

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.jd.com/",
})


def sleep_random(min_s=0.5, max_s=1.5):
    time.sleep(random.uniform(min_s, max_s))


def get_product_info(product_id):
    """从京东商品页面获取商品基本信息"""
    url = f"https://item.jd.com/{product_id}.html"
    info = {"product_id": product_id}

    try:
        resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            print(f"    商品页状态码: {resp.status_code}")
            return info

        html = resp.text
        soup = BeautifulSoup(html, "lxml")

        # 商品标题
        title_tag = soup.select_one("div.sku-name") or soup.select_one("div.itemInfo-wrap .sku-name")
        if title_tag:
            info["title"] = title_tag.get_text(strip=True)
        else:
            # 尝试从title标签获取
            title_tag2 = soup.select_one("title")
            if title_tag2:
                info["title"] = title_tag2.get_text(strip=True).replace("-京东", "").strip()

        # 价格 - 从页面脚本中提取
        price_match = re.search(r'"p":\s*"([\d.]+)"', html)
        if price_match:
            info["price"] = price_match.group(1)
        else:
            price_match2 = re.search(r'价格[：:]\s*¥?([\d.]+)', html)
            if price_match2:
                info["price"] = price_match2.group(1)

        # 店铺名
        shop_tag = soup.select_one("div.J-hove-wrap.ETab ul li.name a") or soup.select_one(".shopName")
        if shop_tag:
            info["shop"] = shop_tag.get_text(strip=True)
        else:
            shop_match = re.search(r'"shopName":\s*"(.*?)"', html)
            if shop_match:
                info["shop"] = shop_match.group(1)

        # 自营标识
        if "自营" in html or "JD_self" in html:
            info["is_self_run"] = "是"
        else:
            info["is_self_run"] = "否"

        # 品牌
        brand_match = re.search(r'"brand":\s*"(.*?)"', html)
        if brand_match:
            info["brand"] = brand_match.group(1)

        # 从页面中提取更多商品信息
        # 商品参数
        params = {}
        param_tags = soup.select("div.parameter2.p-parameter-list li")
        for p in param_tags:
            text = p.get_text(strip=True)
            if "：" in text:
                k, v = text.split("：", 1)
                params[k.strip()] = v.strip()
        if params:
            info["params"] = params

        print(f"    标题: {info.get('title', 'N/A')[:40]}")
        print(f"    价格: ¥{info.get('price', 'N/A')}")
        print(f"    店铺: {info.get('shop', 'N/A')}")

    except Exception as e:
        print(f"    商品页获取失败: {e}")

    return info


def get_comment_summary(product_id):
    """获取商品评价摘要（好评率、评价数等）"""
    url = f"https://club.jd.com/comment/productCommentSummaries.action?referenceIds={product_id}"

    comment_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": f"https://item.jd.com/{product_id}.html",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }

    try:
        resp = session.get(url, headers=comment_headers, timeout=10)
        if resp.status_code == 200 and len(resp.text) > 10:
            data = resp.json()
            summaries = data.get("CommentsCount", [])
            if summaries:
                s = summaries[0]
                return {
                    "comment_count": s.get("CommentCount", 0),
                    "good_count": s.get("GoodCount", 0),
                    "general_count": s.get("GeneralCount", 0),
                    "poor_count": s.get("PoorCount", 0),
                    "good_rate": s.get("GoodRate", 0),
                    "general_rate": s.get("GeneralRate", 0),
                    "poor_rate": s.get("PoorRate", 0),
                    "show_count": s.get("ShowCount", 0),
                    "video_count": s.get("VideoCount", 0),
                    "after_count": s.get("AfterCount", 0),
                }
            else:
                print(f"    评价摘要为空")
        else:
            print(f"    评价摘要API返回: {resp.status_code} / {resp.text[:50]}")
    except Exception as e:
        print(f"    评价摘要获取失败: {e}")

    return None


def get_product_comments(product_id, max_pages=5):
    """获取商品用户评价内容"""
    comments = []
    comment_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": f"https://item.jd.com/{product_id}.html",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }

    for page in range(0, max_pages):
        url = (f"https://club.jd.com/comment/productPageComments.action?"
               f"productId={product_id}&score=0&sortType=5&page={page}&pageSize=10")

        try:
            resp = session.get(url, headers=comment_headers, timeout=10)
            if resp.status_code == 200 and len(resp.text) > 10:
                data = resp.json()
                item_comments = data.get("comments", [])
                if not item_comments:
                    print(f"      第 {page+1} 页无评价")
                    break

                for c in item_comments:
                    after_content = ""
                    if c.get("afterUserComment"):
                        after_content = (c["afterUserComment"].get("content", "") or "").strip()

                    comments.append({
                        "product_id": product_id,
                        "platform": "京东",
                        "comment_id": c.get("id", ""),
                        "content": c.get("content", "").strip(),
                        "score": c.get("score", 0),
                        "nickname": c.get("nickname", ""),
                        "user_level": c.get("userImage", "").replace("user_", "").replace(".png", ""),
                        "creation_time": c.get("creationTime", ""),
                        "reference_time": c.get("referenceTime", ""),
                        "images_count": len(c.get("images", [])),
                        "videos_count": len(c.get("videos", [])),
                        "after_comment": after_content,
                        "product_color": c.get("productColor", ""),
                        "product_size": c.get("productSize", ""),
                        "is_mobile": c.get("isMobile", False),
                        "days": c.get("days", 0),
                    })

                print(f"      第 {page+1} 页: {len(item_comments)} 条评价")
                sleep_random(0.5, 1)
            else:
                print(f"      第 {page+1} 页: {resp.status_code} / {resp.text[:30]}")
                break
        except Exception as e:
            print(f"      评价获取出错: {e}")
            break

    return comments


def get_comments_by_score(product_id, score, max_pages=3):
    """获取指定评分的评价 (1=差评, 2=中评, 3=好评, 5=晒图)"""
    comments = []
    comment_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": f"https://item.jd.com/{product_id}.html",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }

    for page in range(0, max_pages):
        url = (f"https://club.jd.com/comment/productPageComments.action?"
               f"productId={product_id}&score={score}&sortType=5&page={page}&pageSize=10")
        try:
            resp = session.get(url, headers=comment_headers, timeout=10)
            if resp.status_code == 200 and len(resp.text) > 10:
                data = resp.json()
                item_comments = data.get("comments", [])
                if not item_comments:
                    break
                for c in item_comments:
                    after_content = ""
                    if c.get("afterUserComment"):
                        after_content = (c["afterUserComment"].get("content", "") or "").strip()
                    comments.append({
                        "product_id": product_id,
                        "platform": "京东",
                        "content": c.get("content", "").strip(),
                        "score": c.get("score", 0),
                        "nickname": c.get("nickname", ""),
                        "creation_time": c.get("creationTime", ""),
                        "after_comment": after_content,
                        "product_color": c.get("productColor", ""),
                        "product_size": c.get("productSize", ""),
                        "images_count": len(c.get("images", [])),
                    })
                sleep_random(0.5, 1)
            else:
                break
        except:
            break

    return comments


def run_jd_scraper_v2():
    """主流程"""
    print("=" * 60)
    print(f"京东电火灶爬虫V2 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"目标商品ID: {JD_PRODUCT_IDS}")
    print("=" * 60)

    all_products = []
    all_comments = []
    all_bad_comments = []  # 差评
    all_good_comments = []  # 好评

    for i, pid in enumerate(JD_PRODUCT_IDS):
        print(f"\n[{i+1}/{len(JD_PRODUCT_IDS)}] 处理商品 {pid}")
        print("-" * 40)

        # 1. 获取商品信息
        print("  [1] 获取商品信息...")
        product = get_product_info(pid)
        product["platform"] = "京东"
        product["product_id"] = pid
        product["url"] = f"https://item.jd.com/{pid}.html"

        sleep_random(1, 2)

        # 2. 获取评价摘要
        print("  [2] 获取评价摘要...")
        summary = get_comment_summary(pid)
        if summary:
            product.update(summary)
            print(f"    总评价: {summary['comment_count']}")
            print(f"    好评率: {summary['good_rate']}%")
            print(f"    中评率: {summary['general_rate']}%")
            print(f"    差评率: {summary['poor_rate']}%")
        else:
            product.update({
                "comment_count": 0, "good_count": 0, "general_count": 0,
                "poor_count": 0, "good_rate": 0, "general_rate": 0,
                "poor_rate": 0, "show_count": 0, "video_count": 0, "after_count": 0,
            })

        all_products.append(product)

        sleep_random(1, 2)

        # 3. 获取评价内容（全部评价）
        print("  [3] 获取用户评价...")
        comments = get_product_comments(pid, max_pages=5)
        all_comments.extend(comments)
        print(f"    获取评价: {len(comments)} 条")

        sleep_random(1, 2)

        # 4. 获取差评（重点关注用户体验问题）
        if summary and summary.get("poor_count", 0) > 0:
            print("  [4] 获取差评（关注用户体验）...")
            bad_comments = get_comments_by_score(pid, 1, max_pages=3)
            all_bad_comments.extend(bad_comments)
            print(f"    差评: {len(bad_comments)} 条")

            sleep_random(1, 2)

        # 5. 获取好评（用于对比）
        if summary and summary.get("good_count", 0) > 0:
            print("  [5] 获取好评...")
            good_comments = get_comments_by_score(pid, 3, max_pages=2)
            all_good_comments.extend(good_comments)
            print(f"    好评: {len(good_comments)} 条")

            sleep_random(1, 2)

    # 保存数据
    print("\n" + "=" * 60)
    print("保存数据...")

    products_file = os.path.join(DATA_DIR, "jd_products.json")
    with open(products_file, "w", encoding="utf-8") as f:
        json.dump(all_products, f, ensure_ascii=False, indent=2)
    print(f"  商品数据: {products_file} ({len(all_products)} 个)")

    comments_file = os.path.join(DATA_DIR, "jd_comments.json")
    with open(comments_file, "w", encoding="utf-8") as f:
        json.dump(all_comments, f, ensure_ascii=False, indent=2)
    print(f"  全部评价: {comments_file} ({len(all_comments)} 条)")

    bad_file = os.path.join(DATA_DIR, "jd_bad_comments.json")
    with open(bad_file, "w", encoding="utf-8") as f:
        json.dump(all_bad_comments, f, ensure_ascii=False, indent=2)
    print(f"  差评数据: {bad_file} ({len(all_bad_comments)} 条)")

    good_file = os.path.join(DATA_DIR, "jd_good_comments.json")
    with open(good_file, "w", encoding="utf-8") as f:
        json.dump(all_good_comments, f, ensure_ascii=False, indent=2)
    print(f"  好评数据: {good_file} ({len(all_good_comments)} 条)")

    print(f"\n爬虫完成！")
    print(f"  商品: {len(all_products)} 个")
    print(f"  评价: {len(all_comments)} 条 (全部)")
    print(f"  差评: {len(all_bad_comments)} 条")
    print(f"  好评: {len(all_good_comments)} 条")

    return all_products, all_comments, all_bad_comments, all_good_comments


if __name__ == "__main__":
    run_jd_scraper_v2()
