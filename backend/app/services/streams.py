"""Reducción de series temporales para enviar a las gráficas (miles de puntos → ~1000)."""

import math

# Canales que no se promedian (se toma el primer valor del tramo): coordenadas y acumulados.
_PICK_FIRST = {"lat", "lon", "time", "distance"}


def downsample(channels: dict[str, list[float | None]], max_points: int) -> dict[str, list[float | None]]:
    """
    Reduce todos los canales al mismo número de puntos agrupando en tramos consecutivos.

    Los canales continuos (FC, velocidad…) se promedian ignorando huecos; las
    coordenadas y acumulados toman el primer valor del tramo para no deformar el recorrido.
    """
    if not channels:
        return {}
    length = max(len(v) for v in channels.values())
    if length <= max_points:
        return channels
    size = math.ceil(length / max_points)

    def reduce(name: str, values: list[float | None]) -> list[float | None]:
        out: list[float | None] = []
        for start in range(0, length, size):
            bucket = [v for v in values[start : start + size] if v is not None]
            if not bucket:
                out.append(None)
            elif name in _PICK_FIRST:
                out.append(bucket[0])
            else:
                out.append(sum(bucket) / len(bucket))
        return out

    return {name: reduce(name, values) for name, values in channels.items()}
