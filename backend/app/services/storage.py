"""
Almacenamiento de ficheros (.FIT originales). Hoy en disco local (volumen Docker);
la interfaz permite cambiar a un S3 compatible sin tocar el resto del código.
"""

from pathlib import Path
from typing import Protocol

from app.core.config import get_settings


class ObjectStorage(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes | None: ...


class LocalStorage:
    def __init__(self, base_dir: str | Path) -> None:
        self.base = Path(base_dir).resolve()

    def _path(self, key: str) -> Path:
        path = (self.base / key).resolve()
        if self.base not in path.parents:
            raise ValueError("Clave de almacenamiento fuera del directorio base.")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes | None:
        path = self._path(key)
        return path.read_bytes() if path.exists() else None


def get_storage() -> ObjectStorage:
    return LocalStorage(get_settings().storage_dir)
