# databases.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base

DATABASE_URL = "sqlite:///./lifelink.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    print(f"Initialising database at {DATABASE_URL}...")
    Base.metadata.create_all(bind=engine)
    print("Database ready.")

if __name__ == "__main__":
    init_db()
