from pydantic import BaseModel, Field, field_validator

# En el login basta una validación de forma: el email solo se usa para buscar al usuario.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class LoginRequest(BaseModel):
    email: str = Field(max_length=255, pattern=EMAIL_PATTERN)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class LimitsRead(BaseModel):
    """None = sin límite."""

    history_days: int | None = None
    max_goals: int | None = None
    max_sessions_week: int | None = None


class UserRead(BaseModel):
    id: int
    email: str
    is_admin: bool = False
    tier: str = "full"  # full | basic
    onboarded: bool = True  # False = mostrar la configuración guiada
    limits: LimitsRead = LimitsRead()
