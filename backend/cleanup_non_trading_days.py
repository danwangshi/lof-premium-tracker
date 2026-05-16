# -*- coding: utf-8 -*-
"""清理非交易日份额数据"""
from config import Config
import psycopg2

conn = psycopg2.connect(
    host=Config.DB_HOST,
    port=Config.DB_PORT,
    dbname=Config.DB_NAME,
    user=Config.DB_USER,
    password=Config.DB_PASSWORD
)

cur = conn.cursor()

# 删除 2026-05-16（周日）的数据
cur.execute("DELETE FROM fund_shares WHERE date = '2026-05-16'")
print(f"Deleted {cur.rowcount} rows for 2026-05-16 (Sunday)")

# 查看所有日期
cur.execute("SELECT DISTINCT date FROM fund_shares ORDER BY date DESC LIMIT 10")
dates = [r[0] for r in cur.fetchall()]
print(f"Remaining recent dates: {dates}")

conn.commit()
cur.close()
conn.close()
print("Cleanup complete!")
