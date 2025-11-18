# database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base # Import the Base class from models.py

# A simple SQLite connection for testing
DATABASE_URL = "sqlite:///./lifelink.db"

# Create the SQLAlchemy engine
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False} # SQLite specific arg
)

# Create a configured "Session" class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Creates all tables in the database based on models.py"""
    print(f"Creating database tables at {DATABASE_URL}...")
    Base.metadata.create_all(bind=engine)
    print("Database initialization complete.")

if __name__ == '__main__':
    # Run this file directly to create the database schema
    init_db()