"""Categoriza los movimientos sin categoría y pasa por el LLM los que quedaron en 'pendiente' (Paso 10).

    cd backend && .venv/Scripts/python.exe -m scripts.categorize_backfill            # Supabase local
    cd backend && .venv/Scripts/python.exe -m scripts.categorize_backfill --remote   # nube: solo con
                                                                                       # confirmación
Usa la configuración de backend/.env (service_role). Si SUPABASE_URL no es local, exige --remote:
toda escritura en el proyecto de la nube requiere confirmación explícita del supervisor.
"""

import sys
from urllib.parse import urlparse

from app import categorize
from app.config import settings


def main(argv: list[str]) -> None:
    local = urlparse(settings.supabase_url).hostname in ("127.0.0.1", "localhost")
    if not local and "--remote" not in argv:
        sys.exit(
            "SUPABASE_URL no es local: añade --remote solo con confirmación del supervisor"
        )
    print("destino:", "local" if local else "NUBE")
    print("movimientos por origen de la categoría:", categorize.backfill())


if __name__ == "__main__":
    main(sys.argv[1:])
