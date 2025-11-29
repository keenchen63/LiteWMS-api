from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime

# Category Schemas
class AttributeDefinition(BaseModel):
    name: str
    options: List[str]

class CategoryBase(BaseModel):
    name: str
    attributes: List[AttributeDefinition]

class CategoryCreate(CategoryBase):
    pass

class CategoryUpdate(CategoryBase):
    pass

class Category(CategoryBase):
    id: int
    
    class Config:
        from_attributes = True

# Warehouse Schemas
class WarehouseBase(BaseModel):
    name: str

class WarehouseCreate(WarehouseBase):
    pass

class WarehouseUpdate(WarehouseBase):
    pass

class Warehouse(WarehouseBase):
    id: int
    
    class Config:
        from_attributes = True

# Inventory Item Schemas
class InventoryItemBase(BaseModel):
    warehouse_id: int
    category_id: int
    specs: Dict[str, str]
    quantity: int

class InventoryItemCreate(InventoryItemBase):
    pass

class InventoryItemUpdate(BaseModel):
    quantity: Optional[int] = None
    specs: Optional[Dict[str, str]] = None

class InventoryItem(InventoryItemBase):
    id: int
    updated_at: datetime
    
    class Config:
        from_attributes = True

class InventoryItemWithCategory(InventoryItem):
    category_name: str

# Transaction Schemas
class TransactionBase(BaseModel):
    warehouse_id: int
    item_id: int
    item_name_snapshot: str
    quantity: int
    date: datetime
    user: str
    notes: str
    type: str  # 'IN', 'OUT', 'ADJUST', 'TRANSFER'

class TransactionCreate(TransactionBase):
    related_warehouse_id: Optional[int] = None

class Transaction(TransactionBase):
    id: int
    related_warehouse_id: Optional[int] = None
    
    class Config:
        from_attributes = True

