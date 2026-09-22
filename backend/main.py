"""
backend/main.py
FastAPI 核心入口应用 (全功能完整装配版)
包含：认证、健康画像、库存扣减、AI菜谱、备菜清单、减碳榜、标准图库、生活社区、管理员风控审计、AI厨房对话
"""
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from backend.database import engine, Base
from backend.database import AsyncSessionLocal
from backend.auth import get_password_hash
from backend.models import User
# 引入全部业务路由群
from backend.routers import (
    auth_router,
    health,
    pantry,
    recipe,
    shopping,
    carbon,
    standard_images,
    community,
    admin_audit,
    chat
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 服务启动时，安全确保全套数据库新表自动同步创建
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    admin_username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "").strip()
    admin_password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "").strip()
    if admin_username and admin_password:
        async with AsyncSessionLocal() as session:
            existing = await session.execute(select(User).where(User.username == admin_username))
            if existing.scalar_one_or_none() is None:
                session.add(User(
                    username=admin_username,
                    hashed_password=get_password_hash(admin_password),
                    role="super_admin",
                    status=1,
                ))
                await session.commit()
    yield

app = FastAPI(title="智鲜厨房 OS - 全场景精准健康厨房", version="3.3.0", lifespan=lifespan)

# 允许跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册全部 API 业务路由群
app.include_router(auth_router.router)
app.include_router(health.router)
app.include_router(pantry.router)
app.include_router(recipe.router)
app.include_router(shopping.router)
app.include_router(carbon.router)
app.include_router(standard_images.router)
app.include_router(community.router)
app.include_router(admin_audit.router)
app.include_router(chat.router)


@app.get("/api/healthz", tags=["system"])
async def healthcheck():
    return {"status": "ok", "service": "freshfood"}

# 挂载全部静态文件目录
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads")
COMMUNITY_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads", "community")
STANDARDS_DIR = os.path.join(os.path.dirname(__file__), "static", "standards")
DEFAULTS_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads", "defaults")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(COMMUNITY_DIR, exist_ok=True)
os.makedirs(STANDARDS_DIR, exist_ok=True)
os.makedirs(DEFAULTS_DIR, exist_ok=True)

app.mount("/static/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static/standards", StaticFiles(directory=STANDARDS_DIR), name="standards")

# 挂载前端网页目录
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("APP_ENV", "development") == "development",
    )
