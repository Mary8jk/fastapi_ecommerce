from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.ext.asyncio import (create_async_engine,
                                    async_sessionmaker,
                                    AsyncSession)


# Строка подключения для SQLite
DATABASE_URL = "sqlite:///ecommerce.db"

# Создаём Engine
engine = create_engine(DATABASE_URL, echo=True)

# Настраиваем фабрику сеансов
# SessionLocal — это фабрика, а не сам сеанс.
# Она создаёт новые экземпляры сеансов (Session) при вызове,
# например, session = SessionLocal().
SessionLocal = sessionmaker(bind=engine)

# Строка подключения для PostgreSQl
DATABASE_URL = "postgresql+asyncpg://fastapi_user:1234@localhost:5432/fastapi_db"

# Создаём Engine
async_engine = create_async_engine(DATABASE_URL, echo=True)

# Настраиваем фабрику сеансов
async_session_maker = async_sessionmaker(async_engine,
                                         expire_on_commit=False,
                                         class_=AsyncSession)


class Base(DeclarativeBase):
    pass
