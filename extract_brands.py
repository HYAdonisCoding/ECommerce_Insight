#!/usr/bin/env python3
"""Extract brand names from product titles and shop names, update database"""
import sqlite3
import re
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ecommerce.db")

# Brand mapping: shop_name pattern -> brand
SHOP_BRAND_MAP = [
    (r"华火", "华火"),
    (r"星煜", "星煜"),
    (r"星焰", "星焰"),
    (r"卡曼森", "卡曼森"),
    (r"美的", "美的"),
    (r"荣事达", "荣事达"),
    (r"先科", "先科"),
    (r"德玛仕", "德玛仕"),
    (r"老板", "老板"),
    (r"尚朋堂", "尚朋堂"),
    (r"硕高", "硕高"),
    (r"国爱|GOAI", "国爱"),
    (r"九电|Jiudian", "九电"),
    (r"燚龙|YILONG", "燚龙"),
    (r"东洋|TOYO", "东洋"),
    (r"内芙", "内芙"),
    (r"富得莱", "富得莱"),
    (r"微致", "微致"),
    (r"德克士", "德克士"),
    (r"志高", "志高"),
    (r"欢度", "欢度"),
    (r"奥田美太", "奥田美太"),
    (r"西屋", "西屋"),
    (r"TINME", "TINME"),
    (r"红日|RedSun", "红日"),
    (r"万和", "万和"),
    (r"半球|PESKOE", "半球"),
    (r"方太|FOTILE", "方太"),
]

# Brand keywords that appear at the start of titles
TITLE_BRANDS = [
    "华火", "星焰", "星煜", "卡曼森", "美的", "荣事达", "先科", "德玛仕",
    "老板", "尚朋堂", "硕高", "国爱", "九电", "燚龙", "东洋", "内芙",
    "富得莱", "微致", "德克士", "志高", "欢度", "奥田美太", "西屋", "TINME",
    "GOAI", "YILONG", "Jiudian", "TOYO", "红日", "RedSun", "万和", "半球",
    "PESKOE", "方太", "FOTILE",
]


def extract_brand(title, shop_name):
    """Extract brand from shop_name first, then from title"""
    # Try shop_name first
    if shop_name:
        for pattern, brand in SHOP_BRAND_MAP:
            if re.search(pattern, shop_name):
                return brand

    # Try title - brand usually at the start
    if title:
        for brand in TITLE_BRANDS:
            if title.startswith(brand) or title.startswith(f"【{brand}】"):
                return brand
            # Also check if brand appears early in title
            idx = title.find(brand)
            if 0 <= idx <= 5:
                return brand

    # Try shop_name without 旗舰店 etc.
    if shop_name:
        cleaned = re.sub(r"(京东自营|官方|旗舰|超级|工程|商用|厨电|高端|环境电器|中式厨电|美味厨房|电器|生活电器).*", "", shop_name)
        cleaned = re.sub(r"[（(].*?[)）]", "", cleaned)
        cleaned = cleaned.strip()
        if cleaned and len(cleaned) <= 10:
            return cleaned

    return ""


def main():
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()

    c.execute("SELECT product_id, title, shop_name FROM products")
    rows = c.fetchall()

    updated = 0
    brand_counts = {}

    for pid, title, shop in rows:
        brand = extract_brand(title or "", shop or "")
        if brand:
            c.execute("UPDATE products SET brand=? WHERE product_id=?", (brand, pid))
            updated += 1
            brand_counts[brand] = brand_counts.get(brand, 0) + 1
        else:
            print(f"  [未识别] {pid}: {title[:50] if title else 'N/A'} | shop={shop}")

    db.commit()

    print(f"\n品牌提取完成: {updated}/{len(rows)} 个商品")
    print(f"\n品牌分布:")
    for brand, count in sorted(brand_counts.items(), key=lambda x: -x[1]):
        print(f"  {brand}: {count}")

    db.close()


if __name__ == "__main__":
    main()
