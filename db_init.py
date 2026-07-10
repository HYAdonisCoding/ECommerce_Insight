#!/usr/bin/env python3
"""电火灶电商数据库 - SQLite初始化脚本"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ecommerce.db")

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # ========== 商品表 ==========
    c.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        platform        TEXT NOT NULL,          -- 'jd' / 'taobao' / 'tmall'
        product_id      TEXT NOT NULL,          -- 平台商品ID
        title           TEXT,                   -- 商品标题
        price           REAL,                   -- 当前价格
        original_price  REAL,                   -- 原价
        shop_name       TEXT,                   -- 店铺名称
        brand           TEXT,                   -- 品牌
        model           TEXT,                   -- 型号
        url             TEXT,                   -- 商品链接
        sales_volume    TEXT,                   -- 销量描述(如"月销1000+")
        sales_count     INTEGER DEFAULT 0,      -- 销量数值(解析后)
        review_count    INTEGER DEFAULT 0,      -- 评价总数
        good_rate       REAL,                   -- 好评率 %
        neutral_rate    REAL,                   -- 中评率 %
        poor_rate       REAL,                   -- 差评率 %
        good_count      INTEGER DEFAULT 0,      -- 好评数
        neutral_count   INTEGER DEFAULT 0,      -- 中评数
        poor_count      INTEGER DEFAULT 0,      -- 差评数
        image_url       TEXT,                   -- 主图链接
        search_keyword  TEXT,                   -- 搜索关键词
        collected_at    TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(platform, product_id)
    )
    """)

    # ========== 评价表 ==========
    c.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        platform        TEXT NOT NULL,
        product_id      TEXT NOT NULL,
        review_id       TEXT,                   -- 评价ID
        rating          INTEGER,                -- 评分 1-5
        content         TEXT,                   -- 评价内容
        author          TEXT,                   -- 评论者
        date            TEXT,                   -- 评论日期
        variant         TEXT,                   -- 商品规格/型号
        has_image       INTEGER DEFAULT 0,      -- 是否有图
        has_video       INTEGER DEFAULT 0,      -- 是否有视频
        is_append       INTEGER DEFAULT 0,      -- 是否追评
        useful_count    INTEGER DEFAULT 0,      -- 有用数
        sentiment       TEXT,                   -- 情感: positive/neutral/negative
        collected_at    TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(platform, product_id, review_id)
    )
    """)

    # ========== 评价标签表 ==========
    c.execute("""
    CREATE TABLE IF NOT EXISTS review_tags (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        platform        TEXT NOT NULL,
        product_id      TEXT NOT NULL,
        tag_name        TEXT,                   -- 标签名(如"加热快"、"噪音大")
        tag_count       INTEGER DEFAULT 0,      -- 标签出现次数
        tag_type        TEXT,                   -- 'pros' / 'cons' / 'neutral'
        collected_at    TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(platform, product_id, tag_name, tag_type)
    )
    """)

    # ========== 搜索日志表 ==========
    c.execute("""
    CREATE TABLE IF NOT EXISTS search_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword         TEXT NOT NULL,
        platform        TEXT NOT NULL,
        page            INTEGER,
        result_count    INTEGER DEFAULT 0,
        searched_at     TEXT DEFAULT (datetime('now','localtime'))
    )
    """)

    # ========== 用户体验汇总表 ==========
    c.execute("""
    CREATE TABLE IF NOT EXISTS user_experience (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id      TEXT,
        platform        TEXT,
        pros            TEXT,                   -- 优点(逗号分隔)
        cons            TEXT,                   -- 缺点(逗号分隔)
        usage_scenario  TEXT,                   -- 使用场景
        rating_avg      REAL,                   -- 平均评分
        recommendation  TEXT,                   -- 推荐度
        collected_at    TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(platform, product_id)
    )
    """)

    # ========== 创建索引 ==========
    c.execute("CREATE INDEX IF NOT EXISTS idx_products_platform ON products(platform)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_products_keyword ON products(search_keyword)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_reviews_product ON reviews(platform, product_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_reviews_rating ON reviews(rating)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tags_product ON review_tags(platform, product_id)")

    conn.commit()
    conn.close()
    print(f"数据库初始化完成: {DB_PATH}")
    print("表: products, reviews, review_tags, search_log, user_experience")

if __name__ == "__main__":
    init_db()
