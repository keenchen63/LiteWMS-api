from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import List, Optional
from datetime import datetime, date
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

