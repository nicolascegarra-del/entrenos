"""
Comandos de administración.

    python -m app.cli create-user     # pide email y contraseña por terminal
    python -m app.cli seed-catalog    # carga/actualiza el catálogo de métricas
"""

import argparse
from getpass import getpass

from sqlmodel import Session, select

from app.core.db import engine
from app.core.security import hash_password
from app.models import User
from app.services.metric_catalog import seed_catalog

MIN_PASSWORD_LENGTH = 10


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


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    parser.add_argument("command", choices=["create-user", "seed-catalog"])
    args = parser.parse_args()
    if args.command == "create-user":
        create_user()
    else:
        with Session(engine) as session:
            print(f"Catálogo: {seed_catalog(session)} métricas.")


if __name__ == "__main__":
    main()
