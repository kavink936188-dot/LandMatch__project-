from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    phone = Column(String(20), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(10), nullable=False, default="buyer")  # buyer | seller | admin
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)

    lands = relationship("Land", back_populates="seller", cascade="all, delete-orphan")
    requirements = relationship("BuyerRequirement", back_populates="buyer", cascade="all, delete-orphan")


class Land(Base):
    __tablename__ = "lands"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    land_type = Column(String(20), nullable=False, index=True)
    district = Column(String(60), nullable=False, index=True)
    village = Column(String(100), default="")
    address = Column(String(255), default="")
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    area_sqft = Column(Float, nullable=False)
    price = Column(Float, nullable=False)  # total price in INR
    survey_number = Column(String(60), default="", index=True)

    status = Column(String(10), default="pending", index=True)  # pending | approved | rejected | sold
    fraud_score = Column(Integer, default=0)
    fraud_flags = Column(Text, default="[]")  # JSON list of strings
    admin_note = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow, index=True)

    seller = relationship("User", back_populates="lands")
    images = relationship("LandImage", back_populates="land", cascade="all, delete-orphan")
    documents = relationship("LandDocument", back_populates="land", cascade="all, delete-orphan")


class LandImage(Base):
    __tablename__ = "land_images"

    id = Column(Integer, primary_key=True)
    land_id = Column(Integer, ForeignKey("lands.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    url = Column(String(255), nullable=False)

    land = relationship("Land", back_populates="images")


class LandDocument(Base):
    __tablename__ = "land_documents"

    id = Column(Integer, primary_key=True)
    land_id = Column(Integer, ForeignKey("lands.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)       # stored name on disk
    original_name = Column(String(255), default="")

    land = relationship("Land", back_populates="documents")


class BuyerRequirement(Base):
    __tablename__ = "buyer_requirements"

    id = Column(Integer, primary_key=True)
    buyer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    district = Column(String(60), nullable=True)
    land_type = Column(String(20), nullable=True)
    min_area_sqft = Column(Float, nullable=True)
    max_area_sqft = Column(Float, nullable=True)
    min_price = Column(Float, nullable=True)
    max_price = Column(Float, nullable=True)
    keywords = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    buyer = relationship("User", back_populates="requirements")
