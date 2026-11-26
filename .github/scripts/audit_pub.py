"""Auditoría de dependencias de la app (Paso 15): consulta en OSV cada paquete de pubspec.lock.

Uso: python .github/scripts/audit_pub.py app/pubspec.lock
Sale con 1 si hay vulnerabilidades conocidas. Solo envía nombre y versión de cada paquete.
"""

import json
import re
import sys
import urllib.request


def packages(lock: str) -> list[tuple[str, str]]:
    found, name = [], None
    for line in lock.splitlines():
        if m := re.fullmatch(r"  ([a-z0-9_]+):", line):
            name = m.group(1)
        elif name and (m := re.fullmatch(r'    version: "([^"]+)"', line)):
            found.append((name, m.group(1)))
            name = None
    return found


def main(path: str) -> int:
    pkgs = packages(open(path, encoding="utf-8").read())
    body = {
        "queries": [
            {"package": {"name": n, "ecosystem": "Pub"}, "version": v} for n, v in pkgs
        ]
    }
    req = urllib.request.Request(
        "https://api.osv.dev/v1/querybatch",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        results = json.load(r)["results"]
    vulnerable = [
        (n, v, [x["id"] for x in res.get("vulns", [])])
        for (n, v), res in zip(pkgs, results, strict=True)
        if res.get("vulns")
    ]
    print(f"paquetes revisados: {len(pkgs)}; con vulnerabilidades: {len(vulnerable)}")
    for n, v, ids in vulnerable:
        print(f"  {n} {v}: {', '.join(ids)}")
    return 1 if vulnerable else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
