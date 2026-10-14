"""Formato de números para textos en español (es-ES)."""


def num(value: float, decimals: int = 0, sign: bool = False) -> str:
    """Número con coma decimal: 1.22 → "1,22"; con `sign`, "+3"."""
    text = f"{value:{'+' if sign else ''}.{decimals}f}"
    return text.replace(".", ",")
