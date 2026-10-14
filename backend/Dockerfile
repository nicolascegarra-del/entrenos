FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/app
WORKDIR /app

RUN useradd --create-home --uid 1000 app && mkdir -p /data/garmin-tokens /data/storage && chown app /data/garmin-tokens /data/storage

COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py && pip install ".[dev]" && pip uninstall -y app-entrenos-backend && rm -rf app

COPY --chown=app . .
USER app

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m app.cli seed-catalog && gunicorn app.main:app -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 -w 2"]
