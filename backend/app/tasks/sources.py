import logging

from sqlmodel import Session, select

from app.core.db import engine
from app.models import CorosCredential, User, UserStatus
from app.services import coros
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="coros.sync_user")
def coros_sync_task(user_id: int) -> int:
    with Session(engine) as session:
        return coros.sync(session, user_id)


@celery_app.task(name="coros.sync_all")
def coros_sync_all_task() -> int:
    """Sincroniza cada hora a quien tenga COROS conectado (y la cuenta activa)."""
    total = 0
    with Session(engine) as session:
        users = session.exec(
            select(CorosCredential.user_id)
            .join(User, User.id == CorosCredential.user_id)
            .where(CorosCredential.status != "expired", User.status == UserStatus.ACTIVE)
        ).all()
        for uid in users:
            total += coros.sync(session, uid)
    logger.info("COROS: %s actividades nuevas", total)
    return total


@celery_app.task(name="apple.import_export")
def apple_import_task(import_id: str) -> dict:
    """Procesa un export de Apple Salud ya subido y borra el fichero al terminar (vaya bien o mal)."""
    from app.api.apple import upload_path
    from app.models import AppleImport
    from app.models.base import utcnow
    from app.services.apple_health import import_export
    from app.services.file_import import FileImportError

    path = upload_path(import_id)
    with Session(engine) as session:
        row = session.get(AppleImport, import_id)
        if row is None or row.status not in ("queued", "processing"):
            return {}
        row.status, row.progress, row.updated_at = "processing", 0, utcnow()
        session.add(row)
        session.commit()
        user_id = row.user_id

        # El progreso se guarda en su propia sesión: la principal está ocupada importando.
        def progress(pct: int) -> None:
            with Session(engine) as s:
                r = s.get(AppleImport, import_id)
                if r is not None:
                    r.progress, r.updated_at = pct, utcnow()
                    s.add(r)
                    s.commit()

        try:
            result = import_export(session, user_id, path, progress)
            status_, error = "done", ""
        except (FileImportError, OSError) as exc:
            session.rollback()
            result, status_, error = {}, "error", str(exc)[:255]
        except Exception:
            session.rollback()
            logger.exception("Apple Salud: fallo al importar %s", import_id)
            result, status_, error = {}, "error", "No se pudo leer el export. ¿Está completo?"
        finally:
            path.unlink(missing_ok=True)
        row = session.get(AppleImport, import_id)
        if row is not None:
            row.status, row.result, row.error, row.updated_at = status_, result, error, utcnow()
            row.progress = 100 if status_ == "done" else row.progress
            session.add(row)
            session.commit()
        return result
