from fastapi import APIRouter, Depends, HTTPException, status, Header, Query, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import jwt, JWTError
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from collections import defaultdict
from typing import Optional
import pyotp
import qrcode
import io
import base64
import secrets
import json
import logging

from app.database import get_db
from app.models import Admin
from app.config import settings
from pydantic import BaseModel

# 配置日志
logger = logging.getLogger(__name__)

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBasic()

# 速率限制器将在 main.py 中初始化并设置到 app.state.limiter
# 在 router 中使用时，需要通过 request.app.state.limiter 访问

# 登录失败记录（用于账户级别的速率限制）
# 生产环境应使用 Redis 等持久化存储
login_failed_attempts = defaultdict(list)  # {identifier: [timestamp1, timestamp2, ...]}

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False

def get_password_hash(password: str) -> str:
    # Ensure password is encoded as bytes and handle length limit
    if isinstance(password, str):
        password = password.encode('utf-8')
    # Bcrypt has a 72 byte limit, truncate if necessary
    if len(password) > 72:
        password = password[:72]
    return pwd_context.hash(password)

def get_admin(db: Session) -> Admin:
    """Get or create admin record"""
    admin = db.query(Admin).first()
    if not admin:
        admin = Admin()
        db.add(admin)
        db.commit()
        db.refresh(admin)
    return admin

def verify_admin_password(
    credentials: HTTPBasicCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Verify admin password for protected endpoints"""
    admin = get_admin(db)
    
    if not admin.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin password not set",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    if not verify_password(credentials.password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    return admin

# Schemas
class SetPasswordRequest(BaseModel):
    password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class MFAVerifyRequest(BaseModel):
    totp_code: str

class MFAVerifyResponse(BaseModel):
    verified: bool
    operation_token: Optional[str] = None  # 操作 token，用于后续 API 调用
    expires_in: Optional[int] = None  # token 有效期（秒）

class MFASetupResponse(BaseModel):
    secret: str
    qr_code_url: str
    device_id: str
    device_name: str

class AdminStatusResponse(BaseModel):
    password_set: bool
    mfa_set: bool
    mfa_count: int = 0
    mfa_enabled: bool = True
    mfa_settings: dict = {}  # 细粒度 MFA 配置

class MFASettingsRequest(BaseModel):
    settings: dict  # 细粒度 MFA 配置字典

class MFADeviceInfo(BaseModel):
    id: str
    name: str
    secret: str
    created_at: str

class MFADeviceListResponse(BaseModel):
    devices: list[MFADeviceInfo]

class LoginRequest(BaseModel):
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

class ToggleMFARequest(BaseModel):
    enabled: bool

class MFASettingsRequest(BaseModel):
    settings: dict  # 细粒度 MFA 配置字典

# Endpoints
@router.get("/status", response_model=AdminStatusResponse)
def get_admin_status(db: Session = Depends(get_db)):
    """Check if admin password and MFA are set"""
    admin = get_admin(db)
    
    mfa_count = 0
    if admin.totp_secret:
        if isinstance(admin.totp_secret, list):
            mfa_count = len(admin.totp_secret)
        elif isinstance(admin.totp_secret, str):
            mfa_count = 1  # Legacy format
    
    # 如果 mfa_enabled 字段不存在（旧数据），默认为 True
    mfa_enabled = admin.mfa_enabled if hasattr(admin, 'mfa_enabled') and admin.mfa_enabled is not None else True
    
    # 获取细粒度 MFA 配置，如果不存在则使用默认值
    default_settings = {
        "inbound": True,
        "outbound": False,
        "transfer": True,
        "adjust": True,
        "category_create": True,
        "category_update": True,
        "category_delete": True,
        "warehouse_create": True,
        "warehouse_update": True,
        "warehouse_delete": True
    }
    
    if admin.mfa_settings and isinstance(admin.mfa_settings, dict):
        # 合并默认值和现有配置，确保所有字段都存在
        mfa_settings = {**default_settings, **admin.mfa_settings}
    else:
        mfa_settings = default_settings
    
    return {
        "password_set": admin.password_hash is not None,
        "mfa_set": mfa_count > 0,
        "mfa_count": mfa_count,
        "mfa_enabled": mfa_enabled,
        "mfa_settings": mfa_settings
    }

@router.post("/set-password")
def set_password(request: SetPasswordRequest, db: Session = Depends(get_db)):
    """Set admin password (first time setup)"""
    try:
        admin = get_admin(db)
        
        if admin.password_hash:
            raise HTTPException(status_code=400, detail="Password already set. Use change-password endpoint.")
        
        # Validate password length
        if len(request.password) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters long")
        
        if len(request.password) > 72:
            raise HTTPException(status_code=400, detail="Password cannot be longer than 72 characters")
        
        admin.password_hash = get_password_hash(request.password)
        db.commit()
        return {"message": "Password set successfully"}
    except HTTPException:
        raise
    except Exception as e:
                    logger.error(f"Error setting password: {e}")
                    raise HTTPException(status_code=500, detail=f"Failed to set password: {str(e)}")

def verify_jwt_token(token: str):
    """Verify JWT token"""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "mfa_admin":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

def verify_operation_token(token: str):
    """Verify operation token (for write operations)"""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="操作需要 MFA 验证，请先完成验证",
            headers={"WWW-Authenticate": "Bearer"}
        )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "operation":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的操作 token"
            )
        if not payload.get("verified"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="操作 token 未验证"
            )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="操作 token 已过期或无效，请重新进行 MFA 验证",
            headers={"WWW-Authenticate": "Bearer"}
        )

def get_operation_token(
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    """
    Get and verify operation token from Authorization header.
    Only requires token if MFA is set up and enabled.
    """
    admin = get_admin(db)
    
    # 检查 MFA 是否已设置
    mfa_count = 0
    if admin.totp_secret:
        if isinstance(admin.totp_secret, list):
            mfa_count = len(admin.totp_secret)
        elif isinstance(admin.totp_secret, str):
            mfa_count = 1  # Legacy format
    
    # 如果 MFA 未设置，不需要操作 token
    if mfa_count == 0:
        return None
    
    # 检查 MFA 全局开关是否启用
    mfa_enabled = admin.mfa_enabled if hasattr(admin, 'mfa_enabled') and admin.mfa_enabled is not None else True
    if not mfa_enabled:
        return None
    
    # MFA 已设置且已启用，需要操作 token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="操作需要 MFA 验证，请在请求头中提供有效的操作 token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    token = authorization.replace("Bearer ", "")
    return verify_operation_token(token)

def get_current_admin(
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    """Get current admin from JWT token or Basic Auth (backward compatibility)"""
    # Try JWT token first (from Authorization header)
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
        verify_jwt_token(token)
        return get_admin(db)
    
    # Fallback to Basic Auth for backward compatibility
    try:
        credentials = security(None)
        return verify_admin_password(credentials, db)
    except:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

@router.post("/change-password")
def change_password(
    request: ChangePasswordRequest,
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    """Change admin password - supports both JWT token and Basic Auth"""
    admin = get_current_admin(authorization, db)
    
    if not verify_password(request.old_password, admin.password_hash):
        raise HTTPException(status_code=401, detail="当前密码错误")
    
    admin.password_hash = get_password_hash(request.new_password)
    db.commit()
    return {"message": "Password changed successfully"}

@router.post("/mfa/setup", response_model=MFASetupResponse)
def setup_mfa(
    device_name: str = Query(default="设备", description="设备名称"),
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    """Setup MFA - generate TOTP secret and QR code (add new device)"""
    # Verify authentication
    admin = get_current_admin(authorization, db)
    
    # Generate TOTP secret
    secret = pyotp.random_base32()
    
    # Get existing secrets or initialize empty list
    # IMPORTANT: Create a new list to ensure SQLAlchemy detects the change
    if admin.totp_secret is None:
        secrets_list = []
    elif isinstance(admin.totp_secret, list):
        # Create a deep copy to ensure SQLAlchemy detects the change
        secrets_list = [dict(device) for device in admin.totp_secret] if admin.totp_secret else []
    elif isinstance(admin.totp_secret, str):
        # Try to parse as JSON (handles both single string and JSON string)
        try:
            # First, try to parse as JSON
            parsed = json.loads(admin.totp_secret)
            if isinstance(parsed, list):
                secrets_list = parsed
            elif isinstance(parsed, str):
                # It's a single secret string
                secrets_list = [{
                    "id": "legacy",
                    "name": "默认设备",
                    "secret": parsed,
                    "created_at": datetime.utcnow().isoformat()
                }]
            else:
                # Unexpected format, treat as single secret
                secrets_list = [{
                    "id": "legacy",
                    "name": "默认设备",
                    "secret": admin.totp_secret,
                    "created_at": datetime.utcnow().isoformat()
                }]
        except (json.JSONDecodeError, TypeError):
            # Not valid JSON, treat as single secret string
            secrets_list = [{
                "id": "legacy",
                "name": "默认设备",
                "secret": admin.totp_secret,
                "created_at": datetime.utcnow().isoformat()
            }]
    else:
        secrets_list = []
    
    # Add new device
    device_id = secrets.token_urlsafe(16)
    new_device = {
        "id": device_id,
        "name": device_name,
        "secret": secret,
        "created_at": datetime.utcnow().isoformat()
    }
    secrets_list.append(new_device)
    
    # Update admin's TOTP secret
    # Create a new list to ensure SQLAlchemy detects the change
    admin.totp_secret = list(secrets_list)  # Create a new list object
    db.commit()
    # Expire the object to force reload from database
    db.expire(admin, ['totp_secret'])
    db.refresh(admin)
    
    # Log device addition
    logger.info(f"Added device '{device_name}' with ID '{device_id}'. Total devices: {len(secrets_list)}")
    
    # Verify the secret was saved correctly by reading it back
    db.refresh(admin)
    saved_value = admin.totp_secret
    
    # Helper function to extract secrets from potentially nested structures
    def extract_secrets(value):
        """Recursively extract secrets from potentially nested structures"""
        if isinstance(value, list):
            return value
        elif isinstance(value, str):
            # Try to parse JSON recursively
            parsed = value
            max_attempts = 5
            attempts = 0
            while isinstance(parsed, str) and attempts < max_attempts:
                try:
                    parsed = json.loads(parsed)
                    attempts += 1
                except:
                    return [{"secret": parsed}]  # Single secret string
            return extract_secrets(parsed)  # Recursively parse
        elif isinstance(value, dict):
            return [value]  # Single device object
        else:
            return []
    
    extracted = extract_secrets(saved_value)
    if len(extracted) > 0:
        last_device = extracted[-1]
        if isinstance(last_device, dict):
            saved_secret = last_device.get("secret", "")
            if saved_secret == secret:
                logger.debug(f"Secret verified: Device '{device_name}' secret matches")
            else:
                logger.warning(f"Secret mismatch for device '{device_name}'")
        else:
            logger.warning(f"Last device is not a dict: {type(last_device)}")
    else:
        logger.warning("No devices found in saved value")
    
    # Generate QR code
    totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=f"Admin-{device_name}",
        issuer_name="LiteWMS"
    )
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(totp_uri)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_code_url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
    
    return {
        "secret": secret,
        "qr_code_url": qr_code_url,
        "device_id": device_id,
        "device_name": device_name
    }

@router.post("/mfa/verify", response_model=MFAVerifyResponse)
def verify_mfa(
    request: Request,
    mfa_request: MFAVerifyRequest,
    db: Session = Depends(get_db)
):
    """Verify TOTP code (public endpoint, no auth required) - checks all devices, any match passes"""
    # 速率限制：只对失败的验证进行限制，成功的验证不计入限制
    # 这样可以防止暴力破解，同时不影响正常使用
    limiter = request.app.state.limiter
    
    try:
        admin = get_admin(db)
        
        # Force expire and refresh to get latest data from database (important when multiple devices are added)
        db.expire(admin, ['totp_secret'])
        db.refresh(admin)
        
        if not admin.totp_secret:
            raise HTTPException(status_code=400, detail="MFA not set up")
        
        # Log verification attempt
        logger.debug(f"Verifying TOTP code. Admin totp_secret type: {type(admin.totp_secret)}")
        
        # Log the number of devices for debugging
        if isinstance(admin.totp_secret, list):
            logger.debug(f"Total devices in database: {len(admin.totp_secret)}")
        elif isinstance(admin.totp_secret, str):
            logger.debug(f"totp_secret is a string (may need parsing)")
        
        # Handle both old format (single string) and new format (list)
        # The data might be stored as a string (if column is VARCHAR) or as a list (if column is JSON)
        # It might also be nested JSON strings due to previous bugs
        secrets_list = []
        if isinstance(admin.totp_secret, list):
            secrets_list = admin.totp_secret
            logger.debug(f"Found {len(secrets_list)} devices in list format")
        elif isinstance(admin.totp_secret, str):
            # Try to parse as JSON, handling nested JSON strings
            parsed = admin.totp_secret
            max_parse_attempts = 5  # Prevent infinite loops
            parse_attempts = 0
            
            while isinstance(parsed, str) and parse_attempts < max_parse_attempts:
                try:
                    parsed = json.loads(parsed)
                    parse_attempts += 1
                except (json.JSONDecodeError, TypeError):
                    break
            
            if isinstance(parsed, list):
                secrets_list = parsed
                logger.debug(f"Found {len(secrets_list)} devices in JSON string format (parsed {parse_attempts} time(s))")
            elif isinstance(parsed, str):
                # After parsing, still a string - treat as single secret
                secrets_list = [{"secret": parsed}]
                logger.debug(f"Found single secret after {parse_attempts} parse attempt(s)")
            elif isinstance(parsed, dict):
                # Single device object
                secrets_list = [parsed]
                logger.debug("Found single device object in JSON string")
            else:
                # Unexpected format, treat as single secret
                secrets_list = [{"secret": admin.totp_secret}]
                logger.warning(f"Found string format, but parsed to unexpected type {type(parsed)}, treating as single secret")
        else:
            logger.error(f"Unexpected totp_secret type: {type(admin.totp_secret)}")
            raise HTTPException(status_code=400, detail="MFA not set up")
        
        if not secrets_list:
            raise HTTPException(status_code=400, detail="MFA not set up")
        
        # Try to verify against any of the secrets
        logger.debug(f"Attempting to verify code against {len(secrets_list)} device(s)")
        for idx, device in enumerate(secrets_list):
            secret = device.get("secret") if isinstance(device, dict) else device
            device_name = device.get("name", f"Device {idx+1}") if isinstance(device, dict) else "Unknown"
            if secret:
                try:
                    logger.debug(f"Trying device {idx+1}/{len(secrets_list)}: {device_name} (secret length: {len(secret) if secret else 0})")
                    totp = pyotp.TOTP(secret)
                    # Increase valid_window to 2 (allows ±60 seconds) for better tolerance
                    if totp.verify(mfa_request.totp_code, valid_window=1):
                        logger.info(f"Verification successful with device: {device_name} (device {idx+1}/{len(secrets_list)})")
                        # 生成短期操作 token（5 分钟有效）
                        operation_token_expires = timedelta(minutes=5)
                        operation_token = create_access_token(
                            data={"type": "operation", "verified": True},
                            expires_delta=operation_token_expires
                        )
                        return {
                            "verified": True,
                            "operation_token": operation_token,
                            "expires_in": int(operation_token_expires.total_seconds())
                        }
                    else:
                        logger.debug(f"Verification failed for device: {device_name} (device {idx+1}/{len(secrets_list)})")
                except Exception as e:
                    # Skip invalid secret format, try next device
                    logger.warning(f"Error verifying secret for device {device_name}: {e}")
                    continue
        
        # None of the secrets matched - 验证失败，检查速率限制
        # 只对失败的验证进行速率限制，成功的验证不计入限制
        try:
            from limits import parse_many
            
            # 解析限制字符串 "10/minute" - 提高失败验证的限制次数
            limit_items = parse_many("10/minute")
            
            # 获取客户端标识符
            key = get_remote_address(request)
            
            # 检查每个限制项
            for limit_item in limit_items:
                # hit() 方法返回 True 如果未超过限制（可以继续），False 如果超过限制
                if not limiter.limiter.hit(limit_item, key):
                    # 超过限制，抛出 HTTPException
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="验证失败次数过多，请稍后再试（每分钟最多 10 次失败尝试）"
                    )
        except HTTPException:
            # 重新抛出 HTTPException（包括我们刚抛出的 429 错误）
            raise
        except Exception as e:
            # 其他异常（如 RateLimitExceeded）也转换为 HTTPException
            if isinstance(e, RateLimitExceeded):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="验证失败次数过多，请稍后再试（每分钟最多 10 次失败尝试）"
                )
            # 其他异常继续抛出
            raise
        
        # 验证失败，但未超过速率限制
        raise HTTPException(status_code=401, detail="验证码错误")
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Log the actual error
        logger.error(f"Error in verify_mfa: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

def create_access_token(data: dict, expires_delta: timedelta = None):
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

def check_login_rate_limit(identifier: str):
    """检查登录速率限制（每个账户 5 次/5 分钟）"""
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=5)
    
    # 清理过期的失败记录
    login_failed_attempts[identifier] = [
        t for t in login_failed_attempts[identifier] if t > cutoff
    ]
    
    # 检查是否超过限制
    if len(login_failed_attempts[identifier]) >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录尝试过于频繁，请 5 分钟后重试"
        )

@router.post("/login", response_model=LoginResponse)
def login(
    login_request: LoginRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Login with password, returns JWT token (more secure than Basic Auth)"""
    # 获取账户标识符（使用 IP 地址）
    identifier = get_remote_address(request)
    
    # 检查速率限制
    check_login_rate_limit(identifier)
    
    admin = get_admin(db)
    
    if not admin.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin password not set"
        )
    
    # Verify password
    if not verify_password(login_request.password, admin.password_hash):
        # 记录失败的登录尝试
        login_failed_attempts[identifier].append(datetime.utcnow())
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="密码错误"
        )
    
    # 登录成功，清除失败记录
    if identifier in login_failed_attempts:
        del login_failed_attempts[identifier]
    
    # Create access token
    access_token_expires = timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": "admin", "type": "mfa_admin"},
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.JWT_EXPIRE_MINUTES * 60
    }

@router.get("/verify-password")
def verify_password_endpoint(admin: Admin = Depends(verify_admin_password)):
    """Verify admin password (protected endpoint for login verification) - DEPRECATED, use /login instead"""
    return {"verified": True}

@router.get("/mfa/devices", response_model=MFADeviceListResponse)
def get_mfa_devices(
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    """Get list of all MFA devices"""
    admin = get_current_admin(authorization, db)
    
    if not admin.totp_secret:
        logger.debug("No totp_secret found, returning empty list")
        return {"devices": []}
    
    logger.debug(f"get_mfa_devices: Admin totp_secret type: {type(admin.totp_secret)}")
    
    # Handle both old format and new format, including nested JSON strings
    secrets_list = []
    if isinstance(admin.totp_secret, list):
        secrets_list = admin.totp_secret
        logger.debug(f"get_mfa_devices: Found {len(secrets_list)} devices in list format")
    elif isinstance(admin.totp_secret, str):
        # Try to parse as JSON, handling nested JSON strings
        parsed = admin.totp_secret
        max_parse_attempts = 5  # Prevent infinite loops
        parse_attempts = 0
        
        while isinstance(parsed, str) and parse_attempts < max_parse_attempts:
            try:
                parsed = json.loads(parsed)
                parse_attempts += 1
                logger.debug(f"get_mfa_devices: Parsed JSON string (attempt {parse_attempts}), result type: {type(parsed)}")
            except (json.JSONDecodeError, TypeError) as e:
                logger.debug(f"get_mfa_devices: JSON parse error: {e}")
                break
        
        if isinstance(parsed, list):
            secrets_list = parsed
            logger.debug(f"get_mfa_devices: Found {len(secrets_list)} devices after parsing JSON string")
        elif isinstance(parsed, str):
            # After parsing, still a string - treat as single secret
            secrets_list = [{"secret": parsed, "id": "legacy", "name": "默认设备", "created_at": ""}]
            logger.debug("get_mfa_devices: Parsed to single secret string")
        elif isinstance(parsed, dict):
            # Single device object
            secrets_list = [parsed]
            logger.debug("get_mfa_devices: Parsed to single device object")
        else:
            # Unexpected format, treat as single secret
            secrets_list = [{"secret": admin.totp_secret, "id": "legacy", "name": "默认设备", "created_at": ""}]
            logger.warning(f"get_mfa_devices: Unexpected parsed type {type(parsed)}, treating as single secret")
    else:
        logger.warning(f"get_mfa_devices: Unexpected totp_secret type: {type(admin.totp_secret)}")
        return {"devices": []}
    
    # Extract devices from secrets_list
    devices = []
    for idx, device in enumerate(secrets_list):
        if isinstance(device, dict):
            device_id = device.get("id", f"device_{idx}")
            device_name = device.get("name", "设备")
            device_secret = device.get("secret", "")
            device_created = device.get("created_at", "")
            
            # Skip devices with invalid secrets
            if not device_secret or device_secret == "null" or device_secret == "None":
                logger.warning(f"get_mfa_devices: Skipping device {idx} with invalid secret: {device_secret}")
                continue
            
            devices.append({
                "id": device_id,
                "name": device_name,
                "secret": device_secret,
                "created_at": device_created
            })
            logger.debug(f"get_mfa_devices: Added device {idx}: {device_name} (id: {device_id})")
        else:
            logger.warning(f"get_mfa_devices: Skipping non-dict device at index {idx}: {type(device)}")
    
    logger.debug(f"get_mfa_devices: Returning {len(devices)} devices to frontend")
    return {"devices": devices}

@router.delete("/mfa/devices/{device_id}")
def delete_mfa_device(
    device_id: str,
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    """Delete a specific MFA device"""
    admin = get_current_admin(authorization, db)
    
    if not admin.totp_secret:
        raise HTTPException(status_code=400, detail="No MFA devices found")
    
    if isinstance(admin.totp_secret, list):
        # Remove device by id
        original_count = len(admin.totp_secret)
        admin.totp_secret = [d for d in admin.totp_secret if isinstance(d, dict) and d.get("id") != device_id]
        
        if len(admin.totp_secret) == original_count:
            raise HTTPException(status_code=404, detail="Device not found")
        
        # If no devices left, set to None
        if not admin.totp_secret:
            admin.totp_secret = None
        
        db.commit()
        return {"message": "Device deleted successfully"}
    elif isinstance(admin.totp_secret, str):
        # Legacy format: clear all
        if device_id == "legacy":
            admin.totp_secret = None
            db.commit()
            return {"message": "Device deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Device not found")
    
    raise HTTPException(status_code=400, detail="Invalid MFA configuration")

@router.post("/toggle")
def toggle_mfa(
    request: ToggleMFARequest,
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    """Enable or disable MFA verification"""
    admin = get_current_admin(authorization, db)
    
    # 检查是否有 MFA 设备
    mfa_count = 0
    if admin.totp_secret:
        if isinstance(admin.totp_secret, list):
            mfa_count = len(admin.totp_secret)
        elif isinstance(admin.totp_secret, str):
            mfa_count = 1  # Legacy format
    
    if request.enabled and mfa_count == 0:
        raise HTTPException(
            status_code=400,
            detail="无法启用 MFA：请先添加至少一个 MFA 设备"
        )
    
    # 更新 MFA 启用状态
    admin.mfa_enabled = request.enabled
    db.commit()
    
    logger.info(f"MFA {'enabled' if request.enabled else 'disabled'} by admin")
    
    return {
        "message": f"MFA 已{'启用' if request.enabled else '禁用'}",
        "mfa_enabled": request.enabled
    }

@router.get("/settings")
def get_mfa_settings(
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    """Get granular MFA settings"""
    admin = get_current_admin(authorization, db)
    
    # 默认配置
    default_settings = {
        "inbound": True,
        "outbound": False,
        "transfer": True,
        "adjust": True,
        "category_create": True,
        "category_update": True,
        "category_delete": True,
        "warehouse_create": True,
        "warehouse_update": True,
        "warehouse_delete": True
    }
    
    if admin.mfa_settings and isinstance(admin.mfa_settings, dict):
        # 合并默认值和现有配置
        settings = {**default_settings, **admin.mfa_settings}
    else:
        settings = default_settings
    
    return {"settings": settings}

@router.post("/settings")
def update_mfa_settings(
    request: MFASettingsRequest,
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    """Update granular MFA settings"""
    admin = get_current_admin(authorization, db)
    
    # 验证配置字段
    valid_keys = {
        "inbound", "outbound", "transfer", "adjust",
        "category_create", "category_update", "category_delete",
        "warehouse_create", "warehouse_update", "warehouse_delete"
    }
    
    # 过滤无效字段，只保留有效字段
    filtered_settings = {
        k: bool(v) for k, v in request.settings.items() 
        if k in valid_keys
    }
    
    # 合并现有配置（如果有）
    if admin.mfa_settings and isinstance(admin.mfa_settings, dict):
        admin.mfa_settings.update(filtered_settings)
    else:
        admin.mfa_settings = filtered_settings
    
    db.commit()
    
    logger.info(f"MFA settings updated: {filtered_settings}")
    
    return {
        "message": "MFA 配置已更新",
        "settings": admin.mfa_settings
    }

