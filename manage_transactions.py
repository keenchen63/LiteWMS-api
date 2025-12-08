#!/usr/bin/env python3
"""
交易记录管理脚本
用于安全地修改或删除交易记录，同时确保库存数据的一致性

使用方法:
    python manage_transactions.py delete <transaction_id> [--reason "原因"]
    python manage_transactions.py modify <transaction_id> [--quantity <数量>] [--user <操作人>] [--notes <备注>] [--date <日期>]
    python manage_transactions.py show <transaction_id>
    python manage_transactions.py list [--warehouse <仓库ID>] [--type <类型>] [--limit <数量>]
"""

import sys
import os
import json
import argparse
from datetime import datetime
from typing import Optional, List, Dict, Any

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app.database import SessionLocal, engine
from app import models

def parse_item_snapshot(item_name_snapshot: str) -> Dict[str, Any]:
    """解析 item_name_snapshot，支持新旧格式"""
    try:
        parsed = json.loads(item_name_snapshot)
        if isinstance(parsed, dict):
            # 新格式：JSON 对象
            if 'items' in parsed and isinstance(parsed['items'], list):
                return {
                    'type': parsed.get('type', 'UNKNOWN'),
                    'items': parsed['items'],
                    'is_reverted': parsed.get('reverted', False) or parsed.get('type', '').startswith('MULTI_ITEM_REVERT_'),
                    'original_items': parsed.get('original_items', parsed['items'])
                }
            else:
                # 可能是旧格式的 JSON
                return {
                    'type': 'SINGLE_ITEM',
                    'items': [{
                        'category_name': parsed.get('category_name', ''),
                        'specs': parsed.get('specs', {}),
                        'quantity': parsed.get('quantity', 0),
                        'quantity_diff': parsed.get('quantity_diff', parsed.get('quantity', 0))
                    }],
                    'is_reverted': False,
                    'original_items': None
                }
        else:
            # 不是字典，可能是字符串
            raise ValueError("Not a dict")
    except (json.JSONDecodeError, ValueError, TypeError):
        # 旧格式：字符串 "品类名 - {...specs...}"
        try:
            if ' - ' in item_name_snapshot:
                parts = item_name_snapshot.split(' - ', 1)
                category_name = parts[0]
                specs = json.loads(parts[1]) if len(parts) > 1 else {}
            else:
                category_name = item_name_snapshot
                specs = {}
            
            return {
                'type': 'SINGLE_ITEM',
                'items': [{
                    'category_name': category_name,
                    'specs': specs,
                    'quantity': 0,  # 需要从 transaction.quantity 获取
                    'quantity_diff': 0
                }],
                'is_reverted': False,
                'original_items': None
            }
        except:
            # 完全无法解析，返回空
            return {
                'type': 'UNKNOWN',
                'items': [],
                'is_reverted': False,
                'original_items': None
            }

def reverse_transaction_effect(db: Session, transaction: models.Transaction) -> bool:
    """
    反向交易记录的影响，恢复库存状态
    返回 True 如果成功，False 如果失败
    """
    try:
        parsed = parse_item_snapshot(transaction.item_name_snapshot)
        
        # 如果是撤销记录，需要反向撤销操作（即恢复原操作）
        if parsed['is_reverted']:
            # 撤销记录：需要恢复原始操作的影响
            items = parsed.get('original_items', parsed['items'])
            # 对于撤销记录，quantity 已经是反向的，所以需要再次反向
            reverse_again = True
        else:
            # 普通记录：直接反向
            items = parsed['items']
            reverse_again = False
        
        if not items:
            print(f"⚠️  警告：交易记录 {transaction.id} 无法解析物品信息")
            return False
        
        # 处理每个物品
        for item_data in items:
            category_name = item_data.get('category_name', '')
            specs = item_data.get('specs', {})
            quantity = item_data.get('quantity', 0) or item_data.get('quantity_diff', 0)
            
            if not category_name:
                print(f"⚠️  警告：物品缺少品类名称，跳过")
                continue
            
            # 查找品类
            category = db.query(models.Category).filter(models.Category.name == category_name).first()
            if not category:
                print(f"❌ 错误：找不到品类 '{category_name}'")
                return False
            
            # 查找库存物品
            warehouse_items = db.query(models.InventoryItem).filter(
                and_(
                    models.InventoryItem.warehouse_id == transaction.warehouse_id,
                    models.InventoryItem.category_id == category.id
                )
            ).all()
            
            target_item = None
            for item in warehouse_items:
                if item.specs == specs:
                    target_item = item
                    break
            
            if not target_item:
                print(f"❌ 错误：找不到库存物品 (品类: {category_name}, 规格: {specs}, 仓库: {transaction.warehouse_id})")
                return False
            
            # 根据交易类型执行反向操作
            if transaction.type == 'IN':
                # 入库 -> 出库（减少库存）
                if reverse_again:
                    # 撤销记录：恢复入库（增加库存）
                    target_item.quantity += abs(quantity)
                else:
                    # 普通记录：反向入库（减少库存）
                    target_item.quantity = max(0, target_item.quantity - abs(quantity))
            elif transaction.type == 'OUT':
                # 出库 -> 入库（增加库存）
                if reverse_again:
                    # 撤销记录：恢复出库（减少库存）
                    target_item.quantity = max(0, target_item.quantity - abs(quantity))
                else:
                    # 普通记录：反向出库（增加库存）
                    target_item.quantity += abs(quantity)
            elif transaction.type == 'ADJUST':
                # 调整 -> 反向调整
                quantity_diff = item_data.get('quantity_diff', quantity)
                if reverse_again:
                    # 撤销记录：恢复调整
                    target_item.quantity = max(0, target_item.quantity + quantity_diff)
                else:
                    # 普通记录：反向调整
                    target_item.quantity = max(0, target_item.quantity - quantity_diff)
            elif transaction.type == 'TRANSFER':
                # 调拨 -> 反向调拨
                if transaction.quantity < 0:
                    # 调拨出
                    if reverse_again:
                        # 撤销记录：恢复调拨出（减少当前仓库，增加目标仓库）
                        target_item.quantity = max(0, target_item.quantity - abs(quantity))
                        if transaction.related_warehouse_id:
                            # 处理目标仓库
                            target_warehouse_items = db.query(models.InventoryItem).filter(
                                and_(
                                    models.InventoryItem.warehouse_id == transaction.related_warehouse_id,
                                    models.InventoryItem.category_id == category.id
                                )
                            ).all()
                            for item in target_warehouse_items:
                                if item.specs == specs:
                                    item.quantity += abs(quantity)
                                    item.updated_at = datetime.utcnow()
                                    break
                    else:
                        # 普通记录：反向调拨出（增加当前仓库，减少目标仓库）
                        target_item.quantity += abs(quantity)
                        if transaction.related_warehouse_id:
                            # 处理目标仓库
                            target_warehouse_items = db.query(models.InventoryItem).filter(
                                and_(
                                    models.InventoryItem.warehouse_id == transaction.related_warehouse_id,
                                    models.InventoryItem.category_id == category.id
                                )
                            ).all()
                            for item in target_warehouse_items:
                                if item.specs == specs:
                                    item.quantity = max(0, item.quantity - abs(quantity))
                                    item.updated_at = datetime.utcnow()
                                    break
                else:
                    # 调拨入
                    if reverse_again:
                        # 撤销记录：恢复调拨入（增加当前仓库，减少源仓库）
                        target_item.quantity += abs(quantity)
                        if transaction.related_warehouse_id:
                            # 处理源仓库
                            source_warehouse_items = db.query(models.InventoryItem).filter(
                                and_(
                                    models.InventoryItem.warehouse_id == transaction.related_warehouse_id,
                                    models.InventoryItem.category_id == category.id
                                )
                            ).all()
                            for item in source_warehouse_items:
                                if item.specs == specs:
                                    item.quantity = max(0, item.quantity - abs(quantity))
                                    item.updated_at = datetime.utcnow()
                                    break
                    else:
                        # 普通记录：反向调拨入（减少当前仓库，增加源仓库）
                        target_item.quantity = max(0, target_item.quantity - abs(quantity))
                        if transaction.related_warehouse_id:
                            # 处理源仓库
                            source_warehouse_items = db.query(models.InventoryItem).filter(
                                and_(
                                    models.InventoryItem.warehouse_id == transaction.related_warehouse_id,
                                    models.InventoryItem.category_id == category.id
                                )
                            ).all()
                            for item in source_warehouse_items:
                                if item.specs == specs:
                                    item.quantity += abs(quantity)
                                    item.updated_at = datetime.utcnow()
                                    break
            
            target_item.updated_at = datetime.utcnow()
        
        return True
    except Exception as e:
        print(f"❌ 错误：反向交易影响时出错: {e}")
        import traceback
        traceback.print_exc()
        return False

def apply_transaction_effect(db: Session, transaction: models.Transaction) -> bool:
    """
    应用交易记录的影响到库存
    用于修改交易记录后重新应用
    """
    try:
        parsed = parse_item_snapshot(transaction.item_name_snapshot)
        
        # 只处理非撤销记录
        if parsed['is_reverted']:
            print(f"⚠️  警告：跳过撤销记录的应用")
            return True
        
        items = parsed['items']
        if not items:
            print(f"⚠️  警告：交易记录 {transaction.id} 无法解析物品信息")
            return False
        
        # 处理每个物品
        for item_data in items:
            category_name = item_data.get('category_name', '')
            specs = item_data.get('specs', {})
            quantity = item_data.get('quantity', 0) or item_data.get('quantity_diff', 0)
            
            if not category_name:
                continue
            
            # 查找品类
            category = db.query(models.Category).filter(models.Category.name == category_name).first()
            if not category:
                print(f"❌ 错误：找不到品类 '{category_name}'")
                return False
            
            # 查找库存物品
            warehouse_items = db.query(models.InventoryItem).filter(
                and_(
                    models.InventoryItem.warehouse_id == transaction.warehouse_id,
                    models.InventoryItem.category_id == category.id
                )
            ).all()
            
            target_item = None
            for item in warehouse_items:
                if item.specs == specs:
                    target_item = item
                    break
            
            if not target_item:
                print(f"❌ 错误：找不到库存物品 (品类: {category_name}, 规格: {specs})")
                return False
            
            # 根据交易类型应用操作
            if transaction.type == 'IN':
                target_item.quantity += abs(quantity)
            elif transaction.type == 'OUT':
                target_item.quantity = max(0, target_item.quantity - abs(quantity))
            elif transaction.type == 'ADJUST':
                quantity_diff = item_data.get('quantity_diff', quantity)
                target_item.quantity = max(0, target_item.quantity + quantity_diff)
            elif transaction.type == 'TRANSFER':
                if transaction.quantity < 0:
                    # 调拨出：减少当前仓库，增加目标仓库
                    target_item.quantity = max(0, target_item.quantity - abs(quantity))
                    if transaction.related_warehouse_id:
                        target_warehouse_items = db.query(models.InventoryItem).filter(
                            and_(
                                models.InventoryItem.warehouse_id == transaction.related_warehouse_id,
                                models.InventoryItem.category_id == category.id
                            )
                        ).all()
                        for item in target_warehouse_items:
                            if item.specs == specs:
                                item.quantity += abs(quantity)
                                item.updated_at = datetime.utcnow()
                                break
                else:
                    # 调拨入：增加当前仓库，减少源仓库
                    target_item.quantity += abs(quantity)
                    if transaction.related_warehouse_id:
                        source_warehouse_items = db.query(models.InventoryItem).filter(
                            and_(
                                models.InventoryItem.warehouse_id == transaction.related_warehouse_id,
                                models.InventoryItem.category_id == category.id
                            )
                        ).all()
                        for item in source_warehouse_items:
                            if item.specs == specs:
                                item.quantity = max(0, item.quantity - abs(quantity))
                                item.updated_at = datetime.utcnow()
                                break
            
            target_item.updated_at = datetime.utcnow()
        
        return True
    except Exception as e:
        print(f"❌ 错误：应用交易影响时出错: {e}")
        import traceback
        traceback.print_exc()
        return False

def show_transaction(db: Session, transaction_id: int):
    """显示交易记录详情"""
    transaction = db.query(models.Transaction).filter(models.Transaction.id == transaction_id).first()
    if not transaction:
        print(f"❌ 交易记录 {transaction_id} 不存在")
        return
    
    warehouse = db.query(models.Warehouse).filter(models.Warehouse.id == transaction.warehouse_id).first()
    warehouse_name = warehouse.name if warehouse else f"ID: {transaction.warehouse_id}"
    
    related_warehouse_name = None
    if transaction.related_warehouse_id:
        related_warehouse = db.query(models.Warehouse).filter(models.Warehouse.id == transaction.related_warehouse_id).first()
        related_warehouse_name = related_warehouse.name if related_warehouse else f"ID: {transaction.related_warehouse_id}"
    
    parsed = parse_item_snapshot(transaction.item_name_snapshot)
    
    print(f"\n{'='*60}")
    print(f"交易记录详情 (ID: {transaction.id})")
    print(f"{'='*60}")
    print(f"类型: {transaction.type}")
    print(f"日期: {transaction.date}")
    print(f"操作人: {transaction.user}")
    print(f"备注: {transaction.notes}")
    print(f"仓库: {warehouse_name} (ID: {transaction.warehouse_id})")
    if related_warehouse_name:
        print(f"关联仓库: {related_warehouse_name} (ID: {transaction.related_warehouse_id})")
    print(f"总数量: {transaction.quantity}")
    print(f"是否已撤销: {'是' if parsed['is_reverted'] else '否'}")
    print(f"\n物品列表:")
    for idx, item in enumerate(parsed['items'], 1):
        print(f"  {idx}. {item.get('category_name', '未知')}")
        if item.get('specs'):
            print(f"     规格: {item.get('specs')}")
        print(f"     数量: {item.get('quantity', 0)} / 变动: {item.get('quantity_diff', 0)}")
    print(f"{'='*60}\n")

def delete_transaction(db: Session, transaction_id: int, reason: Optional[str] = None):
    """删除交易记录并恢复库存"""
    transaction = db.query(models.Transaction).filter(models.Transaction.id == transaction_id).first()
    if not transaction:
        print(f"❌ 交易记录 {transaction_id} 不存在")
        return False
    
    print(f"\n准备删除交易记录 {transaction_id}...")
    show_transaction(db, transaction_id)
    
    # 确认
    confirm = input("确认删除此交易记录？(输入 'yes' 确认): ")
    if confirm.lower() != 'yes':
        print("❌ 操作已取消")
        return False
    
    try:
        # 反向交易影响
        print("\n正在反向交易影响，恢复库存...")
        if not reverse_transaction_effect(db, transaction):
            print("❌ 反向交易影响失败，操作已取消")
            db.rollback()
            return False
        
        # 删除交易记录
        print("正在删除交易记录...")
        db.delete(transaction)
        db.commit()
        
        print(f"✅ 交易记录 {transaction_id} 已删除，库存已恢复")
        if reason:
            print(f"   删除原因: {reason}")
        return True
    except Exception as e:
        print(f"❌ 删除失败: {e}")
        db.rollback()
        import traceback
        traceback.print_exc()
        return False

def modify_transaction(
    db: Session,
    transaction_id: int,
    quantity: Optional[int] = None,
    user: Optional[str] = None,
    notes: Optional[str] = None,
    date: Optional[str] = None
):
    """修改交易记录并更新库存"""
    transaction = db.query(models.Transaction).filter(models.Transaction.id == transaction_id).first()
    if not transaction:
        print(f"❌ 交易记录 {transaction_id} 不存在")
        return False
    
    print(f"\n准备修改交易记录 {transaction_id}...")
    show_transaction(db, transaction_id)
    
    # 检查是否有修改
    if not any([quantity is not None, user, notes, date]):
        print("⚠️  没有指定要修改的字段")
        return False
    
    # 确认
    confirm = input("确认修改此交易记录？(输入 'yes' 确认): ")
    if confirm.lower() != 'yes':
        print("❌ 操作已取消")
        return False
    
    try:
        # 如果修改了数量，需要反向原操作，然后应用新操作
        if quantity is not None and quantity != transaction.quantity:
            print("\n正在反向原交易影响...")
            if not reverse_transaction_effect(db, transaction):
                print("❌ 反向原交易影响失败，操作已取消")
                db.rollback()
                return False
            
            # 更新数量
            transaction.quantity = quantity
            
            # 应用新操作
            print("正在应用新交易影响...")
            if not apply_transaction_effect(db, transaction):
                print("❌ 应用新交易影响失败，操作已取消")
                db.rollback()
                return False
        
        # 更新其他字段
        if user:
            transaction.user = user
        if notes:
            transaction.notes = notes
        if date:
            try:
                transaction.date = datetime.fromisoformat(date.replace('Z', '+00:00'))
            except:
                print(f"⚠️  日期格式错误，使用原日期")
        
        db.commit()
        
        print(f"✅ 交易记录 {transaction_id} 已修改")
        print("\n修改后的记录:")
        show_transaction(db, transaction_id)
        return True
    except Exception as e:
        print(f"❌ 修改失败: {e}")
        db.rollback()
        import traceback
        traceback.print_exc()
        return False

def list_transactions(
    db: Session,
    warehouse_id: Optional[int] = None,
    transaction_type: Optional[str] = None,
    limit: int = 20
):
    """列出交易记录"""
    query = db.query(models.Transaction)
    
    if warehouse_id:
        query = query.filter(
            or_(
                models.Transaction.warehouse_id == warehouse_id,
                models.Transaction.related_warehouse_id == warehouse_id
            )
        )
    
    if transaction_type:
        query = query.filter(models.Transaction.type == transaction_type)
    
    transactions = query.order_by(models.Transaction.date.desc()).limit(limit).all()
    
    print(f"\n{'='*80}")
    print(f"交易记录列表 (显示最近 {len(transactions)} 条)")
    print(f"{'='*80}")
    print(f"{'ID':<6} {'类型':<8} {'日期':<12} {'数量':<8} {'操作人':<15} {'备注':<30}")
    print(f"{'-'*80}")
    
    for t in transactions:
        notes_display = t.notes[:27] + "..." if len(t.notes) > 30 else t.notes
        date_display = t.date.strftime("%Y-%m-%d")
        print(f"{t.id:<6} {t.type:<8} {date_display:<12} {t.quantity:<8} {t.user:<15} {notes_display:<30}")
    
    print(f"{'='*80}\n")

def main():
    parser = argparse.ArgumentParser(description='交易记录管理脚本')
    subparsers = parser.add_subparsers(dest='command', help='操作命令')
    
    # delete 命令
    delete_parser = subparsers.add_parser('delete', help='删除交易记录')
    delete_parser.add_argument('transaction_id', type=int, help='交易记录 ID')
    delete_parser.add_argument('--reason', type=str, help='删除原因')
    
    # modify 命令
    modify_parser = subparsers.add_parser('modify', help='修改交易记录')
    modify_parser.add_argument('transaction_id', type=int, help='交易记录 ID')
    modify_parser.add_argument('--quantity', type=int, help='新数量')
    modify_parser.add_argument('--user', type=str, help='新操作人')
    modify_parser.add_argument('--notes', type=str, help='新备注')
    modify_parser.add_argument('--date', type=str, help='新日期 (YYYY-MM-DD 或 ISO 格式)')
    
    # show 命令
    show_parser = subparsers.add_parser('show', help='显示交易记录详情')
    show_parser.add_argument('transaction_id', type=int, help='交易记录 ID')
    
    # list 命令
    list_parser = subparsers.add_parser('list', help='列出交易记录')
    list_parser.add_argument('--warehouse', type=int, help='仓库 ID')
    list_parser.add_argument('--type', type=str, choices=['IN', 'OUT', 'ADJUST', 'TRANSFER'], help='交易类型')
    list_parser.add_argument('--limit', type=int, default=20, help='显示数量限制 (默认: 20)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    db = SessionLocal()
    try:
        if args.command == 'delete':
            delete_transaction(db, args.transaction_id, args.reason)
        elif args.command == 'modify':
            modify_transaction(
                db,
                args.transaction_id,
                quantity=args.quantity,
                user=args.user,
                notes=args.notes,
                date=args.date
            )
        elif args.command == 'show':
            show_transaction(db, args.transaction_id)
        elif args.command == 'list':
            list_transactions(
                db,
                warehouse_id=args.warehouse,
                transaction_type=args.type,
                limit=args.limit
            )
    finally:
        db.close()

if __name__ == '__main__':
    main()

