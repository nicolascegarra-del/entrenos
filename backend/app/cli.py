"""
Comandos de administración (ejecutar dentro del contenedor `api`):

    python -m app.cli create-user              # usuario de la app (email + contraseña)
    python -m app.cli seed-catalog             # carga/actualiza el catálogo de métricas
    python -m app.cli garmin-login             # conecta tu cuenta de Garmin (solo guarda tokens)
    python -m app.cli garmin-sync [--full]     # sincroniza ya (--full: todo el histórico)
    python -m app.cli reprocess [--all]        # re-parsea la capa raw tras cambios del catálogo
    python -m app.cli make-admin               # da permisos de administrador (invitar usuarios)
"""

import argparse
from getpass import getpass

from sqlmodel import Session, select

from app.core.db import engine
from app.core.security import hash_password
from app.models import User
from app.services.metric_catalog import seed_catalog

MIN_PASSWORD_LENGTH = 10


def _ask_user(session: Session) -> User:
    users = session.exec(select(User)).all()
    if len(users) == 1:
        return users[0]
    email = input("Email del usuario de la app: ").strip().lower()
    user = session.exec(select(User).where(User.email == email)).first()
    if user is None:
        raise SystemExit("Ese usuario no existe. Créalo antes con create-user.")
    return user


def create_user() -> None:
    email = input("Email: ").strip().lower()
    password = getpass("Contraseña (mín. 10 caracteres): ")
    if len(password) < MIN_PASSWORD_LENGTH or password != getpass("Repite la contraseña: "):
        raise SystemExit("Contraseña demasiado corta o no coincide.")
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == email)).first()
        if user:
            user.password_hash = hash_password(password)
            print("Contraseña actualizada.")
        else:
            session.add(User(email=email, password_hash=hash_password(password)))
            print("Usuario creado.")
        session.commit()


def garmin_login() -> None:
    from app.services.garmin_client import connect_with_credentials
    from app.services.profile import apply_garmin_profile

    with Session(engine) as session:
        user = _ask_user(session)
    print(f"Conectando Garmin para {user.email}. La contraseña no se guarda; solo los tokens cifrados.")
    email = input("Email de Garmin Connect: ").strip()
    password = getpass("Contraseña de Garmin (no se muestra): ")
    profile = connect_with_credentials(user.id, email, password, prompt_mfa=lambda: input("Código MFA: ").strip())
    with Session(engine) as session:
        apply_garmin_profile(session, user.id, profile)
    print("✔ Garmin conectado.")


def make_admin() -> None:
    with Session(engine) as session:
        email = input("Email del usuario que será administrador: ").strip().lower()
        user = session.exec(select(User).where(User.email == email)).first()
        if user is None:
            raise SystemExit("Ese usuario no existe.")
        user.is_admin = True
        session.add(user)
        session.commit()
    print(f"✔ {email} ahora es administrador (puede invitar a otras personas).")


def garmin_sync(full: bool, days: int) -> None:
    from app.tasks.sync import sync_user

    with Session(engine) as session:
        user = _ask_user(session)
    print("Sincronizando… (el histórico completo puede tardar varios minutos)")
    print("Resultado:", sync_user(user.id, days=days, max_new=None if full else 50))


def reprocess(all_activities: bool) -> None:
    from app.services.sync_service import reprocess_activities

    with Session(engine) as session:
        user = _ask_user(session)
        count = reprocess_activities(session, user.id, only_outdated=not all_activities)
    print(f"Actividades reprocesadas: {count}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    parser.add_argument(
        "command", choices=["create-user", "seed-catalog", "garmin-login", "garmin-sync", "reprocess", "make-admin"]
    )
    parser.add_argument("--full", action="store_true", help="garmin-sync: importar todo el histórico")
    parser.add_argument("--days", type=int, default=7, help="garmin-sync: días de métricas diarias")
    parser.add_argument("--all", action="store_true", help="reprocess: todas, no solo las desactualizadas")
    args = parser.parse_args()

    if args.command == "create-user":
        create_user()
    elif args.command == "garmin-login":
        garmin_login()
    elif args.command == "garmin-sync":
        garmin_sync(args.full, args.days)
    elif args.command == "make-admin":
        make_admin()
    elif args.command == "reprocess":
        reprocess(args.all)
    else:
        with Session(engine) as session:
            print(f"Catálogo: {seed_catalog(session)} métricas.")


if __name__ == "__main__":
    main()
