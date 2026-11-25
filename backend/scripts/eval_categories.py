"""Mide el LLM de categorías con comercios inventados que no encajan en ninguna regla (Paso 10).

    cd backend && .venv/Scripts/python.exe -m scripts.eval_categories [modelo]

No corre en la CI (necesita Ollama). Datos simulados: la medición con comercios reales queda
pendiente, como la de la extracción (antes del Paso 16).
"""

import statistics
import sys
import time

from app import categorize
from app.extract import llm

NAMES = ["Alimentos", "Entretenimiento", "Otros", "Salud", "Servicios", "Transporte"]
# (comercio, categoría esperada). "Otros" cuando no hay forma razonable de saberlo.
CASES = [
    ("TIENDA DE BARRIO EJEMPLO", "Alimentos"),
    ("FRUTERIA LA COSECHA INVENTADA", "Alimentos"),
    ("HAMBURGUESAS EL GORDO FICTICIO", "Alimentos"),
    ("SUSHI INVENTADO 93", "Alimentos"),
    ("BUSES INTERMUNICIPALES FICTICIOS", "Transporte"),
    ("MOTOTAXI INVENTADO", "Transporte"),
    ("APP DE TRANSPORTE FICTICIA", "Transporte"),
    ("BOLERA INVENTADA", "Entretenimiento"),
    ("CONCIERTOS FICTICIOS SAS", "Entretenimiento"),
    ("VIDEOJUEGOS INVENTADOS", "Entretenimiento"),
    ("CONSULTORIO DENTAL FICTICIO", "Salud"),
    ("FISIOTERAPIA INVENTADA", "Salud"),
    ("EMPRESA DE ASEO FICTICIA ESP", "Servicios"),
    ("PLAN CELULAR INVENTADO", "Servicios"),
    ("FERRETERIA EJEMPLO SAS", "Otros"),
    ("PERSONA EJEMPLO", "Otros"),
    ("ZAPATERIA INVENTADA", "Otros"),
    ("INVERSIONES XYZ SAS", "Otros"),
]
# Escritos DESPUÉS de ajustar el prompt (sus descripciones usan palabras de CASES): estos miden
# sin ese sesgo.
HELD_OUT = [
    ("PESCADERIA EL MAR INVENTADA", "Alimentos"),
    ("EMPANADAS DOÑA FICTICIA", "Alimentos"),
    ("LAVADERO DE CARROS INVENTADO", "Transporte"),
    ("TALLER DE MOTOS FICTICIO", "Transporte"),
    ("PARQUE DE DIVERSIONES INVENTADO", "Entretenimiento"),
    ("KARAOKE FICTICIO", "Entretenimiento"),
    ("PSICOLOGIA INVENTADA IPS", "Salud"),
    ("CENTRO MEDICO FICTICIO", "Salud"),
    ("ADMINISTRACION CONJUNTO INVENTADO", "Servicios"),
    ("TELEVISION POR CABLE FICTICIA", "Servicios"),
    ("MARIA FICTICIA PEREZ", "Otros"),
    ("COMERCIALIZADORA ABC SAS", "Otros"),
]


def run(title: str, cases: list, model: str | None) -> None:
    assert all(categorize.rule_category(m) is None for m, _ in cases), (
        "un caso ya tiene regla"
    )
    print(f"== {title}")
    hits, otros, invalid, times = 0, 0, 0, []
    for merchant, expected in cases:
        t = time.perf_counter()
        got = llm.ask_category(merchant, NAMES, model=model)
        times.append(time.perf_counter() - t)
        invalid += got is None
        got = got or "Otros"
        otros += got == "Otros"
        hits += got == expected
        print(
            f"{'OK ' if got == expected else 'MAL'} {merchant:<36} esperado={expected:<16} llm={got}"
        )
    n = len(cases)
    print(
        f"\naciertos: {hits}/{n} ({100 * hits / n:.0f} %) · a Otros: {otros} · inválidas: {invalid}"
    )
    print(
        f"latencia: primera {times[0]:.2f} s · mediana {statistics.median(times[1:]):.2f} s\n"
    )


def main(model: str | None) -> None:
    run("casos usados al ajustar el prompt", CASES, model)
    run("casos no vistos al ajustar el prompt", HELD_OUT, model)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
