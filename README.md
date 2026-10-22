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

Producción en **Coolify** (VPS Contabo) con `docker-compose.prod.yml`. Coolify pone el proxy y el HTTPS
(Let's Encrypt); solo el servicio `web` es público y la API, Postgres y Redis quedan en la red interna.

### Qué hace el compose de producción

| Servicio | Función |
|---|---|
| `postgres`, `redis` | Base de datos y cola, sin puertos publicados |
| `predeploy-backup` | Copia de la BD **antes de cada despliegue** (volumen `backups`) |
| `migrate` | Aplica migraciones y catálogo de métricas una vez; el resto espera a que termine |
| `api`, `worker`, `beat` | Backend, tareas (sincronización, login de Garmin) y planificador, con healthchecks |
| `web` | Next.js; reenvía `/api` al backend interno; cabeceras de seguridad y CSP |
| `backup` | Copia diaria de la BD, se conservan `BACKUP_KEEP_DAYS` días (14 por defecto) |

En producción los logs salen en JSON (formato Klyp) y no incluyen contraseñas, tokens ni la query de las URLs.

### Paso a paso en Coolify

1. **Nuevo recurso** → *Public/Private Repository* → `nicolascegarra-del/entrenos`, rama `v1`.
   Build pack **Docker Compose**, fichero `/docker-compose.prod.yml`.
2. **Variables de entorno** (Coolify no despliega hasta que estén las obligatorias):

   | Variable | Valor |
   |---|---|
   | `POSTGRES_PASSWORD` | `openssl rand -hex 24` |
   | `JWT_SECRET_KEY` | `openssl rand -hex 32` |
   | `GARMIN_TOKEN_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` — **guárdala aparte**: cifra los tokens de Garmin y las claves de IA; si se pierde, cada usuario tendrá que reconectar Garmin y volver a poner su clave de IA |
   | `CORS_ORIGINS` | `["https://entrenos.tudominio.com"]` |
   | `APP_PUBLIC_URL` | `https://entrenos.tudominio.com` (enlaces de los emails) |
   | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_SECURITY` | Opcionales: datos SMTP de Brevo, Resend o tu dominio. Sin ellos no se envían emails y los enlaces de invitación y de contraseña se copian desde Admin |
   | `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` | Opcionales: captcha de Cloudflare Turnstile en el registro sin invitación. El autoregistro exige además SMTP (para confirmar el email) |
   | `BACKUP_KEEP_DAYS` | opcional, 14 por defecto |
   | `LOG_LEVEL` | opcional, `INFO` por defecto |

3. **Dominio**: en *Domains*, asígnalo al servicio **web** con el puerto 3000:
   `https://entrenos.tudominio.com:3000`. El DNS (registro A) debe apuntar a la IP del VPS.
4. **Deploy**. El orden es: postgres → copia previa → migraciones → api/worker/beat → web.
5. **Primer usuario** (terminal del contenedor `api` en Coolify):
   ```bash
   python -m app.cli create-user
   python -m app.cli make-admin
   ```
6. Entra en la web → **Ajustes → Garmin Connect** → conecta tu cuenta. Después, en la terminal de `api`:
   ```bash
   python -m app.cli garmin-sync --full --days 120
   ```
   para traer todo el histórico y 120 días de métricas diarias. A partir de ahí sincroniza sola según Ajustes.
7. Invita a otras personas desde **Ajustes → Usuarios**.
8. **Notificaciones en el móvil**: cada persona las activa en **Ajustes → Notificaciones**. No hay nada que
   configurar: las claves VAPID se generan solas la primera vez y se guardan cifradas en la BD. Necesitan
   HTTPS (o `localhost`); en iPhone/iPad solo funcionan con la app añadida a la pantalla de inicio (iOS 16.4+).

### Otros relojes (además de Garmin)

En **Ajustes → Otros relojes**:

- **Ficheros FIT, GPX o TCX** de cualquier marca (Suunto, Polar, COROS, Wahoo, Amazfit/Zepp, Strava…).
  Si el entreno ya estaba (por ejemplo, desde Garmin) no se duplica: misma hora ±2 min y duración ±5 %.
- **COROS**: con el email y la contraseña de COROS Training Hub (API web no oficial; solo se guarda el token
  cifrado). Se sincroniza cada hora.
- **Samsung, Xiaomi/Amazfit, Huawei y Wear OS** vía Health Connect: la app libre
  [Health Connect Webhook](https://github.com/mcnaveen/health-connect-webhook) envía los datos a
  `https://<tu-dominio>/api/v1/ingest/health-connect` con la cabecera `X-Api-Key` (token personal que se crea
  en esa misma tarjeta). La URL pública es la de **Admin → Correo**.
- **Suunto**: de momento con la exportación de FIT/GPX (su API oficial exige ser partner).

### Copias de seguridad

- Las copias quedan en el volumen `backups` del servidor (`predeploy-*.sql.gz` y `daily-*.sql.gz`).
  Para tenerlas también fuera del VPS, sincroniza ese volumen con un almacenamiento externo (p. ej. rclone a S3).
- Restaurar: `gunzip -c copia.sql.gz | psql -U entrenos -d entrenos` desde el contenedor `postgres`.
- Los `.FIT` originales están en el volumen `storage`; se pueden volver a descargar de Garmin si se pierden.

### Checklist tras cada despliegue

- [ ] La web carga y `/login` responde.
- [ ] Inicio de sesión correcto.
- [ ] Ajustes → Garmin «Conectado» y «Sincronizar ahora» termina bien.
- [ ] Sin errores en los logs de `api` y `worker` (Coolify → Logs).
- [ ] Existe la copia `predeploy-*` del despliegue.

## Contacto / equipo

Klyp · nicolascegarra@gmail.com
