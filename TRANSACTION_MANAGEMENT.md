# 交易记录管理脚本使用说明

## 概述

`manage_transactions.py` 是一个安全的脚本，用于通过数据库直接修改或删除交易记录，同时确保整个系统的数据逻辑正确。

## 功能特性

- ✅ **安全删除**：删除交易记录时自动反向操作，恢复库存状态
- ✅ **安全修改**：修改交易记录时先反向原操作，再应用新操作
- ✅ **支持所有交易类型**：入库、出库、调整、调拨
- ✅ **处理撤销记录**：正确处理已撤销的交易记录
- ✅ **数据一致性**：确保库存数据与交易记录保持一致
- ✅ **交互式确认**：重要操作需要用户确认

## 使用方法

### 1. 查看交易记录详情

```bash
cd backend
python manage_transactions.py show <transaction_id>
```

示例：
```bash
python manage_transactions.py show 123
```

### 2. 列出交易记录

```bash
# 列出最近 20 条记录
python manage_transactions.py list

# 列出指定仓库的记录
python manage_transactions.py list --warehouse 1

# 列出指定类型的记录
python manage_transactions.py list --type IN

# 列出更多记录
python manage_transactions.py list --limit 50
```

### 3. 删除交易记录

```bash
python manage_transactions.py delete <transaction_id> [--reason "删除原因"]
```

**重要**：
- 删除前会显示交易记录详情
- 需要输入 `yes` 确认
- 删除时会自动反向操作，恢复库存状态
- 支持所有交易类型（包括撤销记录）

示例：
```bash
python manage_transactions.py delete 123 --reason "数据错误"
```

### 4. 修改交易记录

```bash
python manage_transactions.py modify <transaction_id> \
  [--quantity <新数量>] \
  [--user <新操作人>] \
  [--notes <新备注>] \
  [--date <新日期>]
```

**重要**：
- 修改数量时会自动反向原操作，然后应用新操作
- 修改其他字段（操作人、备注、日期）不会影响库存
- 需要输入 `yes` 确认

示例：
```bash
# 修改数量
python manage_transactions.py modify 123 --quantity 50

# 修改操作人和备注
python manage_transactions.py modify 123 --user "新操作人" --notes "修正备注"

# 修改日期
python manage_transactions.py modify 123 --date "2024-01-15"
```

## 工作原理

### 删除交易记录

1. 解析交易记录的物品信息
2. 根据交易类型反向操作：
   - **入库 (IN)** → 减少库存
   - **出库 (OUT)** → 增加库存
   - **调整 (ADJUST)** → 反向调整
   - **调拨 (TRANSFER)** → 反向调拨（处理两个仓库）
3. 删除交易记录
4. 提交事务

### 修改交易记录

1. 如果修改了数量：
   - 反向原交易的影响
   - 更新数量
   - 应用新交易的影响
2. 如果只修改其他字段：
   - 直接更新字段
3. 提交事务

### 处理撤销记录

- 识别撤销记录（通过 `reverted` 标志或 `MULTI_ITEM_REVERT_` 类型）
- 撤销记录的反向操作会恢复原始操作的影响

## 注意事项

⚠️ **重要警告**：

1. **备份数据**：在执行删除或修改操作前，建议先备份数据库
2. **测试环境**：建议先在测试环境验证
3. **数据一致性**：脚本会确保数据一致性，但请谨慎操作
4. **撤销记录**：删除撤销记录会恢复原始操作的影响
5. **调拨记录**：调拨记录涉及两个仓库，脚本会正确处理

## 错误处理

- 如果找不到品类或库存物品，操作会失败并回滚
- 如果库存不足（出库时），会设置为 0（不会出现负数）
- 所有错误都会显示详细信息和堆栈跟踪

## 示例场景

### 场景 1：删除错误的入库记录

```bash
# 1. 先查看记录
python manage_transactions.py show 123

# 2. 确认后删除
python manage_transactions.py delete 123 --reason "录入错误"
# 系统会自动减少相应库存
```

### 场景 2：修正出库数量

```bash
# 1. 查看记录
python manage_transactions.py show 123

# 2. 修改数量（从 10 改为 5）
python manage_transactions.py modify 123 --quantity 5
# 系统会：
# - 先恢复原出库（增加 10）
# - 再应用新出库（减少 5）
# - 最终效果：库存增加 5
```

### 场景 3：修正操作人信息

```bash
# 只修改操作人，不影响库存
python manage_transactions.py modify 123 --user "正确的操作人"
```

## 技术细节

- 使用 SQLAlchemy ORM 进行数据库操作
- 支持新旧两种交易记录格式
- 自动处理多物品交易记录
- 事务保证：操作失败时自动回滚

