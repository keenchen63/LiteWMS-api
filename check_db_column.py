#!/usr/bin/env python3
"""检查数据库列类型的脚本"""
import sys
from sqlalchemy import create_engine, text
from app.config import settings

def check_column_type():
    """检查 admin 表的 totp_secret 列类型"""
    engine = create_engine(settings.DATABASE_URL)
    
    with engine.connect() as conn:
        # PostgreSQL 查询列类型
        result = conn.execute(text("""
            SELECT 
                column_name, 
                data_type,
                udt_name
            FROM information_schema.columns 
            WHERE table_name = 'admin' 
            AND column_name = 'totp_secret'
        """))
        
        row = result.fetchone()
        if row:
            print(f"列名: {row[0]}")
            print(f"数据类型: {row[1]}")
            print(f"UDT 名称: {row[2]}")
            
            if row[1] == 'json' or row[1] == 'jsonb':
                print("✓ 列类型正确 (JSON)")
            else:
                print(f"⚠️  列类型不正确: {row[1]} (应该是 json 或 jsonb)")
                print("\n需要执行以下 SQL 来修改列类型:")
                print("ALTER TABLE admin ALTER COLUMN totp_secret TYPE jsonb USING totp_secret::jsonb;")
        else:
            print("未找到 totp_secret 列")
        
        # 检查当前数据
        result = conn.execute(text("SELECT totp_secret FROM admin LIMIT 1"))
        row = result.fetchone()
        if row and row[0]:
            print(f"\n当前数据示例 (前 200 字符):")
            print(str(row[0])[:200])
            print(f"\n数据类型: {type(row[0])}")

if __name__ == "__main__":
    check_column_type()

