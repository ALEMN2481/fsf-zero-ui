"""Compara modelos de Ollama para el respaldo del Paso 09C (no corre en la CI: necesita Ollama).

    cd backend && .venv/Scripts/python.exe -m scripts.eval_llm [modelo ...]

Por cada modelo, con y sin ejemplos en el prompt: latencia de la primera llamada con todos los
modelos descargados de memoria (en frío) y mediana en caliente; precisión por campo sobre las
alertas que deben dar movimiento; montos aceptados erróneamente (debe ser 0).
"""

import json
import statistics
import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import httpx

from app.config import settings
from app.extract import llm

CASES = json.loads(
    (
        Path(__file__).parent.parent
        / "tests"
        / "samples"
        / "llm"
        / "fuera_de_plantilla.json"
    ).read_text(encoding="utf-8")
)["casos"]
FIELDS = ("direction", "amount", "merchant", "occurred_at", "payment_method", "last4")


def unload_all() -> None:
    for m in httpx.get(f"{settings.ollama_url}/api/ps").json()["models"]:
        httpx.post(
            f"{settings.ollama_url}/api/generate",
            json={"model": m["name"], "keep_alive": 0},
        )
    while httpx.get(f"{settings.ollama_url}/api/ps").json()["models"]:
        time.sleep(0.5)


def timed(text: str, model: str, examples: bool) -> tuple[float, str]:
    t = time.perf_counter()
    raw = llm.ask(text, model=model, examples=examples)
    return time.perf_counter() - t, raw


def correct(field: str, exp: dict, got) -> bool:
    if field == "amount":
        return got.amount == Decimal(exp["amount"])
    if field == "occurred_at":
        want = datetime.strptime(
            f"{exp['date']} {exp['time'] or '00:00'}", "%d/%m/%Y %H:%M"
        )
        return got.occurred_at.replace(tzinfo=None) == want
    return getattr(got, field) == exp[field]


def evaluate(model: str, examples: bool) -> dict:
    unload_all()
    cold, _ = timed(CASES[0]["texto"], model, examples)
    hits = dict.fromkeys(FIELDS, 0)
    raw_hits = dict.fromkeys(("direction", "payment_method"), 0)
    warm, accepted, wrong_amounts, rejected_ok, reasons = [], 0, [], 0, {}
    for case in CASES:
        seconds, raw = timed(case["texto"], model, examples)
        warm.append(seconds)
        got = llm.check(case["texto"], raw, datetime.fromisoformat(case["recibido"]))
        exp = case["esperado"]
        if got.status != "pending_review":
            reasons[got.reason] = reasons.get(got.reason, 0) + 1
            rejected_ok += exp is None
            if (
                exp is not None
            ):  # lo que dijo el LLM antes de las comprobaciones, para ver qué atrapan
                try:
                    data = json.loads(raw)
                    for f in raw_hits:
                        raw_hits[f] += data.get(f) == exp[f]
                except ValueError:
                    pass
            continue
        accepted += 1
        if exp is None or got.amount != Decimal(exp["amount"]):
            wrong_amounts.append(case["id"])
            continue
        for f in FIELDS:
            hits[f] += correct(f, exp, got)
        for f in raw_hits:
            raw_hits[f] += getattr(got, f) == exp[f]
    n = sum(c["esperado"] is not None for c in CASES)
    return {
        "model": model,
        "examples": examples,
        "cold": cold,
        "warm_median": statistics.median(warm),
        "warm_max": max(warm),
        "accepted": accepted,
        "movements": n,
        "rejected_ok": rejected_ok,
        "must_reject": len(CASES) - n,
        "wrong_amounts": wrong_amounts,
        "hits": hits,
        "raw_hits": raw_hits,
        "reasons": reasons,
        "score": sum(hits.values()),
    }


def main(models: list[str]) -> None:
    results = [evaluate(m, ex) for m in models for ex in (False, True)]
    for r in results:
        n = r["movements"]
        print(
            f"\n== {r['model']} · {'con' if r['examples'] else 'sin'} ejemplos · keep_alive={settings.ollama_keep_alive}"
        )
        print(
            f"latencia: fría {r['cold']:.2f} s · caliente mediana {r['warm_median']:.2f} s (máx {r['warm_max']:.2f} s)"
        )
        print(
            f"aceptadas por las comprobaciones: {r['accepted']}/{n} · rechazos correctos: {r['rejected_ok']}/{r['must_reject']}"
        )
        print(
            f"MONTOS ACEPTADOS ERRÓNEAMENTE: {len(r['wrong_amounts'])} {r['wrong_amounts'] or ''}"
        )
        print("precisión por campo (sobre las", n, "alertas con movimiento):")
        for f, ok in r["hits"].items():
            print(f"  {f:<15} {ok}/{n} ({100 * ok / n:.0f} %)")
        print(
            "  sin comprobaciones (salida cruda): "
            + ", ".join(f"{f} {ok}/{n}" for f, ok in r["raw_hits"].items())
        )
        print(f"rechazos por motivo: {r['reasons']}")
    safe = [r for r in results if not r["wrong_amounts"]]
    best = max(safe, key=lambda r: (r["score"], -r["warm_median"])) if safe else None
    print(
        "\nGANADOR:",
        best and f"{best['model']} {'con' if best['examples'] else 'sin'} ejemplos",
    )


if __name__ == "__main__":
    main(sys.argv[1:] or ["llama3.2:3b", "qwen2.5:3b"])
