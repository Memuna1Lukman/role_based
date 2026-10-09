from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.engine import URL
from .config import settings


SQLALCHEMY_DATABASE_URL = settings.database_url or URL.create(
    "postgresql+psycopg2",
    username=settings.database_username,
    password=settings.database_password,
    host=settings.database_hostname,
    port=int(settings.database_port),
    database=settings.database_name,
)


engine = create_engine(SQLALCHEMY_DATABASE_URL)


SessionLocal = sessionmaker(autoflush=False,autocommit=False,bind=engine)


Base= declarative_base()
   


def get_db():
    db=SessionLocal()
    try:
        yield db
    finally:
        db.close()

