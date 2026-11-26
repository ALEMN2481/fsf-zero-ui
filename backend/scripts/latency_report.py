"""RQN 04 (Paso 15): tabla de tramos correo → aviso a partir del log del backend y del logcat.

    cd backend && .venv/Scripts/python.exe -m scripts.latency_report <log del backend> <logcat> <desfase>

<desfase>: reloj del emulador menos reloj del PC, en ms (adb shell date +%s%3N frente al PC).
Tramos (epoch ms; los registra el backend en «tramos …» y el teléfono en «latencia correo→aviso»):
  A1 Gmail recibe el correo → Pub/Sub publica el aviso          (Google)
  A2 Pub/Sub publica → llega al backend (incluye el túnel)       (Google + Cloudflare)
  B1 llegada → movimiento guardado (API de Gmail y extracción)   (backend + API de Gmail)
  B2 guardado → FCM acepta el aviso                              (backend)
  C  FCM acepta → el teléfono lo recibe                          (Google)
El internalDate de Gmail tiene resolución de segundo: A1 y el total llevan ±1 s.
"""

import math
import re
import sys
from pathlib import Path

BACKEND = re.compile(
    r"tramos correo=(\d+) publicado=(\d+|None) llegada=(\d+|None) guardado=(\d+) fcm=(\d+) tipo=(\w+)"
)
PHONE = re.compile(r"latencia correo→aviso ms=(-?\d+) tipo=(\w+) correo=(\d+)")
STRETCHES = ["A1", "A2", "B1", "B2", "C", "total"]


def rows(backend_log: str, logcat: str, offset_ms: int) -> list[dict]:
    phone = {}
    for ms, _kind, received in PHONE.findall(logcat):
        # Hora del teléfono pasada al reloj del PC.
        phone.setdefault(int(received), int(received) + int(ms) - offset_ms)
    out = []
    for m in BACKEND.finditer(backend_log):
        received, published, arrived, saved, fcm = (
            None if v == "None" else int(v) for v in m.groups()[:5]
        )
        got = phone.get(received)
        out.append(
            {
                "tipo": m.group(6),
                "A1": published - received if published else None,
                "A2": arrived - published if published and arrived else None,
                "B1": saved - arrived if arrived else None,
                "B2": fcm - saved,
                "C": got - fcm if got else None,
                "total": got - received if got else None,
            }
        )
    return out


def percentile(values: list[int], p: float) -> int | None:
    """Rango más cercano (con 20 valores, el p95 es el 19.º)."""
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    return values[max(0, math.ceil(p / 100 * len(values)) - 1)]


def table(data: list[dict]) -> str:
    def s(ms):
        return "—" if ms is None else f"{ms / 1000:.2f}"

    lines = ["#  | tipo | " + " | ".join(STRETCHES)]
    for i, r in enumerate(data, 1):
        lines.append(
            f"{i:<2} | {r['tipo']} | " + " | ".join(s(r[k]) for k in STRETCHES)
        )
    for p in (50, 95):
        lines.append(
            f"p{p} | | "
            + " | ".join(s(percentile([r[k] for r in data], p)) for k in STRETCHES)
        )
    google = [
        r["A1"] + r["A2"] + r["C"]
        for r in data
        if None not in (r["A1"], r["A2"], r["C"])
    ]
    lines.append(
        f"solo Google (A1+A2+C): p50 {s(percentile(google, 50))} · p95 {s(percentile(google, 95))}"
    )
    within = [r["total"] for r in data if r["total"] is not None]
    lines.append(
        f"total < 10 s: {sum(t < 10_000 for t in within)} de {len(within)} con aviso en el teléfono"
    )
    return "\n".join(lines)


def main(argv: list[str]) -> None:
    backend_log, logcat = (
        Path(f).read_text(encoding="utf-8", errors="replace") for f in argv[:2]
    )
    print(table(rows(backend_log, logcat, int(argv[2]))))


if __name__ == "__main__":
    main(sys.argv[1:])
