#!/usr/bin/env python3
"""
生成操作记录模拟数据脚本

此脚本会：
1. 清除所有现有的操作记录
2. 生成新的模拟操作记录数据（入库、出库、调整、调拨）

使用方法：
1. 确保已激活虚拟环境
2. 运行脚本：python generate_transaction_data.py

注意：
- 此脚本会删除所有现有的操作记录
- 生成的模拟数据基于现有的仓库、品类和物品
- 建议在测试环境中使用
"""
import sys
import os
import random
import json
from datetime import datetime, timedelta

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import settings
from app import models

# 操作人员列表
OPERATORS = ["张三", "李四", "王五", "赵六", "钱七", "孙八", "周九", "吴十"]

# 备注模板
INBOUND_NOTES = [
    "供应商：{supplier}，批次号：{batch}",
    "采购订单：PO-{order}，供应商：{supplier}",
    "到货验收，批次：{batch}",
    "供应商：{supplier}，到货日期：{date}",
]

OUTBOUND_NOTES = [
    "项目：{project}，用途：{purpose}",
    "领用部门：{department}，项目编号：{project}",
    "用途：{purpose}，项目：{project}",
    "领用人：{user}，用途：{purpose}",
]

ADJUST_NOTES = [
    "库存盘点调整，差异原因：{reason}",
    "库存盘点，发现差异：{reason}",
    "库存调整，原因：{reason}",
    "盘点调整：{reason}",
]

TRANSFER_NOTES = [
    "仓库间调拨，原因：{reason}",
    "调拨原因：{reason}，审批人：{approver}",
    "仓库调拨：{reason}",
    "调拨申请：{reason}",
]

SUPPLIERS = ["华为", "中兴", "烽火", "海康威视", "大华", "TP-Link", "H3C", "思科"]
PROJECTS = ["项目A", "项目B", "项目C", "数据中心", "办公楼", "厂房", "仓库改造"]
DEPARTMENTS = ["IT部", "工程部", "运维部", "采购部", "仓储部"]
PURPOSES = ["网络布线", "设备连接", "系统升级", "维护更换", "新项目部署"]
REASONS = ["库存盘点", "仓库整理", "需求调整", "错误修正", "系统调整"]
APPROVERS = ["经理", "主管", "负责人"]


def generate_transaction_data():
    """生成操作记录模拟数据"""
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        print("=" * 60)
        print("开始生成操作记录模拟数据")
        print("=" * 60)
        
        # 1. 清除所有现有操作记录
        print("\n1. 清除现有操作记录...")
        deleted_count = db.query(models.Transaction).delete()
        db.commit()
        print(f"   已删除 {deleted_count} 条操作记录")
        
        # 2. 获取现有数据
        print("\n2. 获取现有数据...")
        warehouses = db.query(models.Warehouse).all()
        categories = db.query(models.Category).all()
        items = db.query(models.InventoryItem).all()
        
        if not warehouses:
            print("   错误：未找到仓库数据，请先运行 seed_data.py 初始化数据")
            return
        
        if not categories:
            print("   错误：未找到品类数据，请先运行 seed_data.py 初始化数据")
            return
        
        if not items:
            print("   错误：未找到物品数据，请先运行 seed_data.py 初始化数据")
            return
        
        print(f"   找到 {len(warehouses)} 个仓库")
        print(f"   找到 {len(categories)} 个品类")
        print(f"   找到 {len(items)} 个物品")
        
        # 3. 生成模拟数据
        print("\n3. 生成模拟操作记录...")
        
        # 生成日期范围（过去30天）
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=30)
        
        transactions_created = 0
        
        # 按日期生成记录
        current_date = start_date
        while current_date <= end_date:
            # 每天生成 5-15 条记录
            daily_count = random.randint(5, 15)
            
            for _ in range(daily_count):
                # 随机选择操作类型
                trans_type = random.choice(['IN', 'OUT', 'ADJUST', 'TRANSFER'])
                
                # 随机选择仓库和物品
                warehouse = random.choice(warehouses)
                warehouse_items = [item for item in items if item.warehouse_id == warehouse.id]
                
                if not warehouse_items:
                    continue
                
                # 根据操作类型过滤物品
                if trans_type == 'OUT':
                    # 出库只能选择有库存的物品
                    available_items = [item for item in warehouse_items if item.quantity > 0]
                    if not available_items:
                        continue
                    warehouse_items = available_items
                elif trans_type == 'TRANSFER':
                    # 调拨只能选择有库存的物品
                    available_items = [item for item in warehouse_items if item.quantity > 0]
                    if not available_items:
                        continue
                    warehouse_items = available_items
                
                # 随机选择1-5个物品
                num_items = random.randint(1, min(5, len(warehouse_items)))
                selected_items = random.sample(warehouse_items, num_items)
                
                operator = random.choice(OPERATORS)
                transaction_date = current_date + timedelta(
                    hours=random.randint(8, 18),
                    minutes=random.randint(0, 59)
                )
                
                # 生成备注
                if trans_type == 'IN':
                    supplier = random.choice(SUPPLIERS)
                    batch = f"BATCH-{random.randint(1000, 9999)}"
                    order = f"PO-{random.randint(10000, 99999)}"
                    note_template = random.choice(INBOUND_NOTES)
                    notes = note_template.format(
                        supplier=supplier,
                        batch=batch,
                        order=order,
                        date=transaction_date.strftime("%Y-%m-%d")
                    )
                elif trans_type == 'OUT':
                    project = random.choice(PROJECTS)
                    purpose = random.choice(PURPOSES)
                    department = random.choice(DEPARTMENTS)
                    note_template = random.choice(OUTBOUND_NOTES)
                    notes = note_template.format(
                        project=project,
                        purpose=purpose,
                        department=department,
                        user=operator
                    )
                elif trans_type == 'ADJUST':
                    reason = random.choice(REASONS)
                    note_template = random.choice(ADJUST_NOTES)
                    notes = note_template.format(reason=reason)
                else:  # TRANSFER
                    target_warehouse = random.choice([w for w in warehouses if w.id != warehouse.id])
                    reason = random.choice(REASONS)
                    approver = random.choice(APPROVERS)
                    note_template = random.choice(TRANSFER_NOTES)
                    notes = note_template.format(reason=reason, approver=approver)
                
                # 构建多物品数据
                items_data = []
                total_quantity = 0
                
                for item in selected_items:
                    # 获取品类名称
                    category = next((c for c in categories if c.id == item.category_id), None)
                    category_name = category.name if category else "未知品类"
                    
                    # 生成数量
                    if trans_type == 'IN':
                        quantity = random.randint(10, 100)
                    elif trans_type == 'OUT':
                        # 出库数量不能超过当前库存，且至少为1
                        max_qty = min(50, item.quantity)
                        if max_qty < 1:
                            continue  # 跳过库存为0的物品（理论上不应该出现，因为已过滤）
                        quantity = random.randint(1, max_qty)
                    elif trans_type == 'ADJUST':
                        # 调整可以是正数或负数
                        quantity = random.randint(-20, 20)
                    else:  # TRANSFER
                        # 调拨数量不能超过当前库存，且至少为1
                        max_qty = min(30, item.quantity)
                        if max_qty < 1:
                            continue  # 跳过库存为0的物品（理论上不应该出现，因为已过滤）
                        quantity = random.randint(1, max_qty)
                    
                    items_data.append({
                        "category_name": category_name,
                        "specs": item.specs,
                        "quantity": quantity
                    })
                    
                    if trans_type == 'ADJUST':
                        total_quantity += quantity
                    else:
                        total_quantity += quantity
                
                # 如果所有物品都被跳过，则跳过这条记录
                if not items_data:
                    continue
                
                # 构建 item_name_snapshot
                if trans_type == 'IN':
                    snapshot_type = 'MULTI_ITEM_INBOUND'
                elif trans_type == 'OUT':
                    snapshot_type = 'MULTI_ITEM_OUTBOUND'
                elif trans_type == 'ADJUST':
                    snapshot_type = 'MULTI_ITEM_ADJUST'
                    # 调整需要 quantity_diff
                    items_data_with_diff = []
                    for item_data in items_data:
                        items_data_with_diff.append({
                            "category_name": item_data["category_name"],
                            "specs": item_data["specs"],
                            "quantity_diff": item_data["quantity"]
                        })
                    items_data = items_data_with_diff
                else:  # TRANSFER
                    snapshot_type = 'MULTI_ITEM_TRANSFER'
                
                item_name_snapshot = json.dumps({
                    "type": snapshot_type,
                    "items": items_data,
                    "total_quantity": abs(total_quantity),
                    "total_quantity_diff": total_quantity if trans_type == 'ADJUST' else None
                })
                
                # 使用第一个物品的ID作为主item_id
                primary_item_id = selected_items[0].id
                
                # 创建交易记录
                if trans_type == 'TRANSFER':
                    # 调拨需要创建两条记录
                    target_warehouse = random.choice([w for w in warehouses if w.id != warehouse.id])
                    
                    # 源仓库记录（调拨出）
                    transaction_out = models.Transaction(
                        warehouse_id=warehouse.id,
                        related_warehouse_id=target_warehouse.id,
                        item_id=primary_item_id,
                        item_name_snapshot=item_name_snapshot,
                        quantity=-abs(total_quantity),
                        date=transaction_date,
                        user=operator,
                        notes=notes,
                        type='TRANSFER'
                    )
                    db.add(transaction_out)
                    
                    # 目标仓库记录（调拨入）
                    # 查找目标仓库中对应的物品，如果不存在则使用源物品ID
                    target_item = next(
                        (item for item in items 
                         if item.warehouse_id == target_warehouse.id 
                         and item.category_id == selected_items[0].category_id
                         and item.specs == selected_items[0].specs),
                        None
                    )
                    target_item_id = target_item.id if target_item else primary_item_id
                    
                    transaction_in = models.Transaction(
                        warehouse_id=target_warehouse.id,
                        related_warehouse_id=warehouse.id,
                        item_id=target_item_id,
                        item_name_snapshot=item_name_snapshot,
                        quantity=abs(total_quantity),
                        date=transaction_date,
                        user=operator,
                        notes=notes,
                        type='TRANSFER'
                    )
                    db.add(transaction_in)
                    transactions_created += 2
                else:
                    # 其他类型只需要一条记录
                    quantity_value = total_quantity if trans_type == 'ADJUST' else abs(total_quantity)
                    if trans_type == 'OUT':
                        quantity_value = -abs(total_quantity)
                    
                    transaction = models.Transaction(
                        warehouse_id=warehouse.id,
                        item_id=primary_item_id,
                        item_name_snapshot=item_name_snapshot,
                        quantity=quantity_value,
                        date=transaction_date,
                        user=operator,
                        notes=notes,
                        type=trans_type
                    )
                    db.add(transaction)
                    transactions_created += 1
            
            # 移动到下一天
            current_date += timedelta(days=1)
        
        # 提交所有更改
        db.commit()
        
        print(f"\n✅ 成功生成 {transactions_created} 条操作记录")
        print(f"   日期范围：{start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")
        print(f"   包含类型：入库、出库、调整、调拨")
        print("\n" + "=" * 60)
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ 生成数据失败: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    try:
        generate_transaction_data()
    except KeyboardInterrupt:
        print("\n\n操作已取消")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n发生错误: {e}")
        sys.exit(1)

