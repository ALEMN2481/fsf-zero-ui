"""Paso 10: reglas de categorización y respuesta del LLM (sin BD ni Ollama)."""

import json
import threading
import tomllib

import pytest

from app import categorize
from app.categorize import merchant_key, rule_category
from app.config import settings
from app.extract import llm

REAL_SCHEDULE = categorize.schedule  # al importar, antes de que conftest la anule
GLOBALS = {"Alimentos", "Transporte", "Entretenimiento", "Servicios", "Salud", "Otros"}


@pytest.mark.parametrize(
    "merchant, category",
    [
        ("SUPERMERCADO EJEMPLO SAS", "Alimentos"),
        ("PANADERIA EJEMPLO", "Alimentos"),
        ("CAFETERIA EJEMPLO", "Alimentos"),
        ("CAFE EJEMPLO SAS", "Alimentos"),
        ("RESTAURANTE EJEMPLO SAS", "Alimentos"),
        ("Almacenes Éxito Calle 80", "Alimentos"),
        ("TIENDA D1 BOSA", "Alimentos"),
        ("TIENDAS ARA 123", "Alimentos"),
        ("JUAN VALDEZ CAFE", "Alimentos"),
        ("DLO*RAPPI COLOMBIA", "Alimentos"),
        ("UBER *TRIP", "Transporte"),
        ("EDS TERPEL LA 30", "Transporte"),
        ("METRO DE MEDELLIN", "Transporte"),
        ("PEAJE CHUSACA", "Transporte"),
        ("NETFLIX.COM", "Entretenimiento"),
        ("SPOTIFY P1234", "Entretenimiento"),
        ("CINE COLOMBIA", "Entretenimiento"),
        ("GIMNASIO INVENTADO", "Entretenimiento"),
        ("EMPRESA DE ENERGIA EJEMPLO", "Servicios"),
        ("INTERNET EJEMPLO", "Servicios"),
        ("CLARO COLOMBIA", "Servicios"),
        ("ACUEDUCTO INVENTADO", "Servicios"),
        ("EPM", "Servicios"),
        ("DROGUERIA EJEMPLO", "Salud"),
        ("Farmacia Ficticia", "Salud"),
        ("CRUZ VERDE 45", "Salud"),
        ("CAJERO EJEMPLO CENTRO", "Otros"),
    ],
)
def test_known_merchants(merchant, category):
    assert rule_category(merchant) == category


@pytest.mark.parametrize(
    "merchant",
    [
        "ARANDANOS DEL CAMPO",  # ARA solo como palabra completa
        "ARAÑA SAS",  # Ñ también cuenta como letra
        "D10 STORE",
        "CINEMATOGRAFIA ANDINA",  # CINE no encaja dentro de otra palabra
        "TIENDA DE BARRIO EJEMPLO",  # sin palabra clave → LLM
        "PERSONA EJEMPLO",
        "FERRETERIA EJEMPLO SAS",  # sin categoría de hogar: la decide el LLM
        "",
    ],
)
def test_no_rule(merchant):
    assert rule_category(merchant) is None


def test_two_categories_is_no_rule():
    """Como con las plantillas: si encaja en más de una categoría no se adivina."""
    assert rule_category("DROGUERIA Y SUPERMERCADO LA 14") is None


def test_merchant_key_normalizes_case_accents_and_spaces():
    assert merchant_key("  Panadería   El  Trigo ") == "PANADERIA EL TRIGO"
    assert merchant_key("x" * 300) == "X" * 200  # el check de la tabla admite hasta 200


def test_rules_file_is_consistent():
    data = tomllib.loads(
        (categorize.Path(categorize.__file__).parent / "rules.toml").read_text(
            encoding="utf-8"
        )
    )
    assert set(data) <= GLOBALS  # solo categorías globales sembradas en la BD
    assert (
        categorize.INCOME not in data
    )  # Ingresos va por dirección, nunca por comercio
    for name, words in data.items():
        for word in words:
            # cada palabra clave, sola, lleva a su categoría y a ninguna otra
            assert rule_category(word) == name, word


# ---------------------------------------------------------------- respuesta del LLM
NAMES = ["Alimentos", "Otros", "Transporte"]


def fake_generate(monkeypatch, answer: str, seen: list | None = None):
    def generate(system, text, schema, model):
        if seen is not None:
            seen.append((text, schema))
        return answer

    monkeypatch.setattr(llm, "_generate", generate)


def test_llm_picks_from_the_user_categories(monkeypatch):
    seen = []
    fake_generate(monkeypatch, json.dumps({"category": "Transporte"}), seen)
    assert llm.ask_category("APP DE TRANSPORTE FICTICIA", NAMES) == "Transporte"
    text, schema = seen[0]
    assert schema["properties"]["category"]["enum"] == NAMES
    assert "APP DE TRANSPORTE FICTICIA" in text  # solo el comercio, no el correo


@pytest.mark.parametrize(
    "answer",
    [
        '{"category": "Mascotas"}',  # inventada
        '{"category": "Transporte", "confianza": 0.9}',
        '["Transporte"]',
        "no sé",
        '{"category": null}',
    ],
)
def test_llm_invalid_answer_is_none(monkeypatch, answer):
    fake_generate(monkeypatch, answer)
    assert llm.ask_category("X", NAMES) is None


def test_schedule_runs_in_background_only_with_llm(monkeypatch):
    real = REAL_SCHEDULE
    done, asks = threading.Event(), []
    monkeypatch.setattr(
        categorize,
        "run_pending",
        lambda user_id, ask=False: asks.append(ask) or done.set(),
    )

    real("u")
    assert not done.wait(0.2)  # sin LLM configurado no se lanza nada

    monkeypatch.setattr(settings, "ollama_url", "http://ollama.test")
    real("u")
    assert done.wait(2)
    assert asks == [
        True
    ]  # en la ingesta en vivo sí se pregunta la categoría si no se sabe
