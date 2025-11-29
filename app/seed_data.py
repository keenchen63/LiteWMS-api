"""
初始化数据库种子数据
"""
from app.database import SessionLocal
from app import models
from datetime import datetime

def seed_data():
    db = SessionLocal()
    
    try:
        # Check if data already exists
        if db.query(models.Warehouse).count() > 0:
            print("数据已存在，跳过种子数据初始化")
            return
        
        # 1. 创建仓库
        wh_a = models.Warehouse(name="仓库 A (Warehouse A)")
        wh_b = models.Warehouse(name="仓库 B (Warehouse B)")
        db.add(wh_a)
        db.add(wh_b)
        db.flush()  # 获取 ID
        
        # 2. 创建品类
        fiber_cat = models.Category(
            name="光纤跳线 (Fiber)",
            attributes=[
                {"name": "模式 (Mode)", "options": ["单模 (SM)", "多模 (MM)", "OM3", "OM4", "OS2"]},
                {"name": "接口类型 (Interface)", "options": ["LC-LC", "SC-SC", "LC-SC", "FC-FC", "ST-ST"]},
                {"name": "长度 (Length)", "options": ["1m", "2m", "3m", "5m", "10m", "15m", "20m", "30m"]},
                {"name": "极性 (Polarity)", "options": ["A-B", "A-A"]}
            ]
        )
        
        copper_cat = models.Category(
            name="网线 (Copper)",
            attributes=[
                {"name": "类型 (Cat)", "options": ["Cat5e", "Cat6", "Cat6a", "Cat7", "Cat8"]},
                {"name": "长度 (Length)", "options": ["0.5m", "1m", "2m", "3m", "5m", "10m", "15m", "20m"]},
                {"name": "颜色 (Color)", "options": ["蓝色", "黄色", "灰色", "红色", "绿色", "黑色"]},
                {"name": "屏蔽 (Shielding)", "options": ["UTP", "STP", "SFTP"]}
            ]
        )
        
        mpo_cat = models.Category(
            name="MPO主干光纤 (MPO)",
            attributes=[
                {"name": "芯数 (Cores)", "options": ["8芯", "12芯", "16芯", "24芯"]},
                {"name": "接头性别 (Gender)", "options": ["公头-公头 (Male-Male)", "母头-母头 (Female-Female)", "公头-母头 (Male-Female)"]},
                {"name": "极性 (Polarity)", "options": ["Type A", "Type B", "Type C"]},
                {"name": "模式 (Mode)", "options": ["OM3", "OM4", "OS2"]},
                {"name": "长度 (Length)", "options": ["3m", "5m", "10m", "15m", "20m", "30m", "50m"]}
            ]
        )
        
        db.add(fiber_cat)
        db.add(copper_cat)
        db.add(mpo_cat)
        db.flush()
        
        # 3. 创建库存项
        items_data = [
            # Fiber Items
            {
                "category_id": fiber_cat.id,
                "warehouse_id": wh_a.id,
                "specs": {"模式 (Mode)": "OM3", "接口类型 (Interface)": "LC-LC", "长度 (Length)": "3m", "极性 (Polarity)": "A-B"},
                "quantity": 120
            },
            {
                "category_id": fiber_cat.id,
                "warehouse_id": wh_a.id,
                "specs": {"模式 (Mode)": "单模 (SM)", "接口类型 (Interface)": "SC-SC", "长度 (Length)": "10m", "极性 (Polarity)": "A-B"},
                "quantity": 50
            },
            {
                "category_id": fiber_cat.id,
                "warehouse_id": wh_a.id,
                "specs": {"模式 (Mode)": "OM4", "接口类型 (Interface)": "LC-SC", "长度 (Length)": "5m", "极性 (Polarity)": "A-A"},
                "quantity": 75
            },
            {
                "category_id": fiber_cat.id,
                "warehouse_id": wh_a.id,
                "specs": {"模式 (Mode)": "多模 (MM)", "接口类型 (Interface)": "FC-FC", "长度 (Length)": "2m", "极性 (Polarity)": "A-B"},
                "quantity": 30
            },
            {
                "category_id": fiber_cat.id,
                "warehouse_id": wh_a.id,
                "specs": {"模式 (Mode)": "OS2", "接口类型 (Interface)": "LC-LC", "长度 (Length)": "15m", "极性 (Polarity)": "A-B"},
                "quantity": 200
            },
            # Copper Items
            {
                "category_id": copper_cat.id,
                "warehouse_id": wh_a.id,
                "specs": {"类型 (Cat)": "Cat6", "长度 (Length)": "1m", "颜色 (Color)": "蓝色", "屏蔽 (Shielding)": "UTP"},
                "quantity": 500
            },
            {
                "category_id": copper_cat.id,
                "warehouse_id": wh_a.id,
                "specs": {"类型 (Cat)": "Cat6", "长度 (Length)": "3m", "颜色 (Color)": "黄色", "屏蔽 (Shielding)": "UTP"},
                "quantity": 300
            },
            {
                "category_id": copper_cat.id,
                "warehouse_id": wh_a.id,
                "specs": {"类型 (Cat)": "Cat6a", "长度 (Length)": "5m", "颜色 (Color)": "灰色", "屏蔽 (Shielding)": "STP"},
                "quantity": 150
            },
            {
                "category_id": copper_cat.id,
                "warehouse_id": wh_a.id,
                "specs": {"类型 (Cat)": "Cat5e", "长度 (Length)": "2m", "颜色 (Color)": "红色", "屏蔽 (Shielding)": "UTP"},
                "quantity": 100
            },
            {
                "category_id": copper_cat.id,
                "warehouse_id": wh_a.id,
                "specs": {"类型 (Cat)": "Cat7", "长度 (Length)": "10m", "颜色 (Color)": "黑色", "屏蔽 (Shielding)": "SFTP"},
                "quantity": 40
            },
            # MPO Items
            {
                "category_id": mpo_cat.id,
                "warehouse_id": wh_a.id,
                "specs": {"芯数 (Cores)": "12芯", "接头性别 (Gender)": "母头-母头 (Female-Female)", "极性 (Polarity)": "Type B", "模式 (Mode)": "OM3", "长度 (Length)": "5m"},
                "quantity": 20
            },
            {
                "category_id": mpo_cat.id,
                "warehouse_id": wh_a.id,
                "specs": {"芯数 (Cores)": "12芯", "接头性别 (Gender)": "公头-公头 (Male-Male)", "极性 (Polarity)": "Type A", "模式 (Mode)": "OM4", "长度 (Length)": "10m"},
                "quantity": 15
            },
            {
                "category_id": mpo_cat.id,
                "warehouse_id": wh_a.id,
                "specs": {"芯数 (Cores)": "24芯", "接头性别 (Gender)": "公头-母头 (Male-Female)", "极性 (Polarity)": "Type B", "模式 (Mode)": "OM4", "长度 (Length)": "3m"},
                "quantity": 8
            },
            {
                "category_id": mpo_cat.id,
                "warehouse_id": wh_a.id,
                "specs": {"芯数 (Cores)": "8芯", "接头性别 (Gender)": "母头-母头 (Female-Female)", "极性 (Polarity)": "Type B", "模式 (Mode)": "OS2", "长度 (Length)": "15m"},
                "quantity": 5
            },
            {
                "category_id": mpo_cat.id,
                "warehouse_id": wh_a.id,
                "specs": {"芯数 (Cores)": "12芯", "接头性别 (Gender)": "母头-母头 (Female-Female)", "极性 (Polarity)": "Type C", "模式 (Mode)": "OM3", "长度 (Length)": "30m"},
                "quantity": 10
            }
        ]
        
        for item_data in items_data:
            item = models.InventoryItem(**item_data, updated_at=datetime.utcnow())
            db.add(item)
        
        db.commit()
        print("种子数据初始化成功！")
        
    except Exception as e:
        db.rollback()
        print(f"种子数据初始化失败: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()

