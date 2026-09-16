from datetime import datetime
from sqlalchemy import Column, DateTime, String, func
from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=True)
    full_name = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    role = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=True)
