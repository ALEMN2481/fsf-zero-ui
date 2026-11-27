"""Paso 15 (D17): los datos de la expo se regeneran iguales y no tocan lo que debe quedarse."""

from datetime import date

from fastapi.testclient import TestClient
from local_supabase import bearer, requires_local
from test_extract_store import SERVICE, svc, unique_gmail

from app.config import settings
from app.main import app
from scripts import expo_seed

pytestmark = requires_local
client = TestClient(app)


def snapshot(user):
    gps = client.get("/gps", headers=bearer(user["token"])).json()
    movements = client.get("/movements", headers=bearer(user["token"])).json()
    pockets = client.get("/pockets", headers=bearer(user["token"])).json()
    return (
        gps["disponible_hoy"],
        gps["periodo"]["presupuesto"],
        sorted(
            (m["comercio"], m["monto"], m["categoria"], m["estado"]) for m in movements
        ),
        pockets["total"],
    )


def test_seed_is_repeatable_and_keeps_gmail_and_device(users, monkeypatch):
    monkeypatch.setattr(settings, "supabase_service_role_key", SERVICE)
    a, b = users["a"], users["b"]
    svc(
        "POST",
        "gmail_connections",
        json={
            "user_id": a["id"],
            "gmail_address": unique_gmail(),
            "key_version": 1,
            "refresh_token_encrypted": "\\x00",
        },
    )
    svc("POST", "device_tokens", json={"token": "tok-expo", "user_id": a["id"]})
    other = svc(
        "POST",
        "budgets",
        json={"user_id": b["id"], "period_start": "2026-11-01", "period_end": "2026-11-30",
              "amount": "1.00"},
        headers={"Prefer": "return=representation"},
    )  # fmt: skip
    today = date.today()

    assert expo_seed.seed(a["id"], today) == {
        "presupuestos": 1,
        "bolsillos": 2,
        "movimientos": 9,
    }
    first = snapshot(a)
    client.post(  # la demo cambia cosas: una categoría corregida
        f"/transactions/{client.get('/movements', headers=bearer(a['token'])).json()[0]['id']}/category",
        headers=bearer(a["token"]),
        json={"category_id": svc("GET", "categories?name=eq.Salud&select=id")[0]["id"]},
    )
    expo_seed.seed(a["id"], today)
    assert snapshot(a) == first  # siempre lo mismo
    assert svc("GET", f"category_rules?user_id=eq.{a['id']}&select=merchant_key") == []
    assert (
        len(svc("GET", f"gmail_connections?user_id=eq.{a['id']}&select=user_id")) == 1
    )
    assert svc("GET", f"device_tokens?user_id=eq.{a['id']}&select=token") == [
        {"token": "tok-expo"}
    ]
    assert svc("GET", f"budgets?user_id=eq.{b['id']}&select=id") == [
        {"id": other[0]["id"]}
    ]  # otra cuenta, intacta
    assert first[0] is not None and first[1] == "2000000.00"
    # --nombre: la cabecera muestra el nombre y no el correo.
    expo_seed.seed(a["id"], today, name="  Sofía   Expo ")
    assert svc("GET", f"profiles?id=eq.{a['id']}&select=display_name") == [
        {"display_name": "Sofía Expo"}
    ]
