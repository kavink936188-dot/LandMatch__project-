import re
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str
    phone: str
    password: str = Field(min_length=6, max_length=128)
    role: str = "buyer"

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address")
        return v

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        digits = re.sub(r"[\s\-+]", "", v)
        if not digits.isdigit() or not 10 <= len(digits) <= 13:
            raise ValueError("Enter a valid phone number (10-13 digits)")
        return digits

    @field_validator("role")
    @classmethod
    def _role(cls, v):
        if v not in ("buyer", "seller"):
            raise ValueError("Role must be buyer or seller")
        return v


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str
    phone: str
    role: str
    is_active: bool
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ImageOut(BaseModel):
    id: int
    url: str


class DocumentOut(BaseModel):
    id: int
    name: str


class LandOut(BaseModel):
    id: int
    title: str
    description: str = ""
    land_type: str
    district: str
    village: str = ""
    address: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    area_sqft: float
    price: float
    price_per_sqft: Optional[float] = None
    status: str
    created_at: datetime
    images: List[ImageOut] = []
    document_count: int = 0
    seller_name: Optional[str] = None
    seller_phone: Optional[str] = None      # only for logged-in viewers
    # owner / admin only
    survey_number: Optional[str] = None
    admin_note: Optional[str] = None
    documents: Optional[List[DocumentOut]] = None
    # admin only
    seller_email: Optional[str] = None
    fraud_score: Optional[int] = None
    fraud_flags: Optional[List[str]] = None


class RequirementCreate(BaseModel):
    district: Optional[str] = None
    land_type: Optional[str] = None
    min_area_sqft: Optional[float] = Field(default=None, ge=0)
    max_area_sqft: Optional[float] = Field(default=None, ge=0)
    min_price: Optional[float] = Field(default=None, ge=0)
    max_price: Optional[float] = Field(default=None, ge=0)
    keywords: Optional[str] = Field(default=None, max_length=255)


class RequirementOut(RequirementCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


class MatchOut(BaseModel):
    land: LandOut
    score: int
    reasons: List[str]


class ReviewIn(BaseModel):
    action: str
    note: Optional[str] = Field(default="", max_length=500)

    @field_validator("action")
    @classmethod
    def _action(cls, v):
        if v not in ("approve", "reject"):
            raise ValueError("action must be approve or reject")
        return v
