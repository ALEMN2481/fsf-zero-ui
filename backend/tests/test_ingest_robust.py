"""Paso 15, integración contra Supabase LOCAL: candado por usuario en la extracción y reproceso de
los correos que quedaron en pending_extraction."""

import threading
import time

from local_supabase import requires_local
from test_extract_store import alert_email, env, invoice_email, statuses, svc, txs

from app.extract import pipeline
from app.ingest import store
from app.ingest.store import ingest

pytestmark = requires_local
__all__ = ["env"]  # fixture compartida


def test_alert_and_invoice_at_the_same_time_are_one_movement(env, monkeypatch):
    user_id, _ = env
    real = pipeline._txs

    def slow(*a, **kw):  # los dos buscan su pareja antes de que el otro escriba
        rows = real(*a, **kw)
        time.sleep(0.5)
        return rows

    monkeypatch.setattr(pipeline, "_txs", slow)
    results = []
    threads = [
        threading.Thread(target=lambda raw=raw: results.append(ingest(user_id, raw)))
        for raw in (alert_email("A02"), invoice_email("F01"))
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == ["stored", "stored"]
    [tx] = txs(user_id)  # sin el candado salían dos movimientos
    assert tx["status"] == "confirmed" and tx["invoice_cufe"]


def test_pending_extraction_is_reprocessed_once(env, monkeypatch):
    user_id, _ = env

    def boom(*a, **kw):
        raise RuntimeError("caído")

    with monkeypatch.context() as m:
        m.setattr(pipeline, "process", boom)
        assert ingest(user_id, alert_email("A02")) == "stored"
    assert statuses(user_id) == ["pending_extraction"] and txs(user_id) == []

    assert store.reprocess_pending(min_age_s=0, user_ids=[user_id]) == 1
    assert statuses(user_id) == ["extracted"] and len(txs(user_id)) == 1
    assert store.reprocess_pending(min_age_s=0, user_ids=[user_id]) == 0


def test_reprocess_does_not_duplicate_a_movement_already_written(env):
    user_id, _ = env
    assert ingest(user_id, alert_email("A02")) == "stored"
    # Se escribió el movimiento pero falló al marcar el correo.
    svc(
        "PATCH",
        f"inbound_emails?user_id=eq.{user_id}",
        json={"status": "pending_extraction"},
    )
    assert store.reprocess_pending(min_age_s=0, user_ids=[user_id]) == 1
    assert statuses(user_id) == ["extracted"] and len(txs(user_id)) == 1


def test_recent_pending_emails_are_left_alone(env, monkeypatch):
    user_id, _ = env
    with monkeypatch.context() as m:
        m.setattr(pipeline, "process", lambda *a, **kw: 1 / 0)
        ingest(user_id, alert_email("A02"))
    # Recién llegado: puede estar procesándose ahora mismo.
    assert store.reprocess_pending(user_ids=[user_id]) == 0
