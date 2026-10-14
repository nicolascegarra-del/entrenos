from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models.base import created_at_field


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(max_length=255, unique=True, index=True)
    password_hash: str = Field(max_length=255)
    created_at: datetime = created_at_field()
