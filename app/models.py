from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Numeric
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime

class Category(Base):
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    attributes = Column(JSON, nullable=False)  # List of AttributeDefinition
    
    items = relationship("InventoryItem", back_populates="category")

class Warehouse(Base):
    __tablename__ = "warehouses"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    
    items = relationship("InventoryItem", back_populates="warehouse")
    transactions = relationship(
        "Transaction", 
        primaryjoin="Warehouse.id == Transaction.warehouse_id",
        back_populates="warehouse"
    )

class InventoryItem(Base):
    __tablename__ = "items"
    
    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False, index=True)
    specs = Column(JSON, nullable=False)  # Record<string, string>
    quantity = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    category = relationship("Category", back_populates="items")
    warehouse = relationship("Warehouse", back_populates="items")
    transactions = relationship("Transaction", back_populates="item")

class Transaction(Base):
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    related_warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False, index=True)
    item_name_snapshot = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)  # Negative for outbound, Positive for inbound
    date = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    user = Column(String, nullable=False)
    notes = Column(String, nullable=False, default="")
    type = Column(String, nullable=False)  # 'IN', 'OUT', 'ADJUST', 'TRANSFER'
    
    warehouse = relationship("Warehouse", foreign_keys=[warehouse_id], back_populates="transactions")
    item = relationship("InventoryItem", back_populates="transactions")

class Admin(Base):
    __tablename__ = "admin"
    
    id = Column(Integer, primary_key=True, index=True)
    password_hash = Column(String, nullable=True)  # NULL means password not set yet
    totp_secret = Column(JSON, nullable=True)  # Changed to JSON to store array of secrets: [{"secret": "...", "name": "设备1", "created_at": "..."}, ...]
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

