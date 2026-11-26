"""Paso 15: la tabla de tramos de RQN 04 se arma bien a partir de los logs."""

from scripts.latency_report import percentile, rows, table

BACKEND = (
    "x INFO fsf.push tramos correo=1000 publicado=3000 llegada=4000 guardado=4500 "
    "fcm=4700 tipo=gasto_registrado\n"
    "x INFO fsf.push tramos correo=9000 publicado=None llegada=None guardado=9500 "
    "fcm=9600 tipo=por_confirmar\n"
)
# El emulador va 500 ms adelantado: recibe a las 5000 del PC (= 5500 en su reloj).
LOGCAT = (
    "I/fsf.push( 1): latencia correo→aviso ms=4500 tipo=gasto_registrado correo=1000\n"
)


def test_stretches_use_the_pc_clock_and_tolerate_missing_marks():
    first, second = rows(BACKEND, LOGCAT, offset_ms=500)
    assert first == {
        "tipo": "gasto_registrado",
        "A1": 2000,
        "A2": 1000,
        "B1": 500,
        "B2": 200,
        "C": 300,
        "total": 4000,
    }
    assert second["A1"] is None and second["C"] is None and second["B2"] == 100


def test_percentiles_are_nearest_rank():
    values = list(range(1, 21))  # 20 mediciones
    assert (percentile(values, 50), percentile(values, 95)) == (10, 19)
    assert percentile([None, None], 95) is None


def test_table_counts_the_ones_under_ten_seconds():
    text = table(rows(BACKEND, LOGCAT, 500))
    assert "total < 10 s: 1 de 1" in text and "solo Google (A1+A2+C): p50 3.30" in text
