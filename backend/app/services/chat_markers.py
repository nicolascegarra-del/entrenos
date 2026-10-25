"""
Botones del chat: el entrenador termina algunos mensajes con una línea especial que la app convierte en botones.

- `[[opciones: 5K | 10K | Media | Maratón]]` → respuestas rápidas a la pregunta que acaba de hacer.
- `[[sugerencias: ¿Y el domingo? | Ajústame el plan]]` → preguntas para seguir la conversación.

Se quitan del texto antes de guardarlo y se guardan como efectos del mensaje (`tipo` opciones / sugerencias).
"""

import re

MARKER = re.compile(r"\[\[\s*(opciones|sugerencias)\s*:\s*(.*?)\]\]", re.IGNORECASE | re.DOTALL)
MAX_ITEMS = 6
MAX_LEN = 60


def parse(text: str) -> tuple[str, list[dict]]:
    """Texto sin las líneas especiales y los efectos de botones que había en ellas (como mucho uno de cada)."""
    found: dict[str, list[str]] = {}
    for kind, body in MARKER.findall(text):
        items = []
        for raw in body.split("|"):
            item = " ".join(raw.split()).strip(" .")
            if item and len(item) <= MAX_LEN and item not in items:
                items.append(item)
        if items:
            found.setdefault(kind.lower(), items[:MAX_ITEMS])
    clean = MARKER.sub("", text)
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    effects = [{"tipo": kind, kind: items} for kind, items in found.items()]
    return clean, effects
