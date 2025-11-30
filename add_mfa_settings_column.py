#!/usr/bin/env python3
"""
添加 mfa_settings 字段到 admin 表的迁移脚本
"""
import sys
from sqlalchemy import create_engine, text
from app.config import settings

def add_mfa_settings_column():
    """添加 mfa_settings 字段到 admin 表"""
    try:
        engine = create_engine(settings.DATABASE_URL)
        
        with engine.connect() as conn:
            # 检查字段是否已存在
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'admin' 
                AND column_name = 'mfa_settings'
            """))
            
            if result.fetchone():
                print("✓ mfa_settings 字段已存在，跳过迁移")
                return
            
            # 添加字段
            print("正在添加 mfa_settings 字段...")
            conn.execute(text("""
                ALTER TABLE admin 
                ADD COLUMN mfa_settings JSON
            """))
            conn.commit()
            
            print("✓ mfa_settings 字段添加成功！")
            print("  类型：JSON")
            print("  默认值：NULL（将使用代码中的默认配置）")
            
    except Exception as e:
        print(f"❌ 迁移失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("=" * 60)
    print("MFA 细粒度配置字段迁移脚本")
    print("=" * 60)
    add_mfa_settings_column()
    print("=" * 60)

