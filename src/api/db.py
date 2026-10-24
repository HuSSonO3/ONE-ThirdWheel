import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(os.environ.get("DATABASE_URL", "postgresql+psycopg://chat:chat@localhost:5432/chat"))
SessionLocal = sessionmaker(engine)
