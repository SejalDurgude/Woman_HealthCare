from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints
from typing_extensions import Annotated

NameText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]

class RegisterIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=8, max_length=128)]

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    model_config = ConfigDict(from_attributes=True)

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut

class SymptomIn(BaseModel):
    symptom: NameText
    recorded_on: date
    severity: int = Field(ge=1, le=10)
    duration_hours: Optional[float] = Field(default=None, ge=0, le=720)
    description: Optional[str] = Field(default=None, max_length=2000)
    sleep_quality: Optional[int] = Field(default=None, ge=1, le=5)  # legacy compatibility
    sleep_hours: Optional[float] = Field(default=None, ge=0, le=24)
    mood: Optional[str] = Field(default=None, max_length=40)
    tags: Optional[str] = Field(default=None, max_length=300)
    cycle_day: Optional[int] = Field(default=None, ge=1, le=45)

class SymptomOut(SymptomIn):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
