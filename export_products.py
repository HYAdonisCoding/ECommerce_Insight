import sqlite3
import pandas as pd
from pathlib import Path

# SQLite 数据库路径
DB_PATH = Path("data/ecommerce.db")

# 导出文件
OUTPUT_PATH = Path("data/products_export.csv")


def export_products():
    conn = sqlite3.connect(DB_PATH)

    sql = """
    SELECT *
    FROM products
    ORDER BY created_at DESC
    """

    df = pd.read_sql_query(sql, conn)

    conn.close()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    print(f"导出完成: {OUTPUT_PATH}")
    print(f"数据量: {len(df)} 条")
    print(df.head())


if __name__ == "__main__":
    export_products()
