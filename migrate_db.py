"""
数据库迁移脚本：添加 total_hours 字段到 category_progress 表
运行方式：python migrate_db.py
"""
import os
import sqlite3
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

# 获取数据库URL
if os.getenv('DATABASE_URL'):
    database_url = os.getenv('DATABASE_URL').replace('postgres://', 'postgresql://')
else:
    database_url = 'sqlite:///instance/timemaster.db'

print(f"连接数据库: {database_url}")

engine = create_engine(database_url)

with engine.connect() as conn:
    # 检查字段是否已存在
    if 'sqlite' in database_url:
        # SQLite 查询
        result = conn.execute(text("PRAGMA table_info(category_progress)"))
        columns = [row[1] for row in result]
    else:
        # PostgreSQL 查询
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'category_progress'
        """))
        columns = [row[0] for row in result]

    print(f"当前字段: {columns}")

    if 'total_hours' not in columns:
        print("添加 total_hours 字段...")
        try:
            conn.execute(text("ALTER TABLE category_progress ADD COLUMN total_hours FLOAT DEFAULT 0.0"))
            conn.commit()
            print("✓ total_hours 字段添加成功！")
        except Exception as e:
            print(f"✗ 添加失败: {e}")
    else:
        print("✓ total_hours 字段已存在，无需添加")

print("迁移完成！")
