import uuid

import pytest
from local_supabase import ANON, PASSWORD, URL, admin, sign_in

from app import auth
from app.config import settings


@pytest.fixture
def users(monkeypatch):
    """Dos usuarios confirmados (a y b) en el Supabase local; se borran al terminar."""
    monkeypatch.setattr(settings, "supabase_url", URL)
    monkeypatch.setattr(settings, "supabase_anon_key", ANON)
    monkeypatch.setattr(auth, "_jwks", None)
    created = {}
    for name in ("a", "b"):
        email = f"fsf-{name}-{uuid.uuid4().hex[:8]}@test.local"
        r = admin(
            "POST",
            "users",
            json={"email": email, "password": PASSWORD, "email_confirm": True},
        )
        assert r.status_code == 200, r.text
        token = sign_in(email).json()["access_token"]
        created[name] = {"id": r.json()["id"], "email": email, "token": token}
    yield created
    for u in created.values():
        admin("DELETE", f"users/{u['id']}")
