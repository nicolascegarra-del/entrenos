from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api import (
    achievements,
    activities,
    admin,
    ai,
    apple,
    auth,
    coach,
    garmin,
    gear,
    goals,
    notifications,
    performance,
    planned_routes,
    plans,
    profile,
    progress,
    reviews,
    routes,
    sources,
    strength,
    training_plans,
    users,
    workouts,
)
from app.api import settings as settings_api
from app.core.config import get_settings
from app.core.db import engine
from app.core.errors import register_error_handlers
from app.core.logging import setup_logging
from app.core.rate_limit import limiter

settings = get_settings()
setup_logging("api")

app = FastAPI(
    title="KTrain API",
    version="0.1.0",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
)
app.state.limiter = limiter
register_error_handlers(app)


@app.exception_handler(RateLimitExceeded)
async def rate_limited(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "RATE_LIMITED",
                "message": "Demasiados intentos, espera un minuto.",
                "request_id": request.state.request_id,
            }
        },
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


app.include_router(auth.router, prefix="/api/v1")
app.include_router(activities.router, prefix="/api/v1")
app.include_router(garmin.router, prefix="/api/v1")
app.include_router(plans.router, prefix="/api/v1")
app.include_router(progress.router, prefix="/api/v1")
app.include_router(settings_api.router, prefix="/api/v1")
app.include_router(strength.router, prefix="/api/v1")
app.include_router(goals.router, prefix="/api/v1")
app.include_router(goals.paces_router, prefix="/api/v1")
app.include_router(profile.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(ai.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(training_plans.router, prefix="/api/v1")
app.include_router(gear.router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(achievements.router, prefix="/api/v1")
app.include_router(routes.router, prefix="/api/v1")
app.include_router(planned_routes.router, prefix="/api/v1")
app.include_router(planned_routes.session_router, prefix="/api/v1")
app.include_router(sources.router, prefix="/api/v1")
app.include_router(apple.router, prefix="/api/v1")
app.include_router(performance.router, prefix="/api/v1")
app.include_router(workouts.router, prefix="/api/v1")
app.include_router(coach.router, prefix="/api/v1")
app.include_router(reviews.router, prefix="/api/v1")


@app.get("/health", summary="Estado del servicio", tags=["infra"])
def health() -> dict:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}
