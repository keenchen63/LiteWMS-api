from pydantic_settings import BaseSettings
from typing import List
from pydantic import field_validator
import sys

class Settings(BaseSettings):
    DATABASE_URL: str
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    JWT_SECRET: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 30
    
    @field_validator('CORS_ORIGINS')
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(',') if origin.strip()]
        return v
    
    @property
    def cors_origins_list(self) -> List[str]:
        """返回 CORS_ORIGINS 作为列表"""
        if isinstance(self.CORS_ORIGINS, list):
            return self.CORS_ORIGINS
        return [origin.strip() for origin in self.CORS_ORIGINS.split(',') if origin.strip()]
    
    def validate_jwt_secret(self):
        """验证 JWT_SECRET 是否已更改"""
        default_secret = "your-secret-key-change-in-production"
        if self.JWT_SECRET == default_secret:
            print("\n" + "="*80)
            print("❌ 安全错误：JWT_SECRET 未更改！")
            print("="*80)
            print("\n当前 JWT_SECRET 仍为默认值，这是严重的安全风险！")
            print("\n请执行以下步骤：")
            print("1. 在 .env 文件中设置强随机密钥：")
            print("   JWT_SECRET=<your-strong-random-secret-key>")
            print("\n2. 生成强随机密钥的方法：")
            print("   python -c \"import secrets; print(secrets.token_urlsafe(32))\"")
            print("\n3. 密钥建议：")
            print("   - 至少 32 个字符")
            print("   - 使用随机生成的字符串")
            print("   - 不要使用可预测的值")
            print("\n" + "="*80)
            sys.exit(1)
        
        # 检查密钥强度
        if len(self.JWT_SECRET) < 32:
            print("\n" + "="*80)
            print("⚠️  安全警告：JWT_SECRET 长度不足！")
            print("="*80)
            print(f"\n当前 JWT_SECRET 长度为 {len(self.JWT_SECRET)} 字符")
            print("建议使用至少 32 个字符的强随机密钥")
            print("\n生成强随机密钥：")
            print("   python -c \"import secrets; print(secrets.token_urlsafe(32))\"")
            print("\n" + "="*80)
            # 警告但不阻止启动（允许开发环境使用较短密钥）
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()

# 在导入时验证 JWT_SECRET（应用启动时）
settings.validate_jwt_secret()

