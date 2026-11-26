"""Paso 15: límite de uso del Coach (60 preguntas cada 10 min por usuario, D17). Sin BD."""

from fastapi.testclient import TestClient

from app import main
from app.auth import CurrentUser, current_user

client = TestClient(main.app)


def test_the_61st_question_waits_and_the_window_frees_up(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(main, "monotonic", lambda: clock[0])
    monkeypatch.setattr(main, "_coach_asks", main.defaultdict(main.deque))
    assert all(main._coach_allowed("u") for _ in range(main.COACH_LIMIT))
    assert not main._coach_allowed("u")
    assert main._coach_allowed("otro")  # cada usuario tiene su cuenta
    clock[0] += main.COACH_WINDOW  # pasó la ventana desde la primera
    assert main._coach_allowed("u")


def test_over_the_limit_the_endpoint_answers_429_before_touching_anything(
    monkeypatch,
):
    monkeypatch.setattr(main, "_coach_allowed", lambda user_id: False)
    main.app.dependency_overrides[current_user] = lambda: CurrentUser(
        id="u", token="jwt"
    )
    try:
        r = client.post("/coach", json={"mensaje": "¿Cuánto llevo?"})
    finally:
        main.app.dependency_overrides.clear()
    assert r.status_code == 429
    assert r.json()["detail"] == "Hiciste muchas preguntas seguidas; espera un momento"
