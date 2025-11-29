from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional
from app.database import get_db
from app import models, schemas

router = APIRouter()

@router.get("/", response_model=List[schemas.InventoryItem])
def get_items(
    warehouse_id: Optional[int] = None,
    category_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 1000,
    db: Session = Depends(get_db)
):
    query = db.query(models.InventoryItem)
    
    if warehouse_id:
        query = query.filter(models.InventoryItem.warehouse_id == warehouse_id)
    if category_id:
        query = query.filter(models.InventoryItem.category_id == category_id)
    
    items = query.offset(skip).limit(limit).all()
    return items

@router.get("/with-category", response_model=List[schemas.InventoryItemWithCategory])
def get_items_with_category(
    warehouse_id: Optional[int] = None,
    category_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 1000,
    db: Session = Depends(get_db)
):
    query = db.query(
        models.InventoryItem,
        models.Category.name.label('category_name')
    ).join(models.Category, models.InventoryItem.category_id == models.Category.id)
    
    if warehouse_id:
        query = query.filter(models.InventoryItem.warehouse_id == warehouse_id)
    if category_id:
        query = query.filter(models.InventoryItem.category_id == category_id)
    
    results = query.offset(skip).limit(limit).all()
    
    items = []
    for item, category_name in results:
        item_dict = {
            "id": item.id,
            "warehouse_id": item.warehouse_id,
            "category_id": item.category_id,
            "specs": item.specs,
            "quantity": item.quantity,
            "updated_at": item.updated_at,
            "category_name": category_name
        }
        items.append(item_dict)
    
    return items

@router.get("/{item_id}", response_model=schemas.InventoryItem)
def get_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(models.InventoryItem).filter(models.InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@router.post("/", response_model=schemas.InventoryItem)
def create_item(item: schemas.InventoryItemCreate, db: Session = Depends(get_db)):
    # Check if item with same specs exists in the warehouse
    existing_items = db.query(models.InventoryItem).filter(
        and_(
            models.InventoryItem.warehouse_id == item.warehouse_id,
            models.InventoryItem.category_id == item.category_id
        )
    ).all()
    
    for existing in existing_items:
        if existing.specs == item.specs:
            # Update quantity
            existing.quantity += item.quantity
            from datetime import datetime
            existing.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(existing)
            return existing
    
    # Create new item
    db_item = models.InventoryItem(**item.dict())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

@router.put("/{item_id}", response_model=schemas.InventoryItem)
def update_item(item_id: int, item_update: schemas.InventoryItemUpdate, db: Session = Depends(get_db)):
    db_item = db.query(models.InventoryItem).filter(models.InventoryItem.id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    for key, value in item_update.dict(exclude_unset=True).items():
        setattr(db_item, key, value)
    
    from datetime import datetime
    db_item.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(db_item)
    return db_item

@router.delete("/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    db_item = db.query(models.InventoryItem).filter(models.InventoryItem.id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    # Delete related transactions first
    db.query(models.Transaction).filter(models.Transaction.item_id == item_id).delete()
    
    # Then delete the item
    db.delete(db_item)
    db.commit()
    return {"message": "Item deleted successfully"}

