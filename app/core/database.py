from typing import AsyncGenerator

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import BASE_DIR, settings
DATABASE_URL: str = settings.DATABASE_URL

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=120,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    # connect_args={
    #     "ssl": "require",
    #     "server_settings": {
    #         "tcp_keepalives_idle": "20",
    #         "tcp_keepalives_interval": "5",
    #         "tcp_keepalives_count": "3",
    #     }
    # },
    connect_args={
        **({"ssl": "require"} if "neon.tech" in DATABASE_URL else {}),
        "server_settings": {
            "tcp_keepalives_idle": "20",
            "tcp_keepalives_interval": "5",
            "tcp_keepalives_count": "3",
        }
    },
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

class Base(DeclarativeBase):
    pass


def get_sync_database_url() -> str:
    return str(make_url(DATABASE_URL).set(drivername="postgresql+psycopg2"))


def run_migrations() -> None:
    print("INFO:     Connecting to PostgreSQL and applying Alembic migrations...")
    try:
        alembic_config = Config(str(BASE_DIR / "alembic.ini"))
        alembic_config.set_main_option("script_location", str(BASE_DIR / "migrations"))
        alembic_config.set_main_option("sqlalchemy.url", DATABASE_URL)
        command.upgrade(alembic_config, "head")
        print("INFO:     Database migrations applied successfully.")
    except Exception as e:
        print(f"ERROR:    Failed to apply database migrations: {e}")
        raise e

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            try:
                await session.close()
            except Exception:
                pass  # ignore close errors on dropped connections

async def db_execute(fn):
    """
    Execute a database operation with a fresh session.
    Use this inside long-running background tasks instead of reusing a session.
    """
    async with AsyncSessionLocal() as session:
        try:
            result = await fn(session)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise
        finally:
            try:
                await session.close()
            except Exception:
                pass
