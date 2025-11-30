# 后端 API 文档

## 快速开始

1. 安装依赖：`pip install -r requirements.txt`
2. 配置环境变量：复制 `.env.example` 为 `.env` 并修改数据库连接
3. 创建数据库：`createdb inventory_db`
4. 运行应用：`python run.py`
5. 初始化数据：`python -m app.seed_data`

## 环境变量配置

创建 `.env` 文件，包含以下配置：

```env
# 数据库配置
DATABASE_URL=postgresql://user:password@localhost:5432/inventory_db

# 服务器配置
HOST=0.0.0.0
PORT=8000

# CORS 配置
CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# JWT 配置（MFA 认证）
JWT_SECRET=your-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440
```

**重要**：`JWT_SECRET` **必须**更改为强随机密钥，否则应用将无法启动。

生成强随机密钥的方法：
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

将生成的密钥设置到 `.env` 文件中的 `JWT_SECRET` 变量。

## API 端点

### 品类 (Categories)
- `GET /api/categories/` - 获取所有品类
- `GET /api/categories/{id}` - 获取单个品类
- `POST /api/categories/` - 创建品类
- `PUT /api/categories/{id}` - 更新品类
- `DELETE /api/categories/{id}` - 删除品类

### 仓库 (Warehouses)
- `GET /api/warehouses/` - 获取所有仓库
- `GET /api/warehouses/{id}` - 获取单个仓库
- `POST /api/warehouses/` - 创建仓库
- `PUT /api/warehouses/{id}` - 更新仓库
- `DELETE /api/warehouses/{id}` - 删除仓库

### 库存项 (Items)
- `GET /api/items/` - 获取库存项（支持 warehouse_id, category_id 查询参数）
- `GET /api/items/with-category` - 获取库存项（包含品类名称）
- `GET /api/items/{id}` - 获取单个库存项
- `POST /api/items/` - 创建库存项（如果规格相同则更新数量）
- `PUT /api/items/{id}` - 更新库存项
- `DELETE /api/items/{id}` - 删除库存项

### 交易记录 (Transactions)
- `GET /api/transactions/` - 获取交易记录（支持 warehouse_id, transaction_type, filter_date 查询参数）
- `GET /api/transactions/{id}` - 获取单个交易记录
- `POST /api/transactions/` - 创建交易记录
- `DELETE /api/transactions/{id}` - 删除交易记录

### MFA 验证 (Multi-Factor Authentication)

#### 管理员状态和密码管理
- `GET /api/mfa/status` - 获取管理员状态（密码是否设置、MFA 设备数量）
- `POST /api/mfa/set-password` - 首次设置管理员密码（无需认证）
- `POST /api/mfa/change-password` - 修改管理员密码（需要 JWT 认证）
- `POST /api/mfa/login` - 管理员登录，获取 JWT token
  - **速率限制**：每个 IP 地址每 5 分钟最多 5 次失败尝试（防止暴力破解）
  - 超过限制后返回 `429 Too Many Requests` 错误

**忘记密码处理**：
如果忘记了 MFA 管理页面的登录密码，可以使用 `reset_admin_password.py` 脚本重置：
```bash
cd backend
source venv/bin/activate
python reset_admin_password.py
```
详见 `TROUBLESHOOTING.md` 中的"忘记 MFA 页面登录密码"章节。

#### MFA 设备管理
- `POST /api/mfa/setup` - 添加新的 MFA 设备，生成 TOTP 密钥和二维码（需要 JWT 认证）
  - 查询参数：`device_name` - 设备名称（可选）
- `GET /api/mfa/devices` - 获取所有已配置的 MFA 设备列表（需要 JWT 认证）
- `DELETE /api/mfa/devices/{device_id}` - 删除指定的 MFA 设备（需要 JWT 认证）

#### MFA 验证
- `POST /api/mfa/verify` - 验证 TOTP 验证码（公开端点，无需认证）
  - 请求体：`{ "code": "123456" }`
  - 验证任意一个已配置设备的验证码即可通过
  - **速率限制**：每个 IP 地址每分钟最多 5 次（防止暴力破解）

#### 认证说明

**JWT 认证**：
- 登录后获取的 JWT token 需要在请求头中携带：`Authorization: Bearer <token>`
- Token 有效期由 `JWT_EXPIRE_MINUTES` 配置决定（默认 1440 分钟，即 24 小时）
- Token 过期后需要重新登录获取新 token

**需要认证的端点**：
- 所有 MFA 设备管理端点（`/api/mfa/setup`, `/api/mfa/devices`, `/api/mfa/devices/{device_id}`）
- 修改密码端点（`/api/mfa/change-password`）

**公开端点**：
- MFA 验证端点（`/api/mfa/verify`）- 用于主站点的操作验证
- 设置密码端点（`/api/mfa/set-password`）- 首次部署时使用

## 技术实现

### MFA 实现细节

- **TOTP 算法**：使用 `pyotp` 库实现 RFC 6238 标准的 TOTP
- **密码加密**：使用 `bcrypt` 进行密码哈希（`passlib[bcrypt]`）
- **多设备支持**：MFA 设备信息以 JSON 格式存储在 `admin.totp_secret` 字段
- **验证窗口**：TOTP 验证窗口设置为 2（允许 ±60 秒的时间偏差）

### 安全特性

#### JWT_SECRET 强制验证
- 应用启动时会检查 `JWT_SECRET` 是否为默认值
- 如果为默认值，应用将拒绝启动并显示错误提示
- 这确保生产环境必须设置强随机密钥

#### 速率限制（Rate Limiting）
- 使用 `slowapi` 库实施速率限制保护
- **MFA 验证端点** (`/api/mfa/verify`)：
  - 限制：每个 IP 地址每分钟最多 5 次
  - 超过限制返回 `429 Too Many Requests` 错误
- **登录端点** (`/api/mfa/login`)：
  - 限制：每个 IP 地址每 5 分钟最多 5 次失败尝试
  - 跟踪失败登录尝试，超过限制后返回 `429 Too Many Requests` 错误
  - 登录成功后清除失败记录

这些安全特性有效防止暴力破解攻击，提升系统安全性。

### 数据库模型

**Admin 表**：
- `id` - 主键
- `password_hash` - 密码哈希（可为 NULL，表示未设置密码）
- `totp_secret` - MFA 设备信息（JSON 格式，存储设备列表）
- `created_at` - 创建时间
- `updated_at` - 更新时间

## 访问 API 文档

启动服务后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

