#!/usr/bin/env python3
"""
将WebSearch找到的淘宝/天猫电火灶商品数据写入数据库
"""
import sqlite3
import os
import re

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ecommerce.db")

# 从搜索结果中提取的天猫/淘宝商品
TAOBAO_PRODUCTS = [
    {
        "title": "华火2026新款双灶电火灶台嵌两用6000瓦家用电生明火灶智能电燃灶",
        "price": 2399, "original_price": 3980, "shop_name": "华火新能源专卖店",
        "brand": "华火", "sales_text": "月销70", "location": "四川巴中",
        "url": "https://tao.hooos.com/goods_VrNVeeni6twv8zqxaYf2kbUvtV-yz622osApPXngQPu4.html",
    },
    {
        "title": "华火电火灶2500W防水电焰灶台式电燃加热大火力热效高插电生明火",
        "price": 2880, "original_price": 3290, "shop_name": "华火华焰天下专卖店",
        "brand": "华火", "sales_text": "月销51", "location": "广东深圳",
        "url": "https://tao.hooos.com/goods_XZ2xkV9IGtXvgqoBootVY9FBtg-Gn755MIqWvAkBWrI9.html",
    },
    {
        "title": "华火电火灶3000W单灶新型电火灶台嵌两用家用电焰灶",
        "price": 2380, "original_price": 2580, "shop_name": "华火新能源专卖店",
        "brand": "华火", "sales_text": "月销100+", "location": "四川巴中",
        "url": "",
    },
    {
        "title": "星煜新能源纯电火灶插电生火大功率新型电焰灶炉公寓户外以电生火",
        "price": 2999, "original_price": 2999, "shop_name": "星煜电焰旗舰店",
        "brand": "星煜", "sales_text": "月销9205", "location": "广东深圳",
        "url": "http://www.ebuyso.com/50035156/CA3kNMD2XTGegeDX9J.html",
        "good_rate": 98.0, "comment_count": 9205,
    },
    {
        "title": "星煜家用新型电火灶明火不用燃气新能源电焰炉3000W",
        "price": 2069, "original_price": 2999, "shop_name": "星煜电焰旗舰店",
        "brand": "星煜", "sales_text": "月销500+", "location": "广东深圳",
        "url": "https://www.smzdm.com/p/161025544/",
    },
    {
        "title": "志高家用气电两用燃气灶电气煤气灶一体电磁炉5200W",
        "price": 699, "original_price": 899, "shop_name": "志高厨卫旗舰店",
        "brand": "志高", "sales_text": "月销100+", "location": "广东广州",
        "url": "https://tao.hooos.com/goods_9oMVkWZSBtO90qNDnjh22BuQt6-4RDrrQF8v8z9Y5OhO.html",
    },
    {
        "title": "华火电火灶双灶6KW大功率电燃灶酒店餐厅厨房用猛火双头炉台式",
        "price": 4980, "original_price": 5380, "shop_name": "华火华焰天下专卖店",
        "brand": "华火", "sales_text": "月销2", "location": "广东深圳",
        "url": "https://tao.hooos.com/goods_JAd58NVfRtqNVDmgAWTXXWuvta-8ZkvvmF5ROGDAp9Ux.html",
    },
    {
        "title": "华火2026家用新款双电火灶6000瓦大功率纯电生明火电燃灶",
        "price": 2480, "original_price": 2880, "shop_name": "华火新能源专卖店",
        "brand": "华火", "sales_text": "已售27", "location": "四川巴中",
        "url": "",
    },
    {
        "title": "华火电生明火电燃灶电陶炉双灶台嵌两用",
        "price": 3980, "original_price": 4380, "shop_name": "华火新能源专卖店",
        "brand": "华火", "sales_text": "已售100+", "location": "四川巴中",
        "url": "",
    },
    {
        "title": "华火电火灶U7Pro家用灶台嵌两用电焰灶",
        "price": 2499, "original_price": 2899, "shop_name": "华火新能源专卖店",
        "brand": "华火", "sales_text": "已售56", "location": "四川巴中",
        "url": "",
    },
    {
        "title": "华火6KW双灶台嵌两用电燃灶家用电火灶",
        "price": 1999, "original_price": 2599, "shop_name": "华火华焰天下专卖店",
        "brand": "华火", "sales_text": "已售26", "location": "广东深圳",
        "url": "",
    },
    {
        "title": "华火电火灶U10Pro嵌入式双明火灶台嵌两用",
        "price": 2299, "original_price": 2499, "shop_name": "华火新能源专卖店",
        "brand": "华火", "sales_text": "已售8", "location": "四川巴中",
        "url": "",
    },
    {
        "title": "华火电火灶3500W组合灶双灶电陶炉一体灶",
        "price": 3480, "original_price": 3980, "shop_name": "华火华焰天下专卖店",
        "brand": "华火", "sales_text": "已售21", "location": "广东深圳",
        "url": "",
    },
    {
        "title": "华火电火灶电陶炉新款组合双灶台嵌两用",
        "price": 1999, "original_price": 2399, "shop_name": "华火新能源专卖店",
        "brand": "华火", "sales_text": "已售46", "location": "四川巴中",
        "url": "",
    },
    {
        "title": "华火台嵌两用钢化玻璃电生明火灶电焰灶",
        "price": 2880, "original_price": 3280, "shop_name": "华火华焰天下专卖店",
        "brand": "华火", "sales_text": "已售65", "location": "广东深圳",
        "url": "",
    },
    {
        "title": "华火电火灶U7台用单灶家用电焰灶",
        "price": 2099, "original_price": 2399, "shop_name": "华火新能源专卖店",
        "brand": "华火", "sales_text": "已售18", "location": "四川巴中",
        "url": "",
    },
    {
        "title": "华火电火灶U9台用双灶6000W电燃灶",
        "price": 1999, "original_price": 2299, "shop_name": "华火华焰天下专卖店",
        "brand": "华火", "sales_text": "已售9", "location": "广东深圳",
        "url": "",
    },
    {
        "title": "华火电火灶5000W商用旋钮式单灶大功率",
        "price": 5380, "original_price": 5980, "shop_name": "华火华焰天下专卖店",
        "brand": "华火", "sales_text": "已售12", "location": "广东深圳",
        "url": "",
    },
    {
        "title": "华火电火灶U7家用电焰灶台嵌两用3000W",
        "price": 2399, "original_price": 2699, "shop_name": "华火新能源专卖店",
        "brand": "华火", "sales_text": "已售2", "location": "四川巴中",
        "url": "",
    },
    {
        "title": "华火电陶电火组合灶大火台嵌两用双灶",
        "price": 3980, "original_price": 4380, "shop_name": "华火新能源专卖店",
        "brand": "华火", "sales_text": "已售11", "location": "四川巴中",
        "url": "",
    },
    {
        "title": "华火电火灶U10Pro嵌入式双明火灶高端款",
        "price": 3680, "original_price": 3980, "shop_name": "华火华焰天下专卖店",
        "brand": "华火", "sales_text": "已售4", "location": "广东深圳",
        "url": "",
    },
    {
        "title": "星煜电焰灶插电生明火3.5KW电燃灶电焰电陶组合灶",
        "price": 2639, "original_price": 2999, "shop_name": "星煜电焰旗舰店",
        "brand": "星煜", "sales_text": "月销2.4万", "location": "广东深圳",
        "url": "https://www.chanmama.com/open/tiksaleRank/5D5CfQMy4s3w12ZkCjXBF4kraqyOYTs0.html",
        "good_rate": 98.0, "comment_count": 24000,
    },
    {
        "title": "华火电火灶电陶炉一体灶双灶组合台嵌两用大火力",
        "price": 4282, "original_price": 4680, "shop_name": "华火新能源专卖店",
        "brand": "华火", "sales_text": "已售30+", "location": "四川巴中",
        "url": "https://comment.zol.com.cn/59/10631526_0_0_1.html",
    },
    {
        "title": "华火2025款新型家用电火灶明火不用燃气新能源台嵌电焰灶电生明火",
        "price": 2330, "original_price": 2380, "shop_name": "华火新能源专卖店",
        "brand": "华火", "sales_text": "月销50+", "location": "四川巴中",
        "url": "https://m.smzdm.com/p/169909701/",
    },
]


def save_taobao_products():
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()

    # 确保表存在
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id     TEXT UNIQUE,
            platform       TEXT,
            keyword        TEXT,
            title          TEXT,
            price          REAL,
            original_price REAL,
            shop_name      TEXT,
            brand          TEXT,
            model          TEXT,
            url            TEXT,
            image_url      TEXT,
            comment_count  INTEGER DEFAULT 0,
            good_count     INTEGER DEFAULT 0,
            general_count  INTEGER DEFAULT 0,
            poor_count     INTEGER DEFAULT 0,
            good_rate      REAL,
            general_rate   REAL,
            poor_rate      REAL,
            sales_text     TEXT,
            created_at     TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at     TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    inserted = 0
    updated = 0

    for i, p in enumerate(TAOBAO_PRODUCTS):
        # 生成唯一ID
        product_id = f"tb_web_{i+1:04d}"

        # 从sales_text提取销量数字
        sales_text = p.get("sales_text", "")
        comment_count = p.get("comment_count", 0)
        if not comment_count and sales_text:
            m = re.search(r'(\d+)', sales_text.replace("万", "0000"))
            if m:
                comment_count = int(m.group(1))
                if "万" in sales_text:
                    comment_count = int(m.group(1)) * 10000

        try:
            c.execute("""
                INSERT INTO products (product_id, platform, keyword, title, price,
                                       original_price, shop_name, brand, url, image_url,
                                       comment_count, good_rate, sales_text)
                VALUES (?, 'taobao', '电火灶', ?, ?, ?, ?, ?, ?, '', ?, ?, ?)
                ON CONFLICT(product_id) DO UPDATE SET
                    title=excluded.title, price=excluded.price,
                    original_price=excluded.original_price,
                    shop_name=excluded.shop_name, sales_text=excluded.sales_text,
                    comment_count=MAX(comment_count, excluded.comment_count),
                    good_rate=COALESCE(NULLIF(good_rate, 0), excluded.good_rate),
                    updated_at=datetime('now','localtime')
            """, (
                product_id,
                p["title"],
                p["price"],
                p.get("original_price", 0),
                p.get("shop_name", ""),
                p.get("brand", ""),
                p.get("url", ""),
                comment_count,
                p.get("good_rate", 0),
                sales_text,
            ))
            if c.rowcount == 1:
                inserted += 1
            else:
                updated += 1
        except Exception as e:
            print(f"  错误: {e}")

    db.commit()

    # 统计
    c.execute("SELECT COUNT(*) FROM products WHERE platform='taobao'")
    total = c.fetchone()[0]
    c.execute("SELECT brand, COUNT(*) FROM products WHERE platform='taobao' GROUP BY brand ORDER BY COUNT(*) DESC")
    brands = c.fetchall()
    c.execute("SELECT MIN(price), MAX(price), AVG(price) FROM products WHERE platform='taobao' AND price > 0")
    price_range = c.fetchone()

    print(f"淘宝/天猫商品入库完成!")
    print(f"  新增: {inserted} | 更新: {updated} | 总计: {total}")
    print(f"  品牌分布: {brands}")
    print(f"  价格区间: ¥{price_range[0]:.0f} - ¥{price_range[1]:.0f} | 均价: ¥{price_range[2]:.0f}")

    db.close()


if __name__ == "__main__":
    save_taobao_products()
