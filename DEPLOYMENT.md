# 后端生产部署指南

本文档详细说明如何将 LiteWMS 后端部署到生产环境。

## 📋 目录

- [系统要求](#系统要求)
- [环境准备](#环境准备)
- [数据库配置](#数据库配置)
- [应用配置](#应用配置)
- [部署方式](#部署方式)
- [安全配置](#安全配置)
- [监控与日志](#监控与日志)
- [备份策略](#备份策略)
- [性能优化](#性能优化)
- [故障排查](#故障排查)

---

## 系统要求

### 服务器要求

- **操作系统**: Linux (Ubuntu 20.04+ / CentOS 7+ / Debian 10+)
- **Python**: 3.9+
- **PostgreSQL**: 12+ (推荐 14+)
- **内存**: 最低 512MB，推荐 1GB+
- **磁盘**: 最低 10GB，推荐 20GB+
- **CPU**: 1 核心（推荐 2 核心+）

### 网络要求

- 开放端口：8000（或自定义端口）
- 防火墙配置允许前端访问
- SSL/TLS 证书（推荐使用 Nginx 反向代理）

---

## 环境准备

### 1. 更新系统

```bash
# Ubuntu/Debian
sudo apt update && sudo apt upgrade -y

# CentOS/RHEL
sudo yum update -y
```

### 2. 安装 Python 3.9+

```bash
# Ubuntu/Debian
sudo apt install python3.9 python3.9-venv python3-pip -y

# CentOS/RHEL
sudo yum install python39 python39-pip -y

# 验证版本
python3 --version
```

### 3. 安装 PostgreSQL

```bash
# Ubuntu/Debian
sudo apt install postgresql postgresql-contrib -y

# CentOS/RHEL
sudo yum install postgresql-server postgresql-contrib -y
sudo postgresql-setup --initdb
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### 4. 创建应用用户

```bash
# 创建非 root 用户运行应用
sudo useradd -m -s /bin/bash inventory
sudo mkdir -p /opt/inventory-backend
sudo chown inventory:inventory /opt/inventory-backend
```

---

## 数据库配置

### 1. 创建数据库和用户

```bash
# 切换到 postgres 用户
sudo -u postgres psql

# 在 PostgreSQL 中执行
CREATE DATABASE inventory_db;
CREATE USER inventory_user WITH PASSWORD 'your_strong_password_here';
GRANT ALL PRIVILEGES ON DATABASE inventory_db TO inventory_user;
ALTER USER inventory_user CREATEDB;

# ⚠️ PostgreSQL 15+ 需要额外授予 public schema 权限
GRANT ALL ON SCHEMA public TO inventory_user;
GRANT CREATE ON SCHEMA public TO inventory_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO inventory_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO inventory_user;

\q
```

### 2. 配置 PostgreSQL

编辑 `/etc/postgresql/12/main/postgresql.conf` (版本号可能不同):

```conf
# 性能优化
max_connections = 100
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1
effective_io_concurrency = 200
work_mem = 4MB
min_wal_size = 1GB
max_wal_size = 4GB
```

编辑 `/etc/postgresql/12/main/pg_hba.conf`:

```conf
# 允许本地连接
local   all             all                                     peer
host    all             all             127.0.0.1/32            md5
host    all             all             ::1/128                 md5
```

重启 PostgreSQL:

```bash
sudo systemctl restart postgresql
```

### 3. 测试数据库连接

```bash
psql -U inventory_user -d inventory_db -h localhost
```

---

## 应用配置

### 1. 上传代码

```bash
# 切换到应用用户
sudo su - inventory

# 克隆或上传代码到 /opt/inventory-backend
cd /opt/inventory-backend
# git clone <your-repo> . 或使用 scp/rsync 上传
```

### 2. 创建虚拟环境

```bash
cd /opt/inventory-backend
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
# 复制示例文件
cp env.example .env

# 编辑配置文件
nano .env
```

`.env` 文件配置示例：

```env
# 数据库配置
DATABASE_URL=postgresql://inventory_user:your_strong_password_here@localhost:5432/inventory_db

# 服务器配置
HOST=0.0.0.0
PORT=8000

# CORS 配置（生产环境）
CORS_ORIGINS=https://your-frontend-domain.com,https://www.your-frontend-domain.com

# JWT 配置（必须更改！）
JWT_SECRET=your-very-long-and-random-secret-key-here-generate-with-secrets-token_urlsafe
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=30
```

**重要**: 生成强随机 JWT_SECRET:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 4. 初始化数据库

#### 情况 A：从 0 开始部署（全新数据库）

```bash
# 激活虚拟环境
source venv/bin/activate

# 运行应用一次以创建表结构（SQLAlchemy 会自动创建所有表，包括所有字段）
python run.py &
sleep 5
pkill -f "python run.py"

# 初始化种子数据（可选）
python -m app.seed_data
```

**说明**：
- SQLAlchemy 的 `Base.metadata.create_all()` 会根据模型定义**自动创建完整的表结构**
- 包括所有字段（如 `mfa_enabled`、`mfa_settings` 等）
- **不需要运行迁移脚本**，因为表是从模型定义完整创建的

#### 情况 B：已有数据库，升级到新版本

```bash
# 激活虚拟环境
source venv/bin/activate

# 数据库结构由 SQLAlchemy 自动管理
# 首次部署时，运行应用会自动创建所有表
# 如果代码中添加了新字段，需要手动执行 SQL 或重新创建表
```

**说明**：
- 首次部署时，运行应用（`python run.py`）会自动创建所有表
- 如果代码中添加了新字段，需要手动执行 SQL 来添加字段
- 或者使用 SQLAlchemy 的迁移工具（如 Alembic）进行数据库迁移

#### 如何判断？

- **全新部署**：数据库是空的，没有任何表 → 不需要运行迁移脚本
- **升级部署**：数据库已有数据，但可能缺少新字段 → 需要运行迁移脚本

### 5. 测试应用

```bash
source venv/bin/activate
python run.py
```

访问 `http://your-server-ip:8000/docs` 确认 API 文档可访问。

---

## 部署方式

### 方式一：使用 systemd（推荐）

#### 1. 创建 systemd 服务文件

```bash
sudo nano /etc/systemd/system/inventory-backend.service
```

服务文件内容：

```ini
[Unit]
Description=LiteWMS Backend API
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=inventory
Group=inventory
WorkingDirectory=/opt/inventory-backend
Environment="PATH=/opt/inventory-backend/venv/bin"
ExecStart=/opt/inventory-backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=inventory-backend

# 安全设置
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/inventory-backend

[Install]
WantedBy=multi-user.target
```

#### 2. 启动服务

```bash
# 重载 systemd
sudo systemctl daemon-reload

# 启动服务
sudo systemctl start inventory-backend

# 设置开机自启
sudo systemctl enable inventory-backend

# 查看状态
sudo systemctl status inventory-backend

# 查看日志
sudo journalctl -u inventory-backend -f
```

### 方式二：使用 Supervisor

#### 1. 安装 Supervisor

```bash
sudo apt install supervisor -y  # Ubuntu/Debian
# 或
sudo yum install supervisor -y  # CentOS/RHEL
```

#### 2. 创建配置文件

```bash
sudo nano /etc/supervisor/conf.d/inventory-backend.conf
```

配置文件内容：

```ini
[program:inventory-backend]
command=/opt/inventory-backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
directory=/opt/inventory-backend
user=inventory
autostart=true
autorestart=true
stderr_logfile=/var/log/inventory-backend/error.log
stdout_logfile=/var/log/inventory-backend/access.log
environment=PATH="/opt/inventory-backend/venv/bin"
```

#### 3. 创建日志目录

```bash
sudo mkdir -p /var/log/inventory-backend
sudo chown inventory:inventory /var/log/inventory-backend
```

#### 4. 启动服务

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start inventory-backend
sudo supervisorctl status inventory-backend
```

### 方式三：使用 Docker（可选）

#### 1. 创建 Dockerfile

```dockerfile
FROM python:3.9-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### 2. 创建 docker-compose.yml

```yaml
version: '3.8'

services:
  backend:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://inventory_user:password@db:5432/inventory_db
      - CORS_ORIGINS=https://your-frontend-domain.com
      - JWT_SECRET=${JWT_SECRET}
    depends_on:
      - db
    restart: unless-stopped

  db:
    image: postgres:14
    environment:
      - POSTGRES_DB=inventory_db
      - POSTGRES_USER=inventory_user
      - POSTGRES_PASSWORD=your_strong_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

volumes:
  postgres_data:
```

#### 3. 运行

```bash
docker-compose up -d
```

---

## 安全配置

### 1. 防火墙配置

```bash
# Ubuntu/Debian (UFW)
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP (Nginx)
sudo ufw allow 443/tcp   # HTTPS (Nginx)
sudo ufw enable

# CentOS/RHEL (firewalld)
sudo firewall-cmd --permanent --add-service=ssh
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

**注意**: 不要直接暴露 8000 端口，使用 Nginx 反向代理。

### 2. 使用 Nginx 反向代理

#### 安装 Nginx

```bash
sudo apt install nginx -y  # Ubuntu/Debian
sudo yum install nginx -y  # CentOS/RHEL
```

#### 配置 Nginx

```bash
sudo nano /etc/nginx/sites-available/inventory-backend
```

配置文件内容：

```nginx
server {
    listen 80;
    server_name api.yourdomain.com;

    # 重定向到 HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;

    # SSL 证书配置
    ssl_certificate /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # 安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # 反向代理
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket 支持（如果需要）
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # 超时设置
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

启用配置：

```bash
sudo ln -s /etc/nginx/sites-available/inventory-backend /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 3. SSL 证书（Let's Encrypt）

```bash
# 安装 Certbot
sudo apt install certbot python3-certbot-nginx -y

# 获取证书
sudo certbot --nginx -d api.yourdomain.com

# 自动续期测试
sudo certbot renew --dry-run
```

### 4. 应用安全设置

- ✅ 使用强密码
- ✅ 定期更新依赖 (`pip list --outdated`)
- ✅ 限制数据库访问（仅允许本地连接）
- ✅ 使用环境变量存储敏感信息
- ✅ 定期备份数据库
- ✅ 监控日志异常

---

## 监控与日志

### 1. 日志配置

创建日志配置文件 `logging.conf`:

```python
[loggers]
keys=root,app

[handlers]
keys=consoleHandler,fileHandler

[formatters]
keys=simpleFormatter

[logger_root]
level=INFO
handlers=consoleHandler

[logger_app]
level=INFO
handlers=consoleHandler,fileHandler
qualname=app
propagate=0

[handler_consoleHandler]
class=StreamHandler
level=INFO
formatter=simpleFormatter
args=(sys.stdout,)

[handler_fileHandler]
class=FileHandler
level=INFO
formatter=simpleFormatter
args=('/var/log/inventory-backend/app.log', 'a')

[formatter_simpleFormatter]
format=%(asctime)s - %(name)s - %(levelname)s - %(message)s
datefmt=%Y-%m-%d %H:%M:%S
```

### 2. 日志轮转

创建 logrotate 配置：

```bash
sudo nano /etc/logrotate.d/inventory-backend
```

内容：

```
/var/log/inventory-backend/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 inventory inventory
    sharedscripts
    postrotate
        systemctl reload inventory-backend > /dev/null 2>&1 || true
    endscript
}
```

### 3. 监控建议

- **系统监控**: 使用 `htop`, `iostat`, `netstat`
- **应用监控**: 使用 `curl` 定期检查健康端点
- **数据库监控**: 使用 `pg_stat_activity` 查看连接状态
- **日志监控**: 使用 `journalctl` 或日志聚合工具

---

## 备份策略

### 1. 数据库备份

创建备份脚本 `/opt/inventory-backend/backup.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/opt/inventory-backend/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_NAME="inventory_db"
DB_USER="inventory_user"

mkdir -p $BACKUP_DIR

# 备份数据库
pg_dump -U $DB_USER -h localhost $DB_NAME | gzip > $BACKUP_DIR/db_backup_$DATE.sql.gz

# 删除 7 天前的备份
find $BACKUP_DIR -name "db_backup_*.sql.gz" -mtime +7 -delete

echo "Backup completed: db_backup_$DATE.sql.gz"
```

设置权限：

```bash
chmod +x /opt/inventory-backend/backup.sh
```

### 2. 定时备份（Cron）

```bash
crontab -e -u inventory
```

添加：

```
# 每天凌晨 2 点备份
0 2 * * * /opt/inventory-backend/backup.sh >> /var/log/inventory-backend/backup.log 2>&1
```

### 3. 备份恢复

```bash
# 解压备份
gunzip db_backup_20240101_020000.sql.gz

# 恢复数据库
psql -U inventory_user -d inventory_db < db_backup_20240101_020000.sql
```

---

## 性能优化

### 1. PostgreSQL 优化

参考 [数据库配置](#数据库配置) 部分的 `postgresql.conf` 设置。

### 2. 应用优化

- 使用连接池（SQLAlchemy 默认已配置）
- 启用 Gunicorn + Uvicorn workers（生产环境）

创建 `gunicorn_config.py`:

```python
bind = "0.0.0.0:8000"
workers = 4
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
timeout = 30
keepalive = 2
```

安装 Gunicorn:

```bash
pip install gunicorn
```

修改 systemd 服务：

```ini
ExecStart=/opt/inventory-backend/venv/bin/gunicorn -c gunicorn_config.py app.main:app
```

### 3. 缓存（可选）

考虑使用 Redis 缓存频繁查询的数据。

---

## 故障排查

### 1. 数据库连接错误

#### 错误：`password authentication failed for user`

**原因：** 数据库用户名或密码不正确，或用户不存在

**解决步骤：**

1. **检查 PostgreSQL 服务：**
   ```bash
   sudo systemctl status postgresql
   ```

2. **检查用户是否存在：**
   ```bash
   sudo -u postgres psql -c "\du"
   ```

3. **创建或重置用户：**
   ```bash
   sudo -u postgres psql
   ```
   在 PostgreSQL 中执行：
   ```sql
   -- 如果用户不存在，创建用户
   CREATE USER inventory_db WITH PASSWORD 'your_strong_password_here';
   ALTER USER inventory_db CREATEDB;
   
   -- 如果用户已存在，重置密码
   ALTER USER inventory_db WITH PASSWORD 'your_new_password_here';
   ```

4. **创建数据库：**
   ```sql
   CREATE DATABASE inventory_db OWNER inventory_db;
   GRANT ALL PRIVILEGES ON DATABASE inventory_db TO inventory_db;
   \q
   ```

5. **更新 `.env` 文件：**
   ```env
   DATABASE_URL=postgresql://inventory_db:your_strong_password_here@localhost:5432/inventory_db
   ```
   **注意：** 密码必须与步骤 3 中设置的密码完全一致

6. **测试连接：**
   ```bash
   psql -U inventory_db -d inventory_db -h localhost
   ```

7. **检查 PostgreSQL 认证配置：**
   编辑 `/etc/postgresql/12/main/pg_hba.conf`：
   ```conf
   host    all             all             127.0.0.1/32            md5
   ```
   重启 PostgreSQL：
   ```bash
   sudo systemctl restart postgresql
   ```

**常见问题：**
- 密码包含特殊字符：需要进行 URL 编码（如 `@` → `%40`）
- 用户名和数据库名混淆：确保用户名和数据库名正确对应
- 使用 postgres 超级用户：生产环境应使用专用用户

### 2. 服务无法启动

```bash
# 检查服务状态
sudo systemctl status inventory-backend

# 查看详细日志
sudo journalctl -u inventory-backend -n 100 --no-pager

# 检查端口占用
sudo netstat -tlnp | grep 8000

# 检查环境变量
sudo -u inventory cat /opt/inventory-backend/.env
```

### 2. 数据库连接失败

```bash
# 测试数据库连接
psql -U inventory_user -d inventory_db -h localhost

# 检查 PostgreSQL 状态
sudo systemctl status postgresql

# 查看 PostgreSQL 日志
sudo tail -f /var/log/postgresql/postgresql-12-main.log
```

### 3. 性能问题

```bash
# 查看数据库连接数
psql -U inventory_user -d inventory_db -c "SELECT count(*) FROM pg_stat_activity;"

# 查看慢查询
psql -U inventory_user -d inventory_db -c "SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;"

# 查看系统资源
htop
iostat -x 1
```

### 4. 常见错误

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| `JWT_SECRET must be changed` | JWT_SECRET 未更改 | 在 .env 中设置强随机密钥 |
| `Connection refused` | 数据库未启动 | `sudo systemctl start postgresql` |
| `Permission denied` | 文件权限问题 | 检查文件所有者：`sudo chown -R inventory:inventory /opt/inventory-backend` |
| `Port already in use` | 端口被占用 | 更改端口或停止占用进程 |
| `permission denied for schema public` | PostgreSQL 15+ 权限问题 | 执行：`GRANT ALL ON SCHEMA public TO inventory_user;` |
| `password authentication failed` | 数据库用户或密码错误 | 检查 `.env` 中的 `DATABASE_URL` 配置 |

---

## 更新部署

### 1. 更新代码

```bash
cd /opt/inventory-backend
sudo -u inventory git pull  # 或使用 scp/rsync

# 激活虚拟环境
source venv/bin/activate

# 更新依赖
pip install -r requirements.txt --upgrade

# 如果代码中添加了新字段，需要手动执行 SQL 迁移
# 例如添加 mfa_settings 字段：
# ALTER TABLE admin ADD COLUMN IF NOT EXISTS mfa_settings JSON;
```

**何时需要数据库迁移**：
- ✅ **代码更新包含新的数据库字段**（如新增 `mfa_settings` 字段）
- ❌ **只是修复 bug 或功能优化，没有数据库结构变化** → 不需要迁移

**注意**：建议使用 Alembic 等专业的数据库迁移工具来管理数据库结构变更，而不是手动执行 SQL。

### 2. 重启服务

```bash
sudo systemctl restart inventory-backend
```

### 3. 验证

```bash
# 检查服务状态
sudo systemctl status inventory-backend

# 测试 API
curl http://localhost:8000/api/health
```

---

## 维护检查清单

### 每日
- [ ] 检查服务状态
- [ ] 查看错误日志
- [ ] 检查磁盘空间

### 每周
- [ ] 检查数据库备份
- [ ] 查看系统资源使用
- [ ] 检查安全更新

### 每月
- [ ] 更新依赖包
- [ ] 检查日志文件大小
- [ ] 性能优化评估
- [ ] 安全审计

---

## 联系与支持

如遇到问题，请检查：
1. 日志文件：`/var/log/inventory-backend/`
2. 系统日志：`journalctl -u inventory-backend`
3. 数据库日志：`/var/log/postgresql/`

---

**最后更新**: 2024年

