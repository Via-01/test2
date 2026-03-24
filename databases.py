# database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base  # Import the Base class from models.py

# SQLite connection URL (adjust path if needed)
DATABASE_URL = "sqlite:///./lifelink.db"

# Create SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}  # SQLite-specific
)

# Create a configured "Session" class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """
    Yields a database session for use with Flask routes.
    Example:
        db = next(get_db())
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """
    Creates all tables based on models.py.
    This ensures your donors table now includes bloodType column.
    """
    print(f"Initializing database tables at {DATABASE_URL}...")
    Base.metadata.create_all(bind=engine)
    print("Database initialization complete.")

if __name__ == "__main__":
    init_db()