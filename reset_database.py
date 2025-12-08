#!/usr/bin/env python3
"""
数据库重置脚本
将数据库恢复到初始状态（清空所有数据并重新初始化）

使用方法:
    python reset_database.py
"""

import sys
from sqlalchemy import text
from app.database import SessionLocal, engine, Base
from app import models
from app.seed_data import seed_data

def reset_database(keep_admin: bool = False, seed_data_flag: bool = True):
    """
    重置数据库到初始状态
    
    Args:
        keep_admin: 如果为 True，保留 admin 表的数据（MFA 配置等）
        seed_data_flag: 如果为 True，重新初始化种子数据
    """
    db = SessionLocal()
    
    try:
        print("=" * 80)
        print("数据库重置脚本")
        print("=" * 80)
        
        # 交互式选择：是否保留管理员配置
        print("\n请选择操作选项：")
        print("1. 清空所有数据（包括管理员配置）")
        print("2. 保留管理员配置（MFA 设置等）")
        admin_choice = input("\n请选择 (1/2，默认 1): ").strip()
        keep_admin = admin_choice == '2'
        
        if keep_admin:
            print("\n✅ 将保留管理员配置（MFA 设置等）")
        else:
            print("\n⚠️  将清空所有数据，包括管理员配置！")
        
        # 交互式选择：是否创建种子数据
        print("\n请选择是否创建种子数据：")
        print("1. 创建种子数据（仓库、品类、示例库存）")
        print("2. 不创建种子数据（仅清空数据）")
        seed_choice = input("\n请选择 (1/2，默认 1): ").strip()
        seed_data_flag = seed_choice != '2'
        
        if seed_data_flag:
            print("\n📦 将重新初始化种子数据")
        else:
            print("\n📦 不会创建种子数据（仅清空现有数据）")
        
        # 确认操作
        print("\n" + "=" * 80)
        print("操作摘要：")
        if keep_admin:
            print("  - 管理员配置：保留")
        else:
            print("  - 管理员配置：清空")
        if seed_data_flag:
            print("  - 种子数据：创建")
        else:
            print("  - 种子数据：不创建")
        print("=" * 80)
        
        confirm = input("\n确认要重置数据库吗？(输入 'yes' 确认): ")
        if confirm.lower() != 'yes':
            print("操作已取消")
            return
        
        print("\n开始重置数据库...")
        
        # 按依赖顺序删除数据（避免外键约束错误）
        # 注意：不使用 session_replication_role，因为需要特殊权限
        # 直接按正确顺序删除即可
        
        print("1. 清空交易记录表...")
        try:
            db.execute(text("DELETE FROM transactions"))
            print(f"   ✅ 已清空交易记录表")
        except Exception as e:
            db.rollback()
            print(f"   ❌ 清空交易记录表时出错: {e}")
            raise
        
        print("2. 清空库存物品表...")
        try:
            db.execute(text("DELETE FROM items"))
            print(f"   ✅ 已清空库存物品表")
        except Exception as e:
            db.rollback()
            print(f"   ❌ 清空库存物品表时出错: {e}")
            raise
        
        print("3. 清空品类表...")
        try:
            db.execute(text("DELETE FROM categories"))
            print(f"   ✅ 已清空品类表")
        except Exception as e:
            db.rollback()
            print(f"   ❌ 清空品类表时出错: {e}")
            raise
        
        print("4. 清空仓库表...")
        try:
            db.execute(text("DELETE FROM warehouses"))
            print(f"   ✅ 已清空仓库表")
        except Exception as e:
            db.rollback()
            print(f"   ❌ 清空仓库表时出错: {e}")
            raise
        
        # 处理 admin 表
        if keep_admin:
            print("5. 保留管理员配置...")
            try:
                admin_count = db.query(models.Admin).count()
                if admin_count > 0:
                    print(f"   ✅ 保留 {admin_count} 条管理员记录")
                else:
                    print("   ℹ️  管理员表为空")
            except Exception as e:
                db.rollback()
                print(f"   ❌ 检查管理员表时出错: {e}")
                raise
        else:
            print("5. 清空管理员表...")
            try:
                db.execute(text("DELETE FROM admin"))
                print(f"   ✅ 已清空管理员表")
            except Exception as e:
                db.rollback()
                print(f"   ❌ 清空管理员表时出错: {e}")
                raise
        
        # 重置序列（PostgreSQL）
        print("6. 重置自增序列...")
        sequences = [
            "categories_id_seq",
            "warehouses_id_seq",
            "items_id_seq",
            "transactions_id_seq"
        ]
        if not keep_admin:
            sequences.append("admin_id_seq")
        
        for seq_name in sequences:
            try:
                db.execute(text(f"ALTER SEQUENCE IF EXISTS {seq_name} RESTART WITH 1"))
                print(f"   ✅ 已重置序列 {seq_name}")
            except Exception as e:
                # 序列重置失败不影响整体操作，只记录警告
                print(f"   ⚠️  重置序列 {seq_name} 时出错（可忽略）: {e}")
        
        # 提交删除操作
        db.commit()
        print("\n✅ 数据清空完成")
        
        # 重新初始化种子数据
        if seed_data_flag:
            print("\n7. 初始化种子数据...")
            try:
                seed_data()
                print("\n" + "=" * 80)
                print("✅ 数据库重置完成！")
                print("=" * 80)
                print("\n数据库已恢复到初始状态：")
                print("  - 仓库：仓库 A, 仓库 B")
                print("  - 品类：光纤跳线、网线、MPO主干光纤")
                print("  - 库存：已创建示例库存数据")
                if keep_admin:
                    print("  - 管理员配置：已保留")
                else:
                    print("  - 管理员配置：已清空（需要重新设置）")
                print("=" * 80)
            except Exception as e:
                print(f"\n⚠️  种子数据初始化失败: {e}")
                print("数据已清空，但种子数据未创建")
                raise
        else:
            print("\n" + "=" * 80)
            print("✅ 数据库重置完成！")
            print("=" * 80)
            print("\n所有数据已清空")
            if keep_admin:
                print("  - 管理员配置：已保留")
            else:
                print("  - 管理员配置：已清空（需要重新设置）")
            print("  - 种子数据：未创建")
            print("=" * 80)
        
    except Exception as e:
        db.rollback()
        print("\n" + "=" * 80)
        print("❌ 数据库重置失败！")
        print("=" * 80)
        print(f"\n错误信息: {e}")
        print("\n请检查数据库连接和权限设置")
        print("=" * 80)
        raise
    finally:
        db.close()

if __name__ == "__main__":
    try:
        reset_database()
    except KeyboardInterrupt:
        print("\n\n操作被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n发生错误: {e}")
        sys.exit(1)

