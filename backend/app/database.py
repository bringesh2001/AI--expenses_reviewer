from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from .config import settings

# Supabase Transaction mode (port 6543) uses pgbouncer — persistent connection
# pools are not supported. NullPool creates a fresh connection per request.
_use_nullpool = ":6543" in settings.database_url
_ssl = {"ssl": "require"} if "supabase.co" in settings.database_url else {}

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    connect_args=_ssl,
    **({"poolclass": NullPool} if _use_nullpool else {"pool_size": 5, "max_overflow": 10}),
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
