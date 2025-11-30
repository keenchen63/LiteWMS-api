#!/usr/bin/env python3
"""
重置管理员密码脚本

如果忘记了 MFA 页面的登录密码，可以使用此脚本重置密码。

使用方法：
1. 确保已激活虚拟环境
2. 运行脚本：python reset_admin_password.py
3. 按照提示输入新密码

注意：
- 此脚本需要直接访问数据库
- 重置密码后，MFA 设备配置不会受影响
- 建议在生产环境中谨慎使用
"""
import sys
import os
import getpass

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text
from app.config import settings
from app.routers.mfa import get_password_hash

def reset_admin_password():
    """重置管理员密码"""
    print("=" * 60)
    print("重置管理员密码")
    print("=" * 60)
    print()
    
    # 获取新密码
    print("请输入新密码（至少 6 位，最多 72 位）：")
    new_password = getpass.getpass("新密码: ")
    
    if len(new_password) < 6:
        print("❌ 错误：密码长度至少 6 位")
        sys.exit(1)
    
    if len(new_password) > 72:
        print("❌ 错误：密码长度不能超过 72 位")
        sys.exit(1)
    
    # 确认密码
    confirm_password = getpass.getpass("确认密码: ")
    
    if new_password != confirm_password:
        print("❌ 错误：两次输入的密码不一致")
        sys.exit(1)
    
    try:
        # 连接数据库
        engine = create_engine(settings.DATABASE_URL)
        
        with engine.connect() as conn:
            # 检查 admin 表是否存在
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'admin'
                )
            """))
            
            if not result.fetchone()[0]:
                print("❌ 错误：admin 表不存在，请先运行应用初始化数据库")
                sys.exit(1)
            
            # 生成密码哈希
            password_hash = get_password_hash(new_password)
            
            # 更新密码
            conn.execute(text("""
                UPDATE admin 
                SET password_hash = :password_hash,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = (SELECT id FROM admin LIMIT 1)
            """), {"password_hash": password_hash})
            
            conn.commit()
            
            print()
            print("=" * 60)
            print("✓ 密码重置成功！")
            print("=" * 60)
            print()
            print("现在可以使用新密码登录 MFA 管理页面。")
            print("MFA 设备配置不会受到影响。")
            print()
            
    except Exception as e:
        print(f"❌ 错误：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    reset_admin_password()

