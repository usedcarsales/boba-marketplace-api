import ssl as _ssl

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import get_settings

settings = get_settings()

# For Neon with asyncpg: strip ?ssl=require from URL, use connect_args instead
db_url = settings.database_url.replace("?ssl=require", "").replace("&ssl=require", "")

# Create proper SSL context for asyncpg
ssl_context = _ssl.create_default_context()

engine = create_async_engine(
    db_url,
    echo=False,
    pool_size=3,
    max_overflow=2,
    pool_timeout=30,
    pool_recycle=300,
    connect_args={"ssl": ssl_context},
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("Database initialized successfully")
    except Exception as e:
        print(f"Warning: init_db failed: {e}")
