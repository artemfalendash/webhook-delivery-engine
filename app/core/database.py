from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_size=10, max_overflow=20)

AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

# Under the hood, async_sessionmaker wraps SQLAlchemy's standard session factory. 
# By default, standard session factories spawn synchronous Session objects.
# Passing class_=AsyncSession explicitly tells the factory: "When get_db() asks for a database session, 
# build an AsyncSession object so we can use await session.commit(), await session.execute(), and non-blocking database queries."


# Modern SQLAlchemy 2.0 Base Class
class Base(DeclarativeBase):
    pass

# Clean Async Dependency with Built-in try/finally
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as sessionx:
        yield sessionx








'''  
THE OLD VERSION


from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings


engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
'''























