import pytest

from app.services.readiness import ALERT, GOOD, NODATA, WATCH, readiness


@pytest.mark.parametrize(
    ("tsb", "acwr", "status", "title"),
    [
        (None, None, NODATA, "Sin datos todavía"),
        (-35, 1.0, ALERT, "Sobrecargado"),
        (-15, 1.0, WATCH, "Cansado"),
        (20, None, GOOD, "Muy descansado"),
        (8, 1.0, GOOD, "Fresco"),
        (0, 1.0, GOOD, "En equilibrio"),
    ],
)
def test_readiness_cuando_frescura_entonces_estado_esperado(tsb, acwr, status, title):
    result = readiness(tsb, acwr)
    assert (result.status, result.title) == (status, title)


def test_readiness_cuando_pico_de_carga_entonces_avisa_aunque_este_fresco():
    assert readiness(10, 1.6).status == ALERT
    assert readiness(10, 1.4).status == WATCH


def test_readiness_cuando_sin_acwr_entonces_decide_solo_por_frescura():
    assert readiness(-5, None).status == GOOD
