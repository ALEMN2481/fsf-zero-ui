import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth
from app.config import settings

URL = "http://supabase.test"
KEY = ec.generate_private_key(ec.SECP256R1())
OTHER_KEY = ec.generate_private_key(ec.SECP256R1())


def jwks(*pairs):
    keys = []
    for kid, private in pairs:
        jwk = jwt.algorithms.ECAlgorithm.to_jwk(private.public_key(), as_dict=True)
        keys.append({**jwk, "kid": kid, "alg": "ES256", "use": "sig"})
    return jwt.PyJWKSet.from_dict({"keys": keys})


def make_token(key=KEY, kid="k1", alg="ES256", **overrides):
    claims = {
        "sub": "user-a",
        "aud": "authenticated",
        "iss": f"{URL}/auth/v1",
        "exp": int(time.time()) + 300,
        **overrides,
    }
    return jwt.encode(claims, key, algorithm=alg, headers={"kid": kid})


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", URL)
    monkeypatch.setattr(auth, "_jwks", None)
    monkeypatch.setattr(auth, "_loaded_at", 0.0)
    monkeypatch.setattr(auth, "_last_kid_refetch", float("-inf"))
    clock = [1000.0]  # reloj falso: los tests avanzan el tiempo sin dormir
    monkeypatch.setattr(auth, "monotonic", lambda: clock[0])
    calls = []

    def fake_fetch():
        calls.append(1)
        return fake_fetch.sets[min(len(calls), len(fake_fetch.sets)) - 1]

    fake_fetch.sets = [jwks(("k1", KEY))]
    monkeypatch.setattr(auth, "_fetch_jwks", fake_fetch)

    app = FastAPI()

    @app.get("/x")
    def x(user: auth.User):
        return {"sub": user.id}

    c = TestClient(app)
    c.fetch, c.calls, c.clock = fake_fetch, calls, clock
    return c


def get(client, token):
    return client.get("/x", headers={"Authorization": f"Bearer {token}"})


def test_valid_token(client):
    r = get(client, make_token())
    assert r.status_code == 200 and r.json() == {"sub": "user-a"}


def test_missing_token(client):
    assert client.get("/x").status_code == 401


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(lambda: make_token(key=OTHER_KEY), id="firma-invalida"),
        pytest.param(lambda: make_token(exp=int(time.time()) - 10), id="caducado"),
        pytest.param(lambda: make_token(aud="anon"), id="audiencia-incorrecta"),
        pytest.param(lambda: make_token(iss="https://otro.supabase.co/auth/v1"), id="emisor-incorrecto"),
        pytest.param(lambda: make_token(key="secreto-compartido-de-32-bytes!!", alg="HS256"), id="alg-HS256"),
        pytest.param(lambda: make_token(key=None, alg="none"), id="alg-none"),
        pytest.param(lambda: "no-es-un-jwt", id="malformado"),
    ],
)
def test_rejected_tokens(client, token):
    assert get(client, token()).status_code == 401


def test_disallowed_alg_does_not_fetch_jwks(client):
    get(client, make_token(key="secreto-compartido-de-32-bytes!!", alg="HS256"))
    assert client.calls == []


def test_unknown_kid_refetches_once_and_accepts_rotated_key(client):
    client.fetch.sets = [jwks(("k1", KEY)), jwks(("k1", KEY), ("k2", OTHER_KEY))]
    assert get(client, make_token()).status_code == 200  # carga inicial
    assert get(client, make_token(key=OTHER_KEY, kid="k2")).status_code == 200
    assert len(client.calls) == 2


def test_unknown_kid_refetches_only_once(client):
    assert get(client, make_token(kid="desconocido")).status_code == 401
    assert len(client.calls) == 2  # carga inicial + una recarga, sin bucle


def test_many_unknown_kids_trigger_a_single_refetch(client):
    assert get(client, make_token()).status_code == 200  # carga inicial
    for i in range(20):
        assert get(client, make_token(kid=f"inventado-{i}")).status_code == 401
    assert len(client.calls) == 2  # carga inicial + una sola recarga por kid
    client.clock[0] += 61  # pasado el intervalo, se permite otra recarga
    get(client, make_token(kid="inventado-otra-vez"))
    assert len(client.calls) == 3


def test_cached_keys_expire_after_ttl(client):
    assert get(client, make_token()).status_code == 200
    client.clock[0] += 599
    assert get(client, make_token()).status_code == 200
    assert len(client.calls) == 1  # dentro de los 10 min, usa la caché
    client.clock[0] += 2
    assert get(client, make_token()).status_code == 200
    assert len(client.calls) == 2  # caducada: vuelve a descargar
