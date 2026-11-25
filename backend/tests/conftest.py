import uuid

import pytest
from local_supabase import ANON, PASSWORD, URL, admin, sign_in

from app import auth
from app.config import settings


@pytest.fixture(autouse=True)
def no_local_llm(monkeypatch):
    """Los tests no dependen de si Ollama está en marcha; los que lo usan lo simulan."""
    monkeypatch.setattr(settings, "ollama_url", "")


@pytest.fixture
def users(monkeypatch):
    """Dos usuarios confirmados (a y b) en el Supabase local; se borran al terminar."""
    monkeypatch.setattr(settings, "supabase_url", URL)
    monkeypatch.setattr(settings, "supabase_anon_key", ANON)
    monkeypatch.setattr(auth, "_jwks", None)
    created = {}
    try:
        for name in ("a", "b"):
            email = f"fsf-{name}-{uuid.uuid4().hex[:8]}@test.local"
            r = admin(
                "POST",
                "users",
                json={"email": email, "password": PASSWORD, "email_confirm": True},
            )
            assert r.status_code == 200, r.text
            created[name] = {"id": r.json()["id"], "email": email}
            s = sign_in(email)
            assert s.status_code == 200, f"sign_in {s.status_code}: {s.text}"
            created[name]["token"] = s.json()["access_token"]
        yield created
    finally:
        # También si la preparación falla a medias: un usuario huérfano rompe otros tests.
        for u in created.values():
            admin("DELETE", f"users/{u['id']}")
