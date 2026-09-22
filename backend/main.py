"""
backend/main.py
FastAPI 核心入口应用 (全功能完整装配版)
包含：认证、健康画像、库存扣减、AI菜谱、备菜清单、减碳榜、标准图库、生活社区、管理员风控审计、AI厨房对话
"""
import sys
import os
import time
from datetime import datetime, timedelta

os.environ.setdefault("TZ", "Asia/Shanghai")
if hasattr(time, "tzset"):
    time.tzset()

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
from backend.seed_data import seed_demo_data
from backend.storage import STANDARDS_DIR, UPLOAD_DIR
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

    # The first Docker deployment used UTC before the runtime timezone was set.
    # Correct only records from that known deployment window; the range makes
    # this migration idempotent on later restarts.
    if os.getenv("PERSISTENT_DATA_DIR", "").strip():
        utc_window_start = datetime(2026, 9, 22, 0, 0, 0)
        utc_window_end = datetime(2026, 9, 22, 8, 0, 0)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User).where(
                    User.created_at >= utc_window_start,
                    User.created_at < utc_window_end,
                )
            )
            migrated_users = result.scalars().all()
            for user in migrated_users:
                user.created_at += timedelta(hours=8)
                if user.updated_at and utc_window_start <= user.updated_at < utc_window_end:
                    user.updated_at += timedelta(hours=8)
            if migrated_users:
                await session.commit()

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

    persistent_dir = os.getenv("PERSISTENT_DATA_DIR", "").strip()
    if persistent_dir:
        async with AsyncSessionLocal() as session:
            await seed_demo_data(session, persistent_dir)
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


@app.post("/invoke", include_in_schema=False)
async def modelscope_healthcheck():
    return {"status": "ok"}

# 挂载全部静态文件目录
app.mount("/static/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
app.mount("/static/standards", StaticFiles(directory=str(STANDARDS_DIR)), name="standards")

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
