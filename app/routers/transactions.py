from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import List, Optional
from datetime import datetime, date
from pydantic import BaseModel
from app.database import get_db
from app import models, schemas

router = APIRouter()

@router.get("/", response_model=List[schemas.Transaction])
def get_transactions(
    warehouse_id: Optional[int] = None,
    transaction_type: Optional[str] = None,
    filter_date: Optional[str] = None,
    skip: int = 0,
    limit: int = 1000,
    db: Session = Depends(get_db)
):
    query = db.query(models.Transaction)
    
    if warehouse_id:
        # Include transactions where warehouse_id matches OR related_warehouse_id matches
        query = query.filter(
            or_(
                models.Transaction.warehouse_id == warehouse_id,
                models.Transaction.related_warehouse_id == warehouse_id
            )
        )
    
    if transaction_type:
        query = query.filter(models.Transaction.type == transaction_type)
    
    if filter_date:
        filter_dt = datetime.fromisoformat(filter_date)
        next_day = datetime(filter_dt.year, filter_dt.month, filter_dt.day, 23, 59, 59)
        query = query.filter(
            and_(
                models.Transaction.date >= filter_dt,
                models.Transaction.date <= next_day
            )
        )
    
    transactions = query.order_by(models.Transaction.date.desc()).offset(skip).limit(limit).all()
    return transactions

@router.get("/{transaction_id}", response_model=schemas.Transaction)
def get_transaction(transaction_id: int, db: Session = Depends(get_db)):
    transaction = db.query(models.Transaction).filter(models.Transaction.id == transaction_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction

@router.post("/", response_model=schemas.Transaction)
def create_transaction(transaction: schemas.TransactionCreate, db: Session = Depends(get_db)):
    db_transaction = models.Transaction(**transaction.dict())
    db.add(db_transaction)
    db.commit()
    db.refresh(db_transaction)
    return db_transaction

@router.delete("/{transaction_id}")
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    db_transaction = db.query(models.Transaction).filter(models.Transaction.id == transaction_id).first()
    if not db_transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    db.delete(db_transaction)
    db.commit()
    return {"message": "Transaction deleted successfully"}

class RevertTransactionRequest(BaseModel):
    user: str
    notes: str

@router.post("/{transaction_id}/revert", response_model=schemas.Transaction)
def revert_transaction(transaction_id: int, request: RevertTransactionRequest, db: Session = Depends(get_db)):
    """
    撤销交易记录：更新原有记录为撤销状态，并执行反向操作来撤回该交易的所有影响
    """
    import json
    
    # 获取原始交易记录
    original_transaction = db.query(models.Transaction).filter(models.Transaction.id == transaction_id).first()
    if not original_transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    # 检查是否已经被撤销
    try:
        parsed = json.loads(original_transaction.item_name_snapshot)
        if isinstance(parsed, dict) and parsed.get('type', '').startswith('MULTI_ITEM_REVERT_'):
            raise HTTPException(status_code=400, detail="该记录已经被撤销，无法再次撤销")
        if isinstance(parsed, dict) and parsed.get('reverted', False):
            raise HTTPException(status_code=400, detail="该记录已经被撤销，无法再次撤销")
    except (json.JSONDecodeError, AttributeError):
        # 旧格式，继续处理
        pass
    
    # 解析物品信息（保存原始数据用于显示）
    original_items = []
    try:
        parsed = json.loads(original_transaction.item_name_snapshot)
        if isinstance(parsed, dict) and 'items' in parsed and isinstance(parsed['items'], list):
            items = parsed['items']
            original_items = parsed['items']  # 保存原始数据
        elif isinstance(parsed, dict) and 'original_items' in parsed and isinstance(parsed['original_items'], list):
            # 如果已经是撤销记录，使用 original_items
            items = parsed['original_items']
            original_items = parsed['original_items']
        else:
            # 旧格式：单物品
            items = [{
                'category_name': original_transaction.item_name_snapshot.split(' - ')[0] if ' - ' in original_transaction.item_name_snapshot else original_transaction.item_name_snapshot,
                'specs': json.loads(original_transaction.item_name_snapshot.split(' - ')[1]) if ' - ' in original_transaction.item_name_snapshot else {},
                'quantity': original_transaction.quantity,
                'quantity_diff': original_transaction.quantity
            }]
            original_items = items.copy()
    except:
        # 解析失败，使用原始数据
        items = [{
            'category_name': original_transaction.item_name_snapshot,
            'specs': {},
            'quantity': original_transaction.quantity,
            'quantity_diff': original_transaction.quantity
        }]
        original_items = items.copy()
    
    # 根据交易类型执行反向操作
    revert_items = []
    total_revert_quantity = 0
    
    for item_data in items:
        specs = item_data.get('specs', {})
        quantity = item_data.get('quantity', 0) or item_data.get('quantity_diff', 0)
        category_name = item_data.get('category_name', '')
        
        # 查找对应的品类
        category = db.query(models.Category).filter(models.Category.name == category_name).first()
        if not category:
            raise HTTPException(status_code=404, detail=f"Category '{category_name}' not found")
        
        # 查找对应的库存物品（根据仓库、品类和规格）
        warehouse_items = db.query(models.InventoryItem).filter(
            and_(
                models.InventoryItem.warehouse_id == original_transaction.warehouse_id,
                models.InventoryItem.category_id == category.id
            )
        ).all()
        
        # 找到规格匹配的物品
        target_item = None
        for item in warehouse_items:
            if item.specs == specs:
                target_item = item
                break
        
        if not target_item:
            raise HTTPException(
                status_code=404, 
                detail=f"Item not found: category={category_name}, specs={specs}, warehouse_id={original_transaction.warehouse_id}"
            )
        
        # 根据交易类型执行反向操作
        if original_transaction.type == 'IN':
            # 入库 -> 出库（减少库存）
            revert_quantity = -abs(quantity)
            target_item.quantity = max(0, target_item.quantity - abs(quantity))
        elif original_transaction.type == 'OUT':
            # 出库 -> 入库（增加库存）
            revert_quantity = abs(quantity)
            target_item.quantity += abs(quantity)
        elif original_transaction.type == 'ADJUST':
            # 调整 -> 反向调整
            # ADJUST类型的quantity就是变化量（quantity_diff）
            quantity_diff = item_data.get('quantity_diff', quantity)
            # 反向调整：如果原来是增加，现在减少；如果原来是减少，现在增加
            revert_quantity = -quantity_diff
            target_item.quantity = max(0, target_item.quantity - quantity_diff)
        elif original_transaction.type == 'TRANSFER':
            # 调拨 -> 反向调拨
            if original_transaction.quantity < 0:
                # 调拨出 -> 调拨入（增加当前仓库库存）
                revert_quantity = abs(quantity)
                target_item.quantity += abs(quantity)
                
                # 如果有目标仓库，也需要处理目标仓库的库存
                if original_transaction.related_warehouse_id:
                    target_warehouse_items = db.query(models.InventoryItem).filter(
                        and_(
                            models.InventoryItem.warehouse_id == original_transaction.related_warehouse_id,
                            models.InventoryItem.category_id == category.id
                        )
                    ).all()
                    target_warehouse_item = None
                    for item in target_warehouse_items:
                        if item.specs == specs:
                            target_warehouse_item = item
                            break
                    if target_warehouse_item:
                        target_warehouse_item.quantity = max(0, target_warehouse_item.quantity - abs(quantity))
                        target_warehouse_item.updated_at = datetime.utcnow()
            else:
                # 调拨入 -> 调拨出（减少当前仓库库存）
                revert_quantity = -abs(quantity)
                target_item.quantity = max(0, target_item.quantity - abs(quantity))
                
                # 如果有源仓库，也需要处理源仓库的库存
                if original_transaction.related_warehouse_id:
                    source_warehouse_items = db.query(models.InventoryItem).filter(
                        and_(
                            models.InventoryItem.warehouse_id == original_transaction.related_warehouse_id,
                            models.InventoryItem.category_id == category.id
                        )
                    ).all()
                    source_warehouse_item = None
                    for item in source_warehouse_items:
                        if item.specs == specs:
                            source_warehouse_item = item
                            break
                    if source_warehouse_item:
                        source_warehouse_item.quantity += abs(quantity)
                        source_warehouse_item.updated_at = datetime.utcnow()
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported transaction type: {original_transaction.type}")
        
        target_item.updated_at = datetime.utcnow()
        total_revert_quantity += revert_quantity
        
        revert_items.append({
            'category_name': category_name,
            'specs': specs,
            'quantity': abs(revert_quantity),
            'quantity_diff': revert_quantity
        })
    
    # 更新原有记录为撤销状态
    # 保留原始数据，但添加撤销标记
    try:
        original_parsed = json.loads(original_transaction.item_name_snapshot)
        if not isinstance(original_parsed, dict):
            original_parsed = {}
    except (json.JSONDecodeError, AttributeError):
        original_parsed = {}
    
    # 更新 item_name_snapshot，添加撤销标记和撤销信息
    updated_snapshot = {
        'type': f'MULTI_ITEM_REVERT_{original_transaction.type}',
        'items': revert_items,  # 撤销操作的数据（用于库存操作）
        'total_quantity': abs(total_revert_quantity),
        'total_quantity_diff': total_revert_quantity,
        'reverted': True,
        'reverted_at': datetime.utcnow().isoformat(),
        'reverted_by': request.user,
        'revert_notes': request.notes,
        # 保留原始数据用于显示
        'original_items': original_items,  # 原始物品数据
        'original_type': original_transaction.type,
        'original_quantity': original_transaction.quantity,
        'original_total_quantity': abs(original_transaction.quantity) if original_transaction.quantity != 0 else 0
    }
    
    # 更新原有记录
    original_transaction.item_name_snapshot = json.dumps(updated_snapshot)
    original_transaction.quantity = total_revert_quantity  # 更新数量为反向数量
    original_transaction.user = request.user  # 更新操作人为撤销操作人
    original_transaction.notes = f"撤销操作：{request.notes}"  # 更新备注为撤销备注
    # 保持 date 不变，确保记录位置不变
    
    db.commit()
    db.refresh(original_transaction)
    
    return original_transaction

