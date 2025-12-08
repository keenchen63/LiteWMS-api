# 数据库备份与恢复脚本使用说明

## 概述

提供了两个脚本用于数据库的备份和恢复：
- `backup_database.py` - 数据库备份脚本
- `restore_database.py` - 数据库恢复脚本

## 前置要求

### 1. PostgreSQL 客户端工具

需要安装 PostgreSQL 客户端工具（`pg_dump` 和 `pg_restore` 或 `psql`）：

**macOS:**
```bash
brew install postgresql
```

**Ubuntu/Debian:**
```bash
sudo apt-get install postgresql-client
```

**CentOS/RHEL:**
```bash
sudo yum install postgresql
```

### 2. 数据库连接配置

脚本会自动从 `app.config.settings.DATABASE_URL` 读取数据库连接信息。

## 备份脚本 (`backup_database.py`)

### 基本用法

```bash
cd backend
python backup_database.py
```

默认会创建 `backups/db_backup_YYYYMMDD_HHMMSS.sql` 文件。

### 选项

- `--output, -o`: 指定备份文件输出路径
- `--format, -f`: 备份格式
  - `plain` (默认): SQL 文本格式，可读性强
  - `custom`: 压缩二进制格式，体积小
  - `directory`: 目录格式
  - `tar`: tar 格式
- `--compress`: 对 plain 格式启用压缩

### 示例

```bash
# 使用默认设置备份
python backup_database.py

# 指定输出路径
python backup_database.py --output /path/to/backup.sql

# 使用 custom 格式（压缩）
python backup_database.py --format custom --output backup.dump

# 使用 plain 格式并压缩
python backup_database.py --format plain --compress --output backup.sql.gz
```

### 备份格式说明

1. **plain (SQL 文本格式)**
   - 优点：可读性强，可以用文本编辑器查看
   - 缺点：文件较大
   - 适用：小数据库，需要查看备份内容

2. **custom (压缩二进制格式)**
   - 优点：体积小，恢复速度快
   - 缺点：不可读
   - 适用：生产环境，大数据库

3. **directory (目录格式)**
   - 优点：可以并行恢复，灵活
   - 缺点：文件较多
   - 适用：超大数据库

4. **tar (tar 格式)**
   - 优点：单文件，可压缩
   - 缺点：恢复较慢
   - 适用：中等规模数据库

## 恢复脚本 (`restore_database.py`)

### 基本用法

```bash
cd backend
python restore_database.py <备份文件路径>
```

### 选项

- `--drop-existing`: 删除现有数据库并重新创建（危险操作）
- `--create-db`: 如果数据库不存在则创建

### 示例

```bash
# 从 SQL 备份恢复
python restore_database.py backups/db_backup_20240101_120000.sql

# 从 custom 格式备份恢复
python restore_database.py backups/db_backup_20240101_120000.dump

# 删除现有数据库并恢复
python restore_database.py backups/db_backup_20240101_120000.sql --drop-existing

# 如果数据库不存在则创建
python restore_database.py backups/db_backup_20240101_120000.sql --create-db
```

### 注意事项

⚠️ **重要警告**：

1. **备份现有数据**：恢复操作会覆盖现有数据，请先备份
2. **确认备份文件**：确保备份文件完整且有效
3. **数据库连接**：确保数据库服务正在运行
4. **权限问题**：确保数据库用户有足够的权限
5. **`--drop-existing` 选项**：会删除整个数据库，请谨慎使用

## 自动化备份

### 定时备份（Linux/macOS）

使用 `cron` 设置定时备份：

```bash
# 编辑 crontab
crontab -e

# 每天凌晨 2 点备份
0 2 * * * cd /path/to/backend && python backup_database.py --format custom
```

### 备份保留策略

建议定期清理旧备份，只保留最近的几个：

```bash
# 只保留最近 7 天的备份
find backups/ -name "db_backup_*.sql" -mtime +7 -delete
find backups/ -name "db_backup_*.dump" -mtime +7 -delete
```

## 完整备份恢复流程示例

### 1. 备份数据库

```bash
cd backend
python backup_database.py --format custom --output backups/production_backup.dump
```

### 2. 验证备份文件

```bash
# 检查文件是否存在
ls -lh backups/production_backup.dump

# 对于 custom 格式，可以查看备份内容
pg_restore --list backups/production_backup.dump
```

### 3. 恢复数据库

```bash
# 方法 1: 删除并重建（生产环境谨慎使用）
python restore_database.py backups/production_backup.dump --drop-existing

# 方法 2: 如果数据库不存在则创建
python restore_database.py backups/production_backup.dump --create-db
```

## 故障排除

### 问题 1: `pg_dump: command not found`

**解决方案**：安装 PostgreSQL 客户端工具（见前置要求）

### 问题 2: `FATAL: password authentication failed`

**解决方案**：
- 检查 `DATABASE_URL` 配置是否正确
- 确保数据库用户密码正确
- 检查 PostgreSQL 的 `pg_hba.conf` 配置

### 问题 3: `permission denied`

**解决方案**：
- 确保数据库用户有足够的权限
- 对于 `--drop-existing`，需要 `CREATEDB` 权限

### 问题 4: 备份文件过大

**解决方案**：
- 使用 `custom` 格式（自动压缩）
- 使用 `--compress` 选项（仅 plain 格式）

### 问题 5: 恢复时表已存在错误

**解决方案**：
- 使用 `--drop-existing` 选项
- 或手动删除现有数据库

## 最佳实践

1. **定期备份**：设置自动定时备份
2. **测试恢复**：定期测试备份文件是否可以正常恢复
3. **异地备份**：将备份文件复制到其他位置
4. **版本控制**：为备份文件添加版本标识
5. **监控备份**：确保备份任务成功执行
6. **保留策略**：制定备份保留策略，避免占用过多空间

## 备份文件命名建议

建议使用以下命名格式：
- `db_backup_YYYYMMDD_HHMMSS.sql` - 日期时间
- `db_backup_production_YYYYMMDD.dump` - 环境 + 日期
- `db_backup_v1.0_YYYYMMDD.dump` - 版本 + 日期

