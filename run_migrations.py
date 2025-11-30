#!/usr/bin/env python3
"""
数据库迁移脚本 - 统一执行所有数据库迁移
此脚本会检查并执行所有必要的数据库迁移，确保数据库结构与代码一致。
"""
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text
from app.config import settings

def check_and_add_column(conn, table_name: str, column_name: str, column_type: str, default_value: str = None):
    """检查并添加列（如果不存在）"""
    result = conn.execute(text(f"""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = '{table_name}' 
        AND column_name = '{column_name}'
    """))
    
    if result.fetchone():
        print(f"  ✓ {table_name}.{column_name} 字段已存在，跳过")
        return False
    
    # 构建 ALTER TABLE 语句
    alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
    if default_value:
        alter_sql += f" DEFAULT {default_value}"
    
    conn.execute(text(alter_sql))
    conn.commit()
    print(f"  ✓ 已添加 {table_name}.{column_name} 字段")
    return True

def run_migrations():
    """执行所有数据库迁移"""
    print("=" * 60)
    print("数据库迁移脚本")
    print("=" * 60)
    print(f"数据库: {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else 'N/A'}")
    print("-" * 60)
    
    try:
        engine = create_engine(settings.DATABASE_URL)
        
        with engine.connect() as conn:
            print("\n[1/2] 检查 mfa_enabled 字段...")
            check_and_add_column(
                conn, 
                'admin', 
                'mfa_enabled', 
                'BOOLEAN NOT NULL', 
                'TRUE'
            )
            
            print("\n[2/2] 检查 mfa_settings 字段...")
            check_and_add_column(
                conn, 
                'admin', 
                'mfa_settings', 
                'JSON'
            )
            
            print("\n" + "=" * 60)
            print("✓ 所有迁移已完成！")
            print("=" * 60)
            return True
            
    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    run_migrations()

