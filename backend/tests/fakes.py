"""Dobles de prueba compartidos: Garmin falso con datos de los fixtures y storage en memoria."""

import copy
import json
from datetime import datetime, timedelta
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "garmin"


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


class FakeGarmin:
    """Simula Garmin Connect con N actividades (más reciente primero) basadas en el fixture."""

    def __init__(self, n: int = 3) -> None:
        base = load("activity_summary")
        self.activities = []
        for i in range(n):
            s = copy.deepcopy(base)
            s["activityId"] = 9000000100 - i
            start = datetime(2026, 10, 14, 15, 58, 5) - timedelta(days=i)
            s["startTimeGMT"] = start.strftime("%Y-%m-%d %H:%M:%S")
            s["startTimeLocal"] = (start + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
            self.activities.append(s)
        self.detail_calls = 0

    def get_activities(self, start: int, limit: int) -> list[dict]:
        return self.activities[start : start + limit]

    def get_activity_details(self, activity_id: int) -> dict:
        self.detail_calls += 1
        return load("activity_details")

    def get_activity_splits(self, activity_id: int) -> dict:
        return load("activity_splits")

    def download_fit(self, activity_id: int) -> bytes:
        return b"PK-fake-fit"

    def get_devices(self) -> list[dict]:
        return [{"deviceId": 1000000001, "productDisplayName": "Forerunner 735XT"}]

    def get_daily(self, day: str) -> dict:
        return load("daily")


class MemoryStorage:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        self.files[key] = data

    def get(self, key: str) -> bytes | None:
        return self.files.get(key)

    def delete(self, key: str) -> None:
        self.files.pop(key, None)
