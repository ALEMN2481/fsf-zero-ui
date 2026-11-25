"""Paso 10, integración contra Supabase LOCAL: toda transacción con categoría, correcciones,
reglas aprendidas, LLM en diferido (sin pisar al usuario) y backfill."""

import uuid
from datetime import UTC, datetime

import httpx
import pytest
import test_extract_store
from fastapi.testclient import TestClient
from local_supabase import bearer, requires_local
from test_extract_store import ALERTS, alert_email, invoice_email, svc

from app import categorize
from app.config import settings
from app.extract import llm
from app.ingest.store import ingest
from app.main import app

pytestmark = requires_local
env = test_extract_store.env  # fixture compartida: usuario con Gmail y cuenta *1111
client = TestClient(app)


def categories() -> dict[str, str]:
    rows = svc("GET", "categories", params={"user_id": "is.null", "select": "id,name"})
    return {r["name"]: r["id"] for r in rows}


def rows(user_id: str) -> list[dict]:
    return svc(
        "GET",
        "transactions",
        params={
            "user_id": f"eq.{user_id}",
            "select": "id,merchant,direction,category_source,category:categories(name)",
            "order": "created_at",
        },
    )


def by_merchant(user_id: str) -> dict:
    return {
        r["merchant"]: (r["category"]["name"], r["category_source"])
        for r in rows(user_id)
    }


def fake_llm(monkeypatch, answer):
    monkeypatch.setattr(settings, "ollama_url", "http://ollama.test")
    monkeypatch.setattr(
        llm, "ask_category", answer if callable(answer) else lambda m, names: answer
    )


def test_every_supervisor_movement_ends_with_a_category(env, monkeypatch):
    user_id, _ = env
    for key in [f"A{i:02}" for i in range(1, 17)]:
        assert ingest(user_id, alert_email(key)) == "stored"
    for key in [f"F{i:02}" for i in range(1, 7)]:
        assert ingest(user_id, invoice_email(key)) == "stored"

    got = rows(user_id)
    assert got and all(r["category"] for r in got)  # ninguna sin categoría
    m = by_merchant(user_id)
    assert m["PANADERIA EJEMPLO"] == ("Alimentos", "regla")
    assert m["DROGUERIA EJEMPLO"] == ("Salud", "regla")
    assert m["EMPRESA DE ENERGIA EJEMPLO"] == ("Servicios", "regla")
    assert m["CAJERO EJEMPLO CENTRO"] == ("Otros", "regla")
    assert m["EMPRESA EMPLEADORA EJEMPLO SAS"] == ("Ingresos", "direccion")  # nómina
    assert m["PERSONA EJEMPLO"] == ("Ingresos", "direccion")  # transferencia recibida
    assert m[None] == ("Otros", "otros")  # transferencia enviada sin nombre
    assert m["RESTAURANTE EJEMPLO SAS"] == (
        "Alimentos",
        "regla",
    )  # F02, factura en efectivo
    assert m["CAFE EJEMPLO SAS"] == ("Alimentos", "regla")  # F06
    # Sin palabra clave: Otros mientras espera al LLM (F03 aunque esté en revisión)
    assert m["TIENDA DE BARRIO EJEMPLO"] == ("Otros", "pendiente")
    assert m["FERRETERIA EJEMPLO SAS"] == ("Otros", "pendiente")
    # A13: la devolución se categoriza por el comercio, como un gasto (resta en el Paso 11)
    [refund] = [
        r
        for r in got
        if r["direction"] == "income" and "SUPERMERCADO" in (r["merchant"] or "")
    ]
    assert (refund["category"]["name"], refund["category_source"]) == (
        "Alimentos",
        "regla",
    )

    fake_llm(monkeypatch, "Alimentos")
    assert categorize.run_pending(user_id) == 2
    assert by_merchant(user_id)["TIENDA DE BARRIO EJEMPLO"] == ("Alimentos", "llm")
    assert not [r for r in rows(user_id) if r["category_source"] == "pendiente"]


def test_correction_learns_a_rule_only_for_that_user(env, users):
    user_id, _ = env
    a, b = users["a"], users["b"]
    assert ingest(user_id, alert_email("A16")) == "stored"
    [tx] = rows(user_id)
    assert tx["category_source"] == "pendiente"
    cats = categories()

    r = client.patch(
        f"/transactions/{tx['id']}/category",
        headers=bearer(a["token"]),
        json={"category_id": cats["Alimentos"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["category_source"] == "usuario"
    assert by_merchant(user_id)["TIENDA DE BARRIO EJEMPLO"] == ("Alimentos", "usuario")

    # Volver a corregir actualiza la misma regla (una por comercio).
    r = client.patch(
        f"/transactions/{tx['id']}/category",
        headers=bearer(a["token"]),
        json={"category_id": cats["Entretenimiento"]},
    )
    assert r.status_code == 200
    rules = svc(
        "GET", "category_rules", params={"user_id": f"eq.{user_id}", "select": "*"}
    )
    assert [(x["merchant_key"], x["category_id"]) for x in rules] == [
        ("TIENDA DE BARRIO EJEMPLO", cats["Entretenimiento"])
    ]

    # El siguiente movimiento del mismo comercio usa la regla del usuario, antes que el LLM.
    assert (
        ingest(user_id, alert_email("A16")) == "stored"
    )  # otro correo, otro Message-ID
    assert rows(user_id)[-1]["category_source"] == "regla_usuario"
    assert rows(user_id)[-1]["category"]["name"] == "Entretenimiento"
    # La corrección no recategoriza el historial ni a otros usuarios.
    assert (
        categorize.assign(b["id"], "TIENDA DE BARRIO EJEMPLO", "expense")[
            "category_source"
        ]
        == "pendiente"
    )


def test_correction_endpoint_checks_owner_and_category(env, users):
    user_id, _ = env
    a, b = users["a"], users["b"]
    assert ingest(user_id, alert_email("A01")) == "stored"
    [tx] = rows(user_id)
    url = f"/transactions/{tx['id']}/category"
    other = categories()["Otros"]

    assert client.patch(url, json={"category_id": other}).status_code == 401
    # B no ve el movimiento de A: 404, y no cambia nada.
    assert (
        client.patch(
            url, headers=bearer(b["token"]), json={"category_id": other}
        ).status_code
        == 404
    )
    # Categoría privada de B: A no puede usarla.
    private = svc(
        "POST",
        "categories",
        json={"user_id": b["id"], "name": "Privada B"},
        headers={"Prefer": "return=representation"},
    )[0]["id"]
    assert (
        client.patch(
            url, headers=bearer(a["token"]), json={"category_id": private}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            url, headers=bearer(a["token"]), json={"category_id": str(uuid.uuid4())}
        ).status_code
        == 422
    )
    assert by_merchant(user_id)["PANADERIA EJEMPLO"] == ("Alimentos", "regla")
    assert (
        svc(
            "GET",
            "category_rules",
            params={"select": "user_id", "user_id": f"in.({a['id']},{b['id']})"},
        )
        == []
    )

    listed = client.get("/categories", headers=bearer(b["token"])).json()
    assert {"Alimentos", "Ingresos", "Otros", "Privada B"} <= {
        c["name"] for c in listed
    }
    assert "Privada B" not in {
        c["name"] for c in client.get("/categories", headers=bearer(a["token"])).json()
    }


def test_llm_never_overwrites_a_user_correction(env, users, monkeypatch):
    """Carrera: el usuario corrige mientras el LLM está pensando. Gana el usuario."""
    user_id, _ = env
    assert ingest(user_id, alert_email("A16")) == "stored"
    [tx] = rows(user_id)
    salud = categories()["Salud"]

    def slow_llm(merchant, names):
        r = client.patch(
            f"/transactions/{tx['id']}/category",
            headers=bearer(users["a"]["token"]),
            json={"category_id": salud},
        )
        assert r.status_code == 200
        return "Alimentos"  # el LLM responde después de la corrección

    fake_llm(monkeypatch, slow_llm)
    assert categorize.run_pending(user_id) == 0
    assert by_merchant(user_id)["TIENDA DE BARRIO EJEMPLO"] == ("Salud", "usuario")


@pytest.mark.parametrize(
    "answer, expected",
    [
        (None, ("Otros", "otros")),  # respuesta inválida: Otros definitivo
        ("Otros", ("Otros", "llm")),  # el LLM no está seguro
    ],
)
def test_llm_unsure_or_invalid_goes_to_otros(env, monkeypatch, answer, expected):
    user_id, _ = env
    assert ingest(user_id, alert_email("A16")) == "stored"
    fake_llm(monkeypatch, answer)
    assert categorize.run_pending(user_id) == 1
    assert by_merchant(user_id)["TIENDA DE BARRIO EJEMPLO"] == expected


def test_llm_down_keeps_pending_for_a_later_retry(env, monkeypatch):
    user_id, _ = env
    assert ingest(user_id, alert_email("A16")) == "stored"

    def down(merchant, names):
        raise httpx.ConnectError("caído")

    fake_llm(monkeypatch, down)
    assert categorize.run_pending(user_id) == 0
    assert by_merchant(user_id)["TIENDA DE BARRIO EJEMPLO"] == ("Otros", "pendiente")


def test_backfill_categorizes_old_movements(env, monkeypatch):
    user_id, _ = env
    now = datetime.now(UTC).isoformat()
    for merchant, direction in [
        ("FARMACIA FICTICIA", "expense"),
        ("ZAPATERIA INVENTADA", "expense"),
        (None, "income"),
    ]:
        svc(
            "POST",
            "transactions",
            json={
                "user_id": user_id,
                "direction": direction,
                "amount": "1000.00",
                "merchant": merchant,
                "occurred_at": now,
                "source": "manual",
            },
        )
    fake_llm(monkeypatch, "Otros")
    counts = categorize.backfill()
    assert counts["por_llm"] >= 1
    m = by_merchant(user_id)
    assert m["FARMACIA FICTICIA"] == ("Salud", "regla")
    assert m["ZAPATERIA INVENTADA"] == ("Otros", "llm")
    assert m[None] == ("Ingresos", "direccion")
    assert (
        svc("GET", "transactions", params={"category_id": "is.null", "select": "id"})
        == []
    )


@pytest.mark.parametrize("corrected", [False, True])
def test_invoice_completion_recategorizes_unless_user_corrected(
    env, users, monkeypatch, corrected
):
    """La factura cambia el comercio del movimiento del banco: nueva categoría, salvo corrección."""
    user_id, _ = env
    text = ALERTS["A02"].replace("SUPERMERCADO EJEMPLO SAS", "PAGOS INVENTADOS")
    assert ingest(user_id, alert_email("", text)) == "stored"
    [tx] = rows(user_id)
    assert tx["category_source"] == "pendiente"
    if corrected:
        r = client.patch(
            f"/transactions/{tx['id']}/category",
            headers=bearer(users["a"]["token"]),
            json={"category_id": categories()["Entretenimiento"]},
        )
        assert r.status_code == 200

    assert (
        ingest(user_id, invoice_email("F01")) == "stored"
    )  # completa: mismo monto y día
    [tx] = rows(user_id)
    assert tx["merchant"] == "SUPERMERCADO EJEMPLO SAS"
    expected = ("Entretenimiento", "usuario") if corrected else ("Alimentos", "regla")
    assert (tx["category"]["name"], tx["category_source"]) == expected
