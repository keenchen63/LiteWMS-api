from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app import models, schemas

router = APIRouter()

@router.get("/", response_model=List[schemas.Warehouse])
def get_warehouses(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    warehouses = db.query(models.Warehouse).offset(skip).limit(limit).all()
    return warehouses

@router.get("/{warehouse_id}", response_model=schemas.Warehouse)
def get_warehouse(warehouse_id: int, db: Session = Depends(get_db)):
    warehouse = db.query(models.Warehouse).filter(models.Warehouse.id == warehouse_id).first()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    return warehouse

@router.post("/", response_model=schemas.Warehouse)
def create_warehouse(warehouse: schemas.WarehouseCreate, db: Session = Depends(get_db)):
    db_warehouse = models.Warehouse(**warehouse.dict())
    db.add(db_warehouse)
    db.commit()
    db.refresh(db_warehouse)
    return db_warehouse

@router.put("/{warehouse_id}", response_model=schemas.Warehouse)
def update_warehouse(warehouse_id: int, warehouse: schemas.WarehouseUpdate, db: Session = Depends(get_db)):
    db_warehouse = db.query(models.Warehouse).filter(models.Warehouse.id == warehouse_id).first()
    if not db_warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    
    for key, value in warehouse.dict().items():
        setattr(db_warehouse, key, value)
    
    db.commit()
    db.refresh(db_warehouse)
    return db_warehouse

@router.delete("/{warehouse_id}")
def delete_warehouse(warehouse_id: int, db: Session = Depends(get_db)):
    db_warehouse = db.query(models.Warehouse).filter(models.Warehouse.id == warehouse_id).first()
    if not db_warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    
    # Check if warehouse has items
    item_count = db.query(models.InventoryItem).filter(models.InventoryItem.warehouse_id == warehouse_id).count()
    if item_count > 0:
        raise HTTPException(status_code=400, detail=f"Warehouse has {item_count} items, cannot delete")
    
    db.delete(db_warehouse)
    db.commit()
    return {"message": "Warehouse deleted successfully"}

