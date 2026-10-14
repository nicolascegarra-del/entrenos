# APP ENTRENOS

App personal para sincronizar entrenamientos de Garmin, ver la progresión en gráficas y comparar las sesiones planificadas con lo que registró el reloj (plan vs real).

## Requisitos previos

- Docker + Docker Compose
- Python 3.12 (solo para ejecutar backend/tests fuera de Docker)
- Node 22 (opcional: el frontend también se puede construir dentro de Docker)

## Instalación y arranque local

```bash
cp .env.example .env              # y rellena los secretos (ver comentarios)
docker compose up -d --build      # postgres, redis, api, worker, beat, web
docker compose exec api python -m app.cli create-user
docker compose exec api python -m app.cli make-admin          # el primer usuario puede invitar a otros
docker compose exec api python -m app.cli garmin-sync --full  # tras conectar Garmin: todo el histórico
```

Garmin se conecta desde **Ajustes → Garmin Connect** (email, contraseña y código de verificación si Garmin lo
pide). La contraseña solo se usa para iniciar sesión en el worker; se guardan únicamente los tokens, cifrados
con `GARMIN_TOKEN_KEY`. Alternativa por terminal: `python -m app.cli garmin-login`.

Cada persona tiene su propio usuario y su Garmin: el administrador invita desde **Ajustes → Usuarios** y comparte
el enlace de registro (un solo uso, 7 días).

Después, el worker sincroniza solo cada 30 minutos (o con «Sincronizar ahora» en Ajustes).

- Web: http://localhost:3000
- API: http://localhost:8000 · Swagger en http://localhost:8000/docs (la web la usa vía proxy en `/api`)

La API aplica las migraciones y carga el catálogo de métricas al arrancar.

## Variables de entorno necesarias

Todas están documentadas en [`.env.example`](.env.example). Las credenciales de Garmin **no** se guardan en `.env`: se introducen una vez y solo se conservan los tokens, cifrados con `GARMIN_TOKEN_KEY` (genera la clave como indica `.env.example`; si la pierdes, cada usuario tendrá que reconectar Garmin).

## Estructura del proyecto

```
backend/    FastAPI + SQLModel + Alembic + Celery
  app/api/        routers (auth…)
  app/core/       config, BD, seguridad, errores, rate limit
  app/models/     modelos; datos dependientes del reloj en JSONB / streams por canal
  app/services/   lógica de negocio (catálogo de métricas…)
  app/tasks/      Celery (sync Garmin en fase 3)
frontend/   Next.js 15 + Tailwind v4 + shadcn/ui + TanStack Query
spike/      script de exploración de datos de Garmin
```

### Preparado para cambiar de reloj

Solo las métricas universales son columnas. El resto va en `metrics` (JSONB), las series temporales se guardan por canal (`activity_stream`) y el catálogo `metric_definition` describe cada métrica y de dónde se extrae. Un reloj con métricas nuevas no requiere migraciones: los canales desconocidos se guardan solos con su nombre de Garmin; para darles nombre y mostrarlos, se añade la métrica al catálogo (`app/services/metric_catalog.py`, admite rutas alternativas `a|b`), se sube `PARSER_VERSION` y se ejecuta `reprocess`.

## Comandos útiles

```bash
# Backend (desde backend/, con el venv del proyecto)
pytest                                   # tests (+ cobertura) contra Postgres en :5433
ruff check . && ruff format .
alembic revision --autogenerate -m "..."  # nueva migración
alembic upgrade head
python -m app.cli seed-catalog
python -m app.cli reprocess              # re-parsea la capa raw tras cambiar catálogo/parser

# Frontend (desde frontend/)
npm run dev | lint | typecheck | test | build
```

## Deploy

Docker Compose en Coolify (VPS Contabo) detrás de Nginx + Let's Encrypt. En producción: `APP_ENV=production`, `DEBUG=false`, `CORS_ORIGINS` con el dominio real y servir web y API bajo el mismo dominio para que la cookie `SameSite=Strict` funcione.

## Contacto / equipo

Klyp · nicolascegarra@gmail.com
