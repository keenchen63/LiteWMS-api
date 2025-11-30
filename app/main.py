from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.routers import categories, warehouses, items, transactions, mfa
from app.database import engine, Base
from app.config import settings
import traceback

# 初始化速率限制器
limiter = Limiter(key_func=get_remote_address)

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="LiteWMS API",
    description="LiteWMS 轻量级仓库管理系统后端 API",
    version="1.0.0"
)

# 配置速率限制器
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 添加 slowapi 中间件以支持速率限制
from slowapi.middleware import SlowAPIMiddleware
app.add_middleware(SlowAPIMiddleware)

# CORS middleware - must be added before routers
# Get CORS origins list
cors_origins = settings.cors_origins_list
import logging
logger = logging.getLogger(__name__)
logger.info(f"CORS allowed origins: {cors_origins}")

# Ensure we have the correct origins
if not cors_origins:
    cors_origins = ["http://localhost:3000", "http://localhost:5173"]
    logger.warning(f"CORS_ORIGINS not set, using defaults: {cors_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

# Include routers
app.include_router(categories.router, prefix="/api/categories", tags=["categories"])
app.include_router(warehouses.router, prefix="/api/warehouses", tags=["warehouses"])
app.include_router(items.router, prefix="/api/items", tags=["items"])
app.include_router(transactions.router, prefix="/api/transactions", tags=["transactions"])
app.include_router(mfa.router, prefix="/api/mfa", tags=["mfa"])

@app.get("/")
def root():
    return {"message": "LiteWMS API", "version": "1.0.0"}

@app.get("/api/health")
def health_check():
    return {"status": "healthy"}

@app.get("/api/test-cors")
def test_cors():
    """Test endpoint to verify CORS is working"""
    return {
        "message": "CORS test successful",
        "cors_origins": cors_origins
    }

# Global exception handler to ensure CORS headers are always present
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all exceptions and ensure CORS headers are present"""
    import logging
    logger = logging.getLogger(__name__)
    logger.error(f"Unhandled exception: {type(exc).__name__}: {str(exc)}", exc_info=True)
    
    # Get origin from request
    origin = request.headers.get("origin", "*")
    if origin not in cors_origins and "*" not in cors_origins:
        origin = cors_origins[0] if cors_origins else "*"
    
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"},
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": "*",
        }
    )

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions and ensure CORS headers are present"""
    origin = request.headers.get("origin", "*")
    if origin not in cors_origins and "*" not in cors_origins:
        origin = cors_origins[0] if cors_origins else "*"
    
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": "*",
        }
    )

