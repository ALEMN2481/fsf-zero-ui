"""Ayudantes para pruebas de integración contra Supabase LOCAL (`supabase status -o env`).

Nunca contra la nube: crear usuarios allí requiere confirmación del supervisor.
"""

import os

import httpx
import pytest

URL = os.getenv("SUPABASE_URL", "")
ANON = os.getenv("SUPABASE_ANON_KEY", "")
SERVICE = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
PASSWORD = "clave-de-prueba-1"
# GoTrue con bcrypt va lento si la máquina está cargada (emulador, Gradle): 10 s se quedó corto.
TIMEOUT = 30

LOCAL_READY = bool(ANON and SERVICE and ("127.0.0.1" in URL or "localhost" in URL))
# En la tarea db de la CI se exige el stack local: saltarse sería un falso verde.
if os.getenv("REQUIRE_SUPABASE") and not LOCAL_READY:
    raise RuntimeError("REQUIRE_SUPABASE=1 pero no hay Supabase local configurado")

requires_local = pytest.mark.skipif(
    not LOCAL_READY, reason="requiere Supabase local (supabase start)"
)


def admin(method, path, **kw):
    h = {"apikey": SERVICE, "Authorization": f"Bearer {SERVICE}"}
    return httpx.request(
        method, f"{URL}/auth/v1/admin/{path}", headers=h, timeout=TIMEOUT, **kw
    )


def sign_in(email, password=PASSWORD):
    return httpx.post(
        f"{URL}/auth/v1/token?grant_type=password",
        headers={"apikey": ANON},
        json={"email": email, "password": password},
        timeout=TIMEOUT,
    )


def sign_up(email, password):
    return httpx.post(
        f"{URL}/auth/v1/signup",
        headers={"apikey": ANON},
        json={"email": email, "password": password},
        timeout=TIMEOUT,
    )


def bearer(token):
    return {"Authorization": f"Bearer {token}"}
