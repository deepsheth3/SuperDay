import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.settings import settings

# Prefer plain DATABASE_URL (12-factor); else HARPER_DATABASE_URL via settings.
DATABASE_URL = os.environ.get("DATABASE_URL") or settings.database_url

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session():
    async with SessionLocal() as session:
        yield session
