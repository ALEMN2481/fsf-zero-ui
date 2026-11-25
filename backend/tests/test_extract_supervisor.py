"""Paso 09B: precisión por campo contra el conjunto independiente del supervisor (samples/supervisor).

Rompe la CI una sola condición: ningún movimiento confirmado con un monto equivocado (o que no
debía confirmarse). El resto se reporta (pytest lo muestra siempre, también en la CI).
"""

import json
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.extract.bancolombia import parse_alert
from app.extract.invoice import check_invoice
from app.extract.pipeline import alert_action, invoice_action

DIR = Path(__file__).parent / "samples" / "supervisor"
EXPECTED = json.loads((DIR / "esperado.json").read_text(encoding="utf-8"))
GMAIL = "cliente.ejemplo@gmail.com"
ALERT_FIELDS = (
    "direction",
    "amount",
    "merchant",
    "occurred_at",
    "payment_method",
    "last4",
)
INVOICE_FIELDS = ("total", "payment_method", "supplier_nit")


def load_alerts() -> dict[str, str]:
    text = (DIR / "alertas.txt").read_text(encoding="utf-8")
    found = re.findall(
        r"\[(A\d+)\]\nAsunto:[^\n]*\n(.*?)(?=\n-----|\Z)", text, re.DOTALL
    )
    return dict(found)


def predict():
    """Procesa como el backend: primero todas las alertas, luego las facturas."""
    alerts = {k: parse_alert(body) for k, body in load_alerts().items()}
    # Gastos del banco ya registrados, aún sin factura (lo que vería _txs en la BD).
    bank = [
        {"key": k, "amount": a.amount, "occurred_at": a.occurred_at}
        for k, a in alerts.items()
        if a.status == "confirmed" and a.direction == "expense"
    ]
    invoices = {}
    for path in sorted(DIR.glob("F*.zip")):
        key = path.name[:3]
        check = check_invoice(path.read_bytes(), GMAIL)
        action, tx = (None, None)
        status = check.status
        if status == "confirmed":
            action, tx = invoice_action(check.invoice, bank)
            if tx is not None:
                bank.remove(tx)  # ya tiene factura
            status = "confirmed" if action in ("complete", "new") else "pending_review"
        invoices[key] = (status, action, tx and tx["key"], check.invoice)
    return alerts, invoices


def same(field, expected, got) -> bool:
    if field in ("amount", "total"):
        return got is not None and Decimal(expected) == got
    if field == "occurred_at":
        return got is not None and datetime.fromisoformat(expected) == got
    return expected == got


def test_supervisor_set_field_precision(capsys):
    alerts, invoices = predict()
    rows, violations, status_ok, total = [], [], 0, 0
    hits = {f: [0, 0] for f in ALERT_FIELDS + INVOICE_FIELDS}

    for key, exp in EXPECTED["alertas"].items():
        got = alerts[key]
        total += 1
        status_ok += got.status == exp["status"]
        if got.status == "confirmed" and (
            exp["status"] != "confirmed"
            or not same("amount", exp["amount"], got.amount)
        ):
            violations.append(key)
        if exp["status"] == "confirmed":
            for f in ALERT_FIELDS:
                hits[f][1] += 1
                hits[f][0] += same(f, exp[f], getattr(got, f))
        rows.append(
            f"{key} esperado={exp['status']:<14} obtenido={got.status:<14} {got.template or got.reason}"
        )

    for key, exp in EXPECTED["facturas"].items():
        status, action, completed, inv = invoices[key]
        total += 1
        status_ok += status == exp["status"]
        if status == "confirmed" and (
            exp["status"] != "confirmed" or not same("total", exp["total"], inv.total)
        ):
            violations.append(key)
        for f in INVOICE_FIELDS:
            if f in exp and inv is not None:
                hits[f][1] += 1
                hits[f][0] += same(f, exp[f], getattr(inv, f))
        rows.append(
            f"{key} esperado={exp['status']:<14} obtenido={status:<14} {action or ''} {completed or ''}"
        )

    report = ["", "== Precisión contra samples/supervisor/esperado.json ==", *rows, ""]
    report.append(f"estado: {status_ok}/{total}")
    for f, (ok, n) in hits.items():
        report.append(f"{f:<15} {ok}/{n} ({100 * ok / n:.0f} %)")
    report.append(
        f"confirmados con monto equivocado: {len(violations)} {violations or ''}"
    )
    with capsys.disabled():
        print("\n".join(report))

    assert not violations, f"movimientos confirmados con monto equivocado: {violations}"


def test_invoice_f01_completes_alert_a02():
    _, invoices = predict()
    assert invoices["F01"][1:3] == ("complete", "A02")
    assert invoices["F03"][:2] == ("pending_review", "new_pending")


def test_invoice_before_alert_is_completed_when_the_alert_arrives():
    """Orden inverso: F01 llega antes que A02 → queda pendiente y la alerta la completa."""
    inv = check_invoice((DIR / "F01_ad900000001000101.zip").read_bytes(), GMAIL).invoice
    action, _ = invoice_action(inv, [])
    assert action == "new_pending"  # tarjeta de crédito sin alerta todavía
    pending = [{"key": "F01", "amount": inv.total, "occurred_at": inv.issued_at}]
    a02 = parse_alert(load_alerts()["A02"])
    assert alert_action(a02, pending) == ("complete", pending[0])


def test_several_candidates_go_to_review():
    inv = check_invoice((DIR / "F01_ad900000001000101.zip").read_bytes(), GMAIL).invoice
    twin = {"amount": inv.total, "occurred_at": inv.issued_at}
    assert invoice_action(inv, [twin, dict(twin)]) == ("review", None)
    a02 = parse_alert(load_alerts()["A02"])
    assert alert_action(a02, [twin, dict(twin)]) == ("review", None)
