"""
Spike de conexión con Garmin Connect.

Objetivo: comprobar qué datos devuelve Garmin para tu reloj antes de diseñar los
modelos definitivos. Descarga las últimas N actividades (resumen, splits, detalle
y .FIT original) y las métricas diarias de los últimos días a `spike/output/`.

Las credenciales se piden por terminal (getpass) y NO se guardan: tras el primer
login solo se persisten los tokens OAuth en ~/.garminconnect (fuera del repo).

Uso:
    python spike/garmin_spike.py --activities 10 --days 7
"""

from __future__ import annotations

import argparse
import json
import zipfile
from datetime import date, timedelta
from getpass import getpass
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from garminconnect import Garmin, GarminConnectAuthenticationError

TOKEN_DIR = Path.home() / ".garminconnect"
OUTPUT_DIR = Path(__file__).parent / "output"


def login() -> Garmin:
    """Reutiliza los tokens guardados; si no existen o caducaron, pide credenciales."""
    try:
        client = Garmin()
        client.login(str(TOKEN_DIR))
        print(f"✔ Sesión reutilizada desde {TOKEN_DIR}")
        return client
    except (FileNotFoundError, GarminConnectAuthenticationError):
        pass  # Sin tokens válidos: login con credenciales.

    email = input("Email de Garmin Connect: ").strip()
    password = getpass("Contraseña (no se muestra ni se guarda): ")
    client = Garmin(email=email, password=password, prompt_mfa=lambda: input("Código MFA: ").strip())
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    # Con tokenstore, la librería persiste los tokens tras el login con credenciales.
    client.login(str(TOKEN_DIR))
    print(f"✔ Login correcto. Tokens guardados en {TOKEN_DIR}")
    return client


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def safe(label: str, fn: Callable[[], Any]) -> Any:
    """Ejecuta una llamada a Garmin sin abortar el spike si un endpoint falla o no aplica al reloj."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - en un spike queremos ver todos los fallos
        print(f"  ⚠ {label}: {type(exc).__name__}: {exc}")
        return None


def fetch_activities(client: Garmin, limit: int) -> list[dict]:
    activities = client.get_activities(0, limit)
    print(f"\n▶ {len(activities)} actividades")
    for act in activities:
        act_id = act["activityId"]
        sport = act.get("activityType", {}).get("typeKey")
        print(f"  · {act.get('startTimeLocal')}  {sport:<20} {act.get('activityName')}")
        base = OUTPUT_DIR / "activities" / str(act_id)
        save_json(base / "summary.json", act)
        save_json(base / "splits.json", safe("splits", lambda: client.get_activity_splits(act_id)))
        save_json(base / "details.json", safe("details", lambda: client.get_activity_details(act_id)))
        if sport and "strength" in sport:
            save_json(base / "exercise_sets.json", safe("sets", lambda: client.get_activity_exercise_sets(act_id)))

        fit_zip = safe(
            "fit",
            lambda: client.download_activity(act_id, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL),
        )
        if fit_zip:
            with zipfile.ZipFile(BytesIO(fit_zip)) as zf:
                zf.extractall(base / "fit")
    return activities


def fetch_daily(client: Garmin, days: int) -> None:
    print(f"\n▶ Métricas diarias ({days} días)")
    today = date.today()
    for i in range(days):
        day = (today - timedelta(days=i)).isoformat()
        base = OUTPUT_DIR / "daily" / day
        save_json(base / "stats.json", safe("stats", lambda: client.get_stats(day)))
        save_json(base / "rhr.json", safe("rhr", lambda: client.get_rhr_day(day)))
        save_json(base / "hrv.json", safe("hrv", lambda: client.get_hrv_data(day)))
        save_json(base / "sleep.json", safe("sleep", lambda: client.get_sleep_data(day)))
        save_json(base / "max_metrics.json", safe("vo2max", lambda: client.get_max_metrics(day)))
        save_json(base / "training_status.json", safe("training", lambda: client.get_training_status(day)))
        print(f"  · {day}")
    start = (today - timedelta(days=days - 1)).isoformat()
    save_json(OUTPUT_DIR / "daily" / "body_battery.json",
              safe("body battery", lambda: client.get_body_battery(start, today.isoformat())))
    save_json(OUTPUT_DIR / "user_profile.json", safe("perfil", client.get_user_profile))
    save_json(OUTPUT_DIR / "devices.json", safe("dispositivos", client.get_devices))


def main() -> None:
    parser = argparse.ArgumentParser(description="Spike de datos Garmin Connect")
    parser.add_argument("--activities", type=int, default=10)
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    client = login()
    fetch_activities(client, args.activities)
    fetch_daily(client, args.days)
    print(f"\n✔ Hecho. Datos en {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
