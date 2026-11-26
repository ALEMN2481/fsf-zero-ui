"""Categorización de movimientos (Paso 10, D11).

Orden, en línea y sin LLM (no retrasa el aviso):
1. Ingreso → Ingresos, salvo las devoluciones, que se categorizan por el comercio como un gasto.
2. Regla propia del usuario (aprendida de sus correcciones).
3. Reglas globales de rules.toml, si el comercio encaja en una sola categoría.
4. Si no: Otros con category_source='pendiente'. El LLM local lo revisa después en segundo
   plano y solo escribe si sigue en 'pendiente': nunca pisa una corrección del usuario.
"""

import logging
import re
import threading
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app import push, service_db
from app.config import settings
from app.extract import llm
from app.extract.bancolombia import _FOLD

log = logging.getLogger("fsf.categorize")

INCOME = "Ingresos"
OTHER = "Otros"


def merchant_key(merchant: str) -> str:
    """Comercio normalizado: mayúsculas, sin tildes, espacios unificados.

    shortcut: las reglas aprendidas comparan el comercio exacto ('EXITO CALLE 80' ≠ 'EXITO LAURELES');
    si las correcciones se repiten por sucursal, comparar por prefijo o por palabras.
    """
    return " ".join(merchant.translate(_FOLD).upper().split())[:200]


def _load_rules() -> dict[str, re.Pattern]:
    data = tomllib.loads(
        (Path(__file__).parent / "rules.toml").read_text(encoding="utf-8")
    )
    # Palabra completa: \w incluye Ñ y dígitos ("ARA" no encaja en "ARAÑA" ni en "ARA2").
    return {
        name: re.compile(
            r"(?<!\w)(?:"
            + "|".join(re.escape(merchant_key(k)) for k in words)
            + r")(?!\w)"
        )
        for name, words in data.items()
    }


RULES = _load_rules()


def rule_category(merchant: str) -> str | None:
    """Categoría global si el comercio encaja en exactamente una; si no, None."""
    key = merchant_key(merchant)
    found = [name for name, pattern in RULES.items() if pattern.search(key)]
    return found[0] if len(found) == 1 else None


# ---------------------------------------------------------------- BD (service_role, D4)
def _get(table: str, params: dict) -> list[dict]:
    return service_db.rest("GET", table, params=params).json()


def _global_id(name: str) -> str:
    [row] = _get(
        "categories", {"name": f"eq.{name}", "user_id": "is.null", "select": "id"}
    )
    return row["id"]


def assign(
    user_id: str, merchant: str | None, direction: str, template: str | None = None
) -> dict:
    """Categoría en línea de un movimiento nuevo → {'category_id', 'category_source'}."""

    def result(category_id: str, source: str) -> dict:
        return {"category_id": category_id, "category_source": source}

    if direction == "income" and template != "devolucion":
        return result(_global_id(INCOME), "direccion")
    if not merchant or not merchant.strip():
        return result(_global_id(OTHER), "otros")  # retiros, transferencias sin nombre
    own = _get(
        "category_rules",
        {
            "user_id": f"eq.{user_id}",
            "merchant_key": f"eq.{merchant_key(merchant)}",
            "select": "category_id",
        },
    )
    if own:
        return result(own[0]["category_id"], "regla_usuario")
    name = rule_category(merchant)
    return result(_global_id(name or OTHER), "regla" if name else "pendiente")


def run_pending(user_id: str, ask: bool = False) -> int:
    """Pasa por el LLM los movimientos del usuario en 'pendiente'. Devuelve cuántos actualizó.

    [ask]: si el LLM tampoco la sabe (queda en Otros por descarte), se le pregunta al usuario con
    un aviso, una vez por movimiento. Solo en la ingesta en vivo, nunca en el backfill.
    """
    if not settings.ollama_url:
        return 0
    rows = _get(
        "transactions",
        {
            "user_id": f"eq.{user_id}",
            "category_source": "eq.pendiente",
            "select": "id,merchant,direction,status",
        },
    )
    if not rows:
        return 0
    # Globales y propias; con el mismo nombre, gana la propia (va después).
    cats = {
        c["name"]: c["id"]
        for c in _get(
            "categories",
            {
                "or": f"(user_id.is.null,user_id.eq.{user_id})",
                "select": "id,name",
                "order": "user_id.nullsfirst",
            },
        )
    }
    names = sorted(n for n in cats if n != INCOME)
    updated = 0
    for row in rows:
        try:
            name = llm.ask_category(row["merchant"] or "", names)
        except (httpx.HTTPError, KeyError, ValueError) as e:
            # Siguen en Otros como 'pendiente': se reintentan en la próxima ejecución.
            log.warning("llm de categorías no disponible error=%s", type(e).__name__)
            break
        if name == OTHER:
            name = None  # elegir «Otros» tampoco es saberla: queda en Otros por descarte
        # Condición en la misma escritura: si el usuario corrigió mientras el LLM pensaba, no se toca.
        r = service_db.rest(
            "PATCH",
            "transactions",
            params={"id": f"eq.{row['id']}", "category_source": "eq.pendiente"},
            json={
                "category_id": cats[name or OTHER],
                "category_source": "llm" if name else "otros",
            },
            prefer="return=representation",
        )
        updated += len(r.json())
        if ask and name is None and r.json():
            _ask(user_id, row)
    log.info("categorías por llm user=%s actualizados=%d", user_id, updated)
    return updated


def _run_quietly(user_id: str, ask: bool = False) -> None:
    try:
        run_pending(user_id, ask)
    except Exception as e:  # noqa: BLE001 - hilo de fondo: un fallo solo deja el movimiento en 'pendiente'
        log.error(
            "falló la categorización con llm user=%s error=%s",
            user_id,
            type(e).__name__,
        )


def _ask(user_id: str, row: dict) -> None:
    """Pregunta la categoría de un gasto confirmado; se reclama con category_asked_at."""
    if row["direction"] != "expense" or row["status"] != "confirmed":
        return
    claimed = service_db.rest(
        "PATCH",
        "transactions",
        params={
            "id": f"eq.{row['id']}",
            "category_asked_at": "is.null",
            "category_source": "eq.otros",
            "select": "id",
        },
        json={"category_asked_at": datetime.now(UTC).isoformat()},
        prefer="return=representation",
    ).json()
    if claimed:
        push.ask_category(user_id, row["id"])


def schedule(user_id: str) -> None:
    """Lanza run_pending en segundo plano: el aviso al usuario no espera al LLM.

    shortcut: un hilo por correo y nada persistente; si el proceso se reinicia, lo que quede en
    'pendiente' lo recoge el backfill. Con varias instancias, una cola de trabajos (Paso 16).
    """
    if settings.ollama_url:
        threading.Thread(target=_run_quietly, args=(user_id, True), daemon=True).start()


def backfill() -> dict[str, int]:
    """Categoriza los movimientos sin categoría y pasa por el LLM todos los 'pendiente'.

    Los movimientos de antes del Paso 10 no guardan su plantilla: una devolución antigua no se
    distingue de otro ingreso y queda en Ingresos (el usuario puede corregirla).
    """
    counts: dict[str, int] = {}
    while rows := _get(
        "transactions",
        {
            "category_id": "is.null",
            "select": "id,user_id,merchant,direction",
            "limit": 500,
        },
    ):
        for row in rows:
            change = assign(row["user_id"], row["merchant"], row["direction"])
            service_db.rest(
                "PATCH",
                "transactions",
                params={"id": f"eq.{row['id']}", "category_id": "is.null"},
                json=change,
            )
            source = change["category_source"]
            counts[source] = counts.get(source, 0) + 1
    users = {
        r["user_id"]
        for r in _get(
            "transactions", {"category_source": "eq.pendiente", "select": "user_id"}
        )
    }
    counts["por_llm"] = sum(run_pending(u) for u in sorted(users))
    return counts
