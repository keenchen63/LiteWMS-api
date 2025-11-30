# 故障排查指南

## 数据库迁移错误

### 错误：`column admin.mfa_enabled does not exist`

#### 问题诊断

这个错误发生在添加了新的 `mfa_enabled` 字段后，但数据库表还没有更新。

#### 解决步骤

##### 方法一：使用迁移脚本（推荐）

```bash
cd backend
python3 add_mfa_enabled_column.py
```

##### 方法二：手动执行 SQL

连接到数据库并执行：

```bash
# 连接到数据库
psql -U your_username -d your_database

# 执行 SQL
ALTER TABLE admin ADD COLUMN mfa_enabled BOOLEAN NOT NULL DEFAULT TRUE;
\q
```

或者使用一行命令：

```bash
psql -U your_username -d your_database -c "ALTER TABLE admin ADD COLUMN mfa_enabled BOOLEAN NOT NULL DEFAULT TRUE;"
```

##### 验证

```bash
# 检查字段是否添加成功
psql -U your_username -d your_database -c "\d admin"
```

应该能看到 `mfa_enabled` 字段。

## 数据库权限错误

### 错误：`permission denied for schema public`

#### 问题诊断

这个错误通常发生在 **PostgreSQL 15+** 版本中，因为从 PostgreSQL 15 开始，`public` schema 的默认权限发生了变化。普通用户不再自动拥有在 `public` schema 中创建对象的权限。

#### 解决步骤

##### 方法一：授予 public schema 权限（推荐）

```bash
# 切换到 postgres 用户
sudo -u postgres psql -d inventory_db

# 在 PostgreSQL 中执行
GRANT ALL ON SCHEMA public TO inventory_user;
GRANT CREATE ON SCHEMA public TO inventory_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO inventory_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO inventory_user;
\q
```

**如果使用不同的用户名，替换 `inventory_user` 为实际用户名。**

##### 方法二：授予数据库所有者权限

```bash
sudo -u postgres psql -d inventory_db

# 在 PostgreSQL 中执行
ALTER DATABASE inventory_db OWNER TO inventory_user;
\q
```

##### 方法三：使用超级用户创建表（临时方案）

如果上述方法不行，可以临时使用 postgres 用户：

```bash
sudo -u postgres psql -d inventory_db

# 在 PostgreSQL 中执行
GRANT ALL PRIVILEGES ON DATABASE inventory_db TO inventory_user;
GRANT ALL ON SCHEMA public TO inventory_user;
ALTER SCHEMA public OWNER TO inventory_user;
\q
```

##### 方法四：创建专用 Schema（高级方案）

```bash
sudo -u postgres psql -d inventory_db

# 在 PostgreSQL 中执行
CREATE SCHEMA inventory;
GRANT ALL ON SCHEMA inventory TO inventory_user;
ALTER USER inventory_user SET search_path TO inventory, public;
\q
```

然后修改应用的数据库连接字符串，在连接参数中添加 `options=-csearch_path=inventory`。

#### 验证权限

```bash
# 连接到数据库
psql -U inventory_user -d inventory_db

# 在 PostgreSQL 中执行
\dn+  # 查看 schema 权限
\du   # 查看用户权限
```

#### 完整修复脚本

```bash
#!/bin/bash
# fix_db_permissions.sh

DB_USER="inventory_user"  # 替换为你的实际用户名
DB_NAME="inventory_db"    # 替换为你的实际数据库名

echo "修复数据库权限..."

sudo -u postgres psql -d $DB_NAME <<EOF
-- 授予 schema 权限
GRANT ALL ON SCHEMA public TO $DB_USER;
GRANT CREATE ON SCHEMA public TO $DB_USER;

-- 授予默认权限
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $DB_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO $DB_USER;

-- 授予数据库权限
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;

-- 如果是数据库所有者，授予所有权限
ALTER DATABASE $DB_NAME OWNER TO $DB_USER;
EOF

echo "权限修复完成！"
echo "现在可以重新运行应用：python3 run.py"
```

## 数据库连接错误

### 错误：`password authentication failed for user "inventory_db"`

#### 问题诊断

这个错误通常由以下原因引起：

1. **数据库用户不存在**
2. **密码不正确**
3. **`.env` 文件中的 `DATABASE_URL` 配置错误**

#### 解决步骤

##### 1. 检查 PostgreSQL 服务状态

```bash
# 检查 PostgreSQL 是否运行
sudo systemctl status postgresql

# 如果未运行，启动服务
sudo systemctl start postgresql
```

##### 2. 检查数据库用户是否存在

```bash
# 切换到 postgres 用户
sudo -u postgres psql

# 在 PostgreSQL 中执行
\du

# 查看所有用户列表，确认是否有 "inventory_db" 用户
```

##### 3. 创建或重置数据库用户

**如果用户不存在，创建用户：**

```bash
sudo -u postgres psql

# 在 PostgreSQL 中执行
CREATE USER inventory_db WITH PASSWORD 'your_strong_password_here';
ALTER USER inventory_db CREATEDB;
\q
```

**如果用户已存在，重置密码：**

```bash
sudo -u postgres psql

# 在 PostgreSQL 中执行
ALTER USER inventory_db WITH PASSWORD 'your_new_password_here';
\q
```

##### 4. 创建数据库

```bash
sudo -u postgres psql

# 在 PostgreSQL 中执行
CREATE DATABASE inventory_db OWNER inventory_db;
GRANT ALL PRIVILEGES ON DATABASE inventory_db TO inventory_db;
\q
```

##### 5. 检查 `.env` 文件配置

确保 `.env` 文件中的 `DATABASE_URL` 格式正确：

```env
# 正确格式
DATABASE_URL=postgresql://inventory_db:your_strong_password_here@localhost:5432/inventory_db

# 注意：
# - 用户名：inventory_db
# - 密码：your_strong_password_here（必须与步骤 3 中设置的密码一致）
# - 主机：localhost
# - 端口：5432
# - 数据库名：inventory_db
```

##### 6. 测试数据库连接

```bash
# 使用 psql 测试连接
psql -U inventory_db -d inventory_db -h localhost

# 如果提示输入密码，输入步骤 3 中设置的密码
# 如果连接成功，说明配置正确
```

##### 7. 检查 PostgreSQL 认证配置

编辑 `/etc/postgresql/12/main/pg_hba.conf`（版本号可能不同）：

```conf
# 确保有以下配置允许本地连接
local   all             all                                     peer
host    all             all             127.0.0.1/32            md5
host    all             all             ::1/128                 md5
```

重启 PostgreSQL：

```bash
sudo systemctl restart postgresql
```

#### 常见问题

##### 问题 1：用户名为数据库名

**错误配置：**
```env
DATABASE_URL=postgresql://inventory_db:password@localhost:5432/inventory_db
```

**说明：** 如果 `inventory_db` 既是用户名又是数据库名，需要确保：
- PostgreSQL 中确实存在名为 `inventory_db` 的用户
- 该用户有权限访问 `inventory_db` 数据库

**推荐配置：**
```env
# 使用不同的用户名和数据库名
DATABASE_URL=postgresql://inventory_user:password@localhost:5432/inventory_db
```

##### 问题 2：密码包含特殊字符

如果密码包含特殊字符（如 `@`, `#`, `$` 等），需要进行 URL 编码：

```env
# 原始密码：P@ssw0rd#123
# URL 编码后：P%40ssw0rd%23123
DATABASE_URL=postgresql://inventory_db:P%40ssw0rd%23123@localhost:5432/inventory_db
```

##### 问题 3：使用 postgres 超级用户

**不推荐但可以临时使用：**

```env
DATABASE_URL=postgresql://postgres:postgres_password@localhost:5432/inventory_db
```

**注意：** 生产环境应使用专用用户，不要使用 `postgres` 超级用户。

#### 快速修复脚本

创建并运行以下脚本：

```bash
#!/bin/bash
# fix_db_connection.sh

DB_USER="inventory_db"
DB_NAME="inventory_db"
DB_PASSWORD="your_strong_password_here"

# 创建用户（如果不存在）
sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';" 2>/dev/null || echo "User already exists"

# 设置用户权限
sudo -u postgres psql -c "ALTER USER $DB_USER CREATEDB;"

# 创建数据库（如果不存在）
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" 2>/dev/null || echo "Database already exists"

# 授予权限
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"

echo "Database setup complete!"
echo "Update your .env file with:"
echo "DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME"
```

#### 验证步骤

1. **测试连接：**
   ```bash
   psql -U inventory_db -d inventory_db -h localhost
   ```

2. **检查应用启动：**
   ```bash
   python3 run.py
   ```

3. **查看日志：** 如果仍有错误，检查应用日志获取详细信息

#### 其他可能的问题

- **PostgreSQL 未安装：** `sudo apt install postgresql postgresql-contrib`
- **端口被占用：** `sudo netstat -tlnp | grep 5432`
- **防火墙阻止：** 检查防火墙设置（本地连接通常不受影响）

