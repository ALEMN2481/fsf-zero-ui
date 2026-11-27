"""Paso 15B: el nombre de la cuenta de Google queda en el perfil si no tiene uno."""

from fastapi.testclient import TestClient
from local_supabase import admin, bearer, requires_local, sign_in
from test_extract_store import svc

from app.auth import _name
from app.main import app

client = TestClient(app)


def test_name_comes_from_google_metadata():
    assert (
        _name({"user_metadata": {"full_name": "  Ana   María  Pérez "}})
        == "Ana María Pérez"
    )
    assert _name({"user_metadata": {"name": "Ana"}}) == "Ana"
    assert _name({"user_metadata": {"full_name": "", "name": "Ana"}}) == "Ana"
    assert _name({"user_metadata": {}}) is None and _name({}) is None
    assert _name({"user_metadata": {"full_name": 7}}) is None
    assert len(_name({"user_metadata": {"full_name": "x" * 200}})) == 80


def token_with(user, metadata):
    r = admin("PUT", f"users/{user['id']}", json={"user_metadata": metadata})
    assert r.status_code == 200, r.text
    return sign_in(user["email"]).json()["access_token"]


@requires_local
def test_me_saves_the_google_name_only_if_the_profile_has_none(users):
    a, b = users["a"], users["b"]
    token = token_with(a, {"full_name": "Ana Prueba Google"})
    assert (
        client.get("/me", headers=bearer(token)).json()["display_name"]
        == "Ana Prueba Google"
    )
    assert svc("GET", f"profiles?id=eq.{a['id']}&select=display_name") == [
        {"display_name": "Ana Prueba Google"}
    ]
    # Con un nombre ya puesto no se pisa.
    svc("PATCH", f"profiles?id=eq.{b['id']}", json={"display_name": "Bea"})
    token = token_with(b, {"full_name": "Beatriz Google"})
    assert client.get("/me", headers=bearer(token)).json()["display_name"] == "Bea"
