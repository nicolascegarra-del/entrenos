FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/app
WORKDIR /app

RUN useradd --create-home --uid 1000 app && mkdir -p /data/garmin-tokens /data/storage && chown app /data/garmin-tokens /data/storage

# Solo dependencias de ejecución (los tests y el linter se ejecutan fuera de la imagen, en local y en CI).
COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py && pip install . && pip uninstall -y app-entrenos-backend && rm -rf app

COPY --chown=app . .
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status != 200)"

# Las migraciones las aplica el servicio `migrate` (una sola vez por despliegue), no cada arranque de la API.
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "-w", "2", "--graceful-timeout", "30"]
