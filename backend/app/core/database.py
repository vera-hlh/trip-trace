"""
数据库初始化与连接管理
使用 SQLAlchemy async + SQLite (aiosqlite)
"""
import logging
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

logger = logging.getLogger(__name__)

# 数据库文件路径（可通过环境变量覆盖）
DB_PATH = os.environ.get("TRIPRACE_DB_PATH", "triprace.sqlite")
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # 生产环境关闭 SQL 日志，调试时可设为 True
    connect_args={"check_same_thread": False},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def _run_migrations() -> None:
    """
    数据库字段迁移（幂等，SQLite ALTER TABLE ADD COLUMN）

    新增列时，旧数据库不会自动更新，需在此处手动 ADD COLUMN。
    SQLite 若列已存在则返回错误，catch 后忽略即可（幂等安全）。

    迁移历史：
      v0.8.0  - files 表加 user_id
      v0.8.0  - trips 表加 user_id
    """
    migrations = [
        # (表名, 列名, 列定义)
        ("files",  "user_id", "VARCHAR NOT NULL DEFAULT 'local'"),
        ("trips",  "user_id", "VARCHAR NOT NULL DEFAULT 'local'"),
    ]

    async with AsyncSessionLocal() as session:
        for table, col, definition in migrations:
            try:
                await session.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
                )
                await session.commit()
                logger.info(f"迁移完成：{table}.{col}")
            except Exception:
                await session.rollback()
                # 列已存在，正常情况，忽略


async def init_db() -> None:
    """
    初始化数据库，创建所有表（若不存在则创建，已存在则跳过），
    并运行字段迁移。
    在 FastAPI startup 事件中调用。
    """
    # 导入所有模型，确保它们被注册到 Base.metadata
    from app.models import file, trip, cache, archive_log  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 对已有数据库执行字段迁移
    await _run_migrations()

    logger.info(f"数据库初始化完成：{DB_PATH}")


async def get_db():
    """
    FastAPI 依赖注入：获取数据库会话
    用法：
        @router.get("/xxx")
        async def handler(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
