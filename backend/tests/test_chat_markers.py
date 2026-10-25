from app.services import chat_markers


def test_quita_las_lineas_y_crea_botones():
    text, effects = chat_markers.parse("Hola.\n\n[[sugerencias: ¿Qué hago el domingo? | Ajústame el plan.]]\n")
    assert text == "Hola."
    assert effects == [{"tipo": "sugerencias", "sugerencias": ["¿Qué hago el domingo?", "Ajústame el plan"]}]


def test_sin_lineas_y_lineas_vacias():
    assert chat_markers.parse("Solo texto") == ("Solo texto", [])
    assert chat_markers.parse("A [[opciones: ]] B") == ("A  B", [])
    long = "x" * 80
    assert chat_markers.parse(f"Q [[OPCIONES: Sí | {long} | No | Sí]]")[1] == [
        {"tipo": "opciones", "opciones": ["Sí", "No"]}
    ]
