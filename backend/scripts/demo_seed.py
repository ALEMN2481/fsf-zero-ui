"""Datos de demostración en el Supabase LOCAL para probar la app a mano (Paso 12).

    cd backend && .venv/Scripts/python.exe -m scripts.demo_seed
    cd backend && .venv/Scripts/python.exe -m scripts.demo_seed --overspend <id del usuario demo>

Crea dos usuarios confirmados (nunca en la nube):
- demo-<sufijo>@test.local: conjunto del supervisor (alertas y facturas simuladas), presupuesto del
  mes, cuenta *1111, Gmail de prueba y un bolsillo «Viaje».
- vacio-<sufijo>@test.local: sin presupuesto ni movimientos (estado vacío).
--overspend añade a ese usuario una compra de hoy que supera su diario (efecto GPS).
Necesita SUPABASE_URL, SUPABASE_ANON_KEY y SUPABASE_SERVICE_ROLE_KEY del stack local.
Mientras exista el usuario demo, los tests de integración que conectan el mismo Gmail de prueba
fallan por clave duplicada (gmail_connections.gmail_address es única): bórralo al terminar.
"""

import base64
import os
import re
import sys
import uuid
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.engine.gps import month_bounds
from app.extract.bancolombia import COLOMBIA
from app.ingest.store import ingest

PASSWORD = "clave-demo-1234"
SAMPLES = Path(__file__).parent.parent / "tests" / "samples" / "supervisor"
GMAIL = "cliente.ejemplo@gmail.com"  # comprador de las facturas simuladas


def _service(method: str, path: str, **kw) -> httpx.Response:
    key = settings.supabase_service_role_key
    r = httpx.request(
        method,
        f"{settings.supabase_url}{path}",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            **kw.pop("headers", {}),
        },
        timeout=30,
        **kw,
    )
    r.raise_for_status()
    return r


def _rest(method: str, table: str, json) -> list:
    return _service(
        method,
        f"/rest/v1/{table}",
        json=json,
        headers={"Prefer": "return=representation"},
    ).json()


def _user(email: str) -> str:
    r = _service(
        "POST",
        "/auth/v1/admin/users",
        json={"email": email, "password": PASSWORD, "email_confirm": True},
    )
    return r.json()["id"]


def _alert(text: str) -> bytes:
    msg = EmailMessage()
    msg["Authentication-Results"] = (
        "mx.google.com; dkim=pass header.d=notificacionesbancolombia.com header.s=s1"
    )
    msg["From"] = (
        "Alertas y Notificaciones <alertasynotificaciones@notificacionesbancolombia.com>"
    )
    msg["Subject"] = "Alertas y Notificaciones"
    msg["Message-ID"] = f"<{uuid.uuid4()}@notificacionesbancolombia.com>"
    msg.set_content(text)
    return msg.as_bytes()


def _invoice(path: Path) -> bytes:
    msg = EmailMessage()
    msg["Authentication-Results"] = "mx.google.com; dkim=pass header.d=comercio.example"
    msg["From"] = "Facturación <facturas@comercio.example>"
    msg["Subject"] = "900000001;COMERCIO EJEMPLO SAS;FE-1;01;COMERCIO EJEMPLO"
    msg["Message-ID"] = f"<{uuid.uuid4()}@comercio.example>"
    msg.set_content("Adjuntamos su factura electrónica.")
    msg.add_attachment(path.read_bytes(), "application", "zip", filename=path.name)
    return msg.as_bytes()


def main(argv: list[str]) -> None:
    if urlparse(settings.supabase_url).hostname not in ("127.0.0.1", "localhost"):
        sys.exit(
            "Solo contra el Supabase local: crear usuarios en la nube requiere confirmación"
        )
    settings.ollama_url = (
        ""  # determinista: lo que no tiene regla queda en Otros 'pendiente'
    )
    settings.email_keys = f"1:{base64.b64encode(os.urandom(32)).decode()}"
    now = datetime.now(COLOMBIA)
    if argv[:1] == ["--overspend"]:
        when = now.strftime("el %d/%m/%Y a las %H:%M")
        text = (
            f"Bancolombia: Compraste $380.000,00 en TIENDA DE TECNOLOGIA EJEMPLO con tu T.Deb "
            f"*0000, {when}. Si tienes dudas, encuentranos aqui: 000 000 0000. Estamos cerca."
        )
        print(ingest(argv[1], _alert(text)))
        return
    suffix = uuid.uuid4().hex[:6]

    demo = _user(f"demo-{suffix}@test.local")
    _rest("POST", "gmail_connections", {"user_id": demo, "gmail_address": GMAIL,
          "key_version": 1, "refresh_token_encrypted": "\\x00"})  # fmt: skip
    _rest(
        "POST",
        "accounts",
        {"user_id": demo, "name": "Crédito", "kind": "credit", "last4": "1111"},
    )
    alerts = re.findall(
        r"\[A\d+\]\nAsunto:[^\n]*\n(.*?)(?=\n-----|\Z)",
        (SAMPLES / "alertas.txt").read_text(encoding="utf-8"),
        re.DOTALL,
    )
    for text in alerts:
        ingest(demo, _alert(text))
    for path in sorted(SAMPLES.glob("F*.zip")):
        ingest(demo, _invoice(path))
    first, last = month_bounds(now.date())
    _rest("POST", "budgets", {"user_id": demo, "period_start": str(first),
          "period_end": str(last), "amount": "3000000.00"})  # fmt: skip
    [pocket] = _rest(
        "POST",
        "pockets",
        {"user_id": demo, "name": "Viaje", "target_amount": "1000000.00"},
    )
    _rest(
        "POST",
        "pocket_movements",
        {"user_id": demo, "pocket_id": pocket["id"], "amount": "350000.00"},
    )

    _user(f"vacio-{suffix}@test.local")
    print(
        f"demo-{suffix}@test.local (id {demo}) · vacio-{suffix}@test.local · contraseña {PASSWORD}"
    )


if __name__ == "__main__":
    main(sys.argv[1:])
