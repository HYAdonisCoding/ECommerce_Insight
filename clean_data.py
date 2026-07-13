#!/usr/bin/env python3
"""
数据清洗 - 修复淘宝商品价格和品牌信息
1. 修复价格：2429100 -> 2429, 439931 -> 4399
2. 从sales_text提取评价数和好评率
3. 从标题提取品牌
"""
import sqlite3
import re
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ecommerce.db")

BRANDS = [
    "华火", "星焰", "星煜", "卡曼森", "美的", "荣事达", "先科",
    "德玛仕", "老板", "尚朋堂", "硕高", "国爱", "九电", "燚龙",
    "东洋", "内芙", "富得莱", "微致", "德克士", "志高", "欢度",
    "奥田美太", "西屋", "TINME", "红日", "万和", "半球", "方太",
    "苏泊尔", "九阳", "海尔", "格力", "艾美特", "万喜", "樱花",
    "帅丰", "美大", "森歌", "亿田", "火星人", "富格", "金利",
]


def fix_prices():
    """修复价格：价格和销量数字合并的问题"""
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()

    c.execute("SELECT product_id, price, sales_text FROM products WHERE platform='taobao' AND price > 10000")
    rows = c.fetchall()

    fixed = 0
    for pid, price, sales_text in rows:
        price_str = str(int(price))

        # 尝试从sales_text提取销量数字
        sales_num = 0
        if sales_text:
            m = re.search(r'(\d+)', sales_text.replace('+', ''))
            if m:
                sales_num = int(m.group(1))

        # 如果价格末尾包含销量数字，截取
        if sales_num > 0 and price_str.endswith(str(sales_num)) and len(price_str) > len(str(sales_num)):
            remaining = price_str[:-len(str(sales_num))]
            if remaining:
                real_price = int(remaining)
                if 100 < real_price < 100000:
                    c.execute("UPDATE products SET price=? WHERE product_id=?", (real_price, pid))
                    fixed += 1
        else:
            # 尝试常见价格分割：价格通常在100-10000范围内
            # 2429100 -> 2429 + 100
            # 439931 -> 4399 + 31
            # 48994 -> 489 + 94
            # 15994 -> 1599 + 4
            for split_pos in range(3, len(price_str)):
                left = int(price_str[:split_pos])
                right = int(price_str[split_pos:])
                if 100 < left < 10000 and 0 < right < 100000:
                    c.execute("UPDATE products SET price=? WHERE product_id=?", (left, pid))
                    fixed += 1
                    break

    db.commit()
    print(f"[价格修复] 修复了 {fixed} 个商品的价格")
    db.close()


def parse_sales_text():
    """从sales_text提取评价数"""
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()

    c.execute("SELECT product_id, sales_text FROM products WHERE sales_text IS NOT NULL AND sales_text != '' AND platform='taobao'")
    rows = c.fetchall()

    updated = 0
    for pid, text in rows:
        comment_count = 0
        # "67500+人付款" -> 67500
        m = re.search(r'(\d+)\+?\s*人付款', text)
        if m:
            comment_count = int(m.group(1))
        # "月销100+" -> 100
        elif re.search(r'月销(\d+)', text):
            m = re.search(r'月销(\d+)', text)
            comment_count = int(m.group(1))
        # "已售100+"
        elif re.search(r'已售(\d+)', text):
            m = re.search(r'已售(\d+)', text)
            comment_count = int(m.group(1))

        if comment_count > 0:
            c.execute("UPDATE products SET comment_count=COALESCE(NULLIF(comment_count,0),?) WHERE product_id=?",
                      (comment_count, pid))
            updated += 1

    db.commit()
    print(f"[销量解析] 更新了 {updated} 个商品的评价数")
    db.close()


def fix_brands():
    """从标题提取品牌"""
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()

    c.execute("SELECT product_id, title FROM products WHERE (brand IS NULL OR brand = '') AND title IS NOT NULL")
    rows = c.fetchall()

    updated = 0
    for pid, title in rows:
        for brand in BRANDS:
            if brand in title:
                c.execute("UPDATE products SET brand=? WHERE product_id=?", (brand, pid))
                updated += 1
                break

    db.commit()
    print(f"[品牌提取] 更新了 {updated} 个商品的品牌")
    db.close()


def print_stats():
    """打印最终统计"""
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()

    c.execute("SELECT platform, COUNT(*) FROM products GROUP BY platform")
    print(f"\n商品总数: {c.fetchall()}")
    c.execute("SELECT COUNT(*) FROM products WHERE price > 0 AND price < 10000")
    print(f"价格正常: {c.fetchone()[0]}")
    c.execute("SELECT COUNT(*) FROM products WHERE price >= 10000")
    print(f"价格异常(>=10000): {c.fetchone()[0]}")
    c.execute("SELECT COUNT(*) FROM products WHERE brand IS NOT NULL AND brand != ''")
    print(f"有品牌: {c.fetchone()[0]}")
    c.execute("SELECT COUNT(*) FROM products WHERE comment_count > 0")
    print(f"有评价数: {c.fetchone()[0]}")
    c.execute("SELECT COUNT(*) FROM reviews")
    print(f"评价文本: {c.fetchone()[0]}")
    c.execute("SELECT brand, COUNT(*) as cnt FROM products GROUP BY brand ORDER BY cnt DESC LIMIT 15")
    print("\n品牌TOP15:")
    for r in c.fetchall():
        print(f"  {r[0] or '无品牌'}: {r[1]}")
    c.execute("SELECT platform, MIN(price), MAX(price), AVG(price) FROM products WHERE price > 0 AND price < 10000 GROUP BY platform")
    print("\n价格区间:")
    for r in c.fetchall():
        print(f"  {r[0]}: ¥{r[1]:.0f}-¥{r[2]:.0f} 均价¥{r[3]:.0f}")

    db.close()


if __name__ == "__main__":
    print("=" * 50)
    print("数据清洗")
    print("=" * 50)
    fix_prices()
    parse_sales_text()
    fix_brands()
    print_stats()
