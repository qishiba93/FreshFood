"""
backend/database.py
异步 MySQL 数据库引擎与 Session 依赖管理
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from dotenv import load_dotenv

load_dotenv()

def normalize_database_url(url: str) -> str:
    """Convert common cloud database URLs to SQLAlchemy async drivers."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("mysql://"):
        return url.replace("mysql://", "mysql+aiomysql://", 1)
    if url.startswith("sqlite:///") and not url.startswith("sqlite+aiosqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return url


DATABASE_URL = normalize_database_url(
    os.getenv(
        "DATABASE_URL",
        "mysql+aiomysql://root:123456@127.0.0.1:3306/freshplate_db?charset=utf8mb4",
    )
)

engine_options = {"echo": False, "pool_pre_ping": True}
if not DATABASE_URL.startswith("sqlite+aiosqlite:///"):
    engine_options.update(pool_size=10, max_overflow=20)

engine = create_async_engine(DATABASE_URL, **engine_options)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    """FastAPI 数据库会话依赖"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
