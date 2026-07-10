#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
淘宝H5移动端API爬虫
通过 mtop 接口获取搜索结果，需要计算sign签名
"""

import requests
import re
import json
import time
import random
import hashlib
import os
from datetime import datetime

# ========== 配置 ==========
KEYWORD = "电火灶"
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(OUTPUT_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

APP_KEY = "12574478"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Accept": "application/json",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://h5.m.taobao.com/",
})


def sleep_random(min_s=0.5, max_s=1.5):
    time.sleep(random.uniform(min_s, max_s))


def get_h5_token():
    """获取淘宝H5 API的 _m_h5_tk token"""
    # 访问H5页面获取cookie
    url = "https://h5api.m.taobao.com/h5/mtop.taobao.wsearch.appsearch/1.0/?jsv=2.6.1&appKey={}&t={}&sign=test&api=mtop.taobao.wsearch.appsearch&v=1.0&type=originaljson&dataType=json".format(
        APP_KEY, int(time.time() * 1000)
    )
    try:
        resp = session.get(url, timeout=15)
        cookies = session.cookies.get_dict()
        token_cookie = cookies.get("_m_h5_tk", "")
        if token_cookie:
            token = token_cookie.split("_")[0]
            print(f"  获取H5 token: {token[:16]}...")
            return token
        else:
            print(f"  未获取到token, cookies: {list(cookies.keys())}")
            # 尝试从响应头获取
            set_cookie = resp.headers.get("Set-Cookie", "")
            if "_m_h5_tk" in set_cookie:
                token_match = re.search(r'_m_h5_tk=([a-f0-9]+)', set_cookie)
                if token_match:
                    token = token_match.group(1)
                    print(f"  从响应头获取token: {token[:16]}...")
                    return token
    except Exception as e:
        print(f"  获取token失败: {e}")
    return None


def calc_sign(token, t, data_str):
    """计算淘宝H5 API签名: md5(token & t & appKey & data)"""
    sign_str = f"{token}&{t}&{APP_KEY}&{data_str}"
    sign = hashlib.md5(sign_str.encode("utf-8")).hexdigest()
    return sign


def search_taobao_h5(keyword, page=1, token=None):
    """通过淘宝H5 API搜索商品"""
    t = str(int(time.time() * 1000))
    data = json.dumps({
        "keyword": keyword,
        "fromFilter": False,
        "isNewUserArea": True,
        "extraFilterData": "{\"customFilter\":{}}",
        "page": page,
    }, separators=(",", ":"), ensure_ascii=False)

    sign = calc_sign(token, t, data) if token else "test"

    params = {
        "jsv": "2.6.1",
        "appKey": APP_KEY,
        "t": t,
        "sign": sign,
        "api": "mtop.taobao.wsearch.appsearch",
        "v": "1.0",
        "type": "originaljson",
        "dataType": "json",
        "data": data,
    }

    url = "https://h5api.m.taobao.com/h5/mtop.taobao.wsearch.appsearch/1.0/"
    try:
        resp = session.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            result = resp.json()
            return result
        else:
            print(f"    HTTP {resp.status_code}")
    except Exception as e:
        print(f"    搜索出错: {e}")
    return None


def search_taobao_pc_h5(keyword, page=1):
    """通过淘宝PC搜索页的API获取数据（备用方案）"""
    t = str(int(time.time() * 1000))
    data_str = json.dumps({
        "keyword": keyword,
        "page": page,
        "sort": "_sale",
        "pageSize": 44,
    }, separators=(",", ":"), ensure_ascii=False)

    # 先获取token
    token_url = f"https://h5api.m.taobao.com/h5/mtop.taobao.pcdetail.data.search/1.0/?jsv=2.6.1&appKey={APP_KEY}&t={t}&sign=test&api=mtop.taobao.pcdetail.data.search&v=1.0&type=originaljson&dataType=json"
    try:
        resp = session.get(token_url, timeout=15)
        cookies = session.cookies.get_dict()
        token_cookie = cookies.get("_m_h5_tk", "")
        token = token_cookie.split("_")[0] if token_cookie else ""
    except:
        token = ""

    if not token:
        return None

    sign = calc_sign(token, t, data_str)
    params = {
        "jsv": "2.6.1",
        "appKey": APP_KEY,
        "t": t,
        "sign": sign,
        "api": "mtop.taobao.pcdetail.data.search",
        "v": "1.0",
        "type": "originaljson",
        "dataType": "json",
        "data": data_str,
    }

    url = f"https://h5api.m.taobao.com/h5/mtop.taobao.pcdetail.data.search/1.0/"
    try:
        resp = session.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"    PC搜索出错: {e}")
    return None


def search_via_suggest_and_detail(keyword):
    """通过搜索建议获取相关关键词，然后搜索商品"""
    print("  通过搜索建议获取相关关键词...")
    suggest_url = f"https://suggest.taobao.com/sug?code=utf-8&q={keyword}"
    try:
        resp = session.get(suggest_url, timeout=10)
        if resp.status_code == 200:
            suggest_data = resp.json()
            suggestions = [item[0] for item in suggest_data.get("result", [])]
            print(f"  建议关键词: {suggestions}")
            return suggestions
    except Exception as e:
        print(f"  搜索建议失败: {e}")
    return []


def get_taobao_item_detail(item_id):
    """获取淘宝商品详情和评价信息"""
    t = str(int(time.time() * 1000))
    data_str = json.dumps({"id": str(item_id)}, separators=(",", ":"))

    # 获取token
    token_url = f"https://h5api.m.taobao.com/h5/mtop.taobao.detail.getdetail/1.0/?jsv=2.6.1&appKey={APP_KEY}&t={t}&sign=test&api=mtop.taobao.detail.getdetail&v=1.0&type=originaljson&dataType=json"
    try:
        resp = session.get(token_url, timeout=15)
        cookies = session.cookies.get_dict()
        token_cookie = cookies.get("_m_h5_tk", "")
        token = token_cookie.split("_")[0] if token_cookie else ""
    except:
        token = ""

    if not token:
        return None

    sign = calc_sign(token, t, data_str)
    params = {
        "jsv": "2.6.1",
        "appKey": APP_KEY,
        "t": t,
        "sign": sign,
        "api": "mtop.taobao.detail.getdetail",
        "v": "1.0",
        "type": "originaljson",
        "dataType": "json",
        "data": data_str,
    }

    url = f"https://h5api.m.taobao.com/h5/mtop.taobao.detail.getdetail/1.0/"
    try:
        resp = session.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"    商品详情出错: {e}")
    return None


def run_taobao_h5_scraper():
    """主流程"""
    print("=" * 60)
    print(f"淘宝H5 API电火灶爬虫 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Step 1: 获取token
    print("\n[Step 1] 获取H5 Token...")
    token = get_h5_token()
    if not token:
        print("  Token获取失败，尝试不使用token搜索...")
        token = ""

    sleep_random(1, 2)

    # Step 2: 搜索商品
    all_products = []
    for page in range(1, 4):
        print(f"\n[Step 2.{page}] 搜索第 {page} 页...")
        result = search_taobao_h5(KEYWORD, page=page, token=token)
        if result:
            ret = result.get("ret", [])
            if ret and "SUCCESS" in str(ret):
                data = result.get("data", {})
                # 解析搜索结果
                items = data.get("listItem", data.get("itemsArray", data.get("items", [])))
                if isinstance(items, dict):
                    items = list(items.values())
                print(f"  找到 {len(items)} 个商品")

                for item in items:
                    parsed = {
                        "platform": "淘宝",
                        "product_id": item.get("nid", item.get("item_id", item.get("id", ""))),
                        "title": item.get("title", item.get("raw_title", "")),
                        "price": item.get("price", item.get("priceShow", item.get("view_price", ""))),
                        "sales_text": item.get("sold", item.get("sales", item.get("view_sales", ""))),
                        "shop": item.get("nick", item.get("sellerNick", item.get("shop_name", ""))),
                        "url": item.get("url", item.get("click_url", f"https://item.taobao.com/item.htm?id={item.get('nid', item.get('item_id', ''))}")),
                        "pic_url": item.get("pic_url", item.get("img", "")),
                        "item_loc": item.get("item_loc", item.get("area", "")),
                        "is_tmall": "是" if item.get("isTmall", item.get("shopcard", False)) else "否",
                        "page": page,
                    }
                    if parsed["title"] and parsed["product_id"]:
                        all_products.append(parsed)
            else:
                print(f"  API返回: {ret}")
                # 如果是token失效，重新获取
                if "FAIL_SYS_TOKEN" in str(ret) or "ILLEGAL_REQUEST" in str(ret):
                    print("  Token失效，重新获取...")
                    token = get_h5_token()
                    if token:
                        result = search_taobao_h5(KEYWORD, page=page, token=token)
                        if result:
                            data = result.get("data", {})
                            items = data.get("listItem", data.get("itemsArray", []))
                            if isinstance(items, dict):
                                items = list(items.values())
                            print(f"  重试后找到 {len(items)} 个商品")
                            for item in items:
                                parsed = {
                                    "platform": "淘宝",
                                    "product_id": item.get("nid", item.get("item_id", "")),
                                    "title": item.get("title", item.get("raw_title", "")),
                                    "price": item.get("price", item.get("priceShow", "")),
                                    "sales_text": item.get("sold", item.get("view_sales", "")),
                                    "shop": item.get("nick", item.get("sellerNick", "")),
                                    "url": f"https://item.taobao.com/item.htm?id={item.get('nid', item.get('item_id', ''))}",
                                    "page": page,
                                }
                                if parsed["title"] and parsed["product_id"]:
                                    all_products.append(parsed)
        else:
            print(f"  第 {page} 页无结果")

        sleep_random(1.5, 2.5)

    # 去重
    seen = set()
    unique = []
    for p in all_products:
        pid = str(p.get("product_id", ""))
        if pid and pid not in seen:
            seen.add(pid)
            unique.append(p)

    # 保存
    if unique:
        output_file = os.path.join(DATA_DIR, "taobao_products.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(unique, f, ensure_ascii=False, indent=2)
        print(f"\n淘宝商品数据已保存: {output_file} ({len(unique)} 个商品)")

    print(f"\n淘宝H5爬虫完成！商品 {len(unique)} 个")
    return unique


if __name__ == "__main__":
    run_taobao_h5_scraper()
