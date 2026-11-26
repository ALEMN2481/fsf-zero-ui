"""Apunta la suscripción push de Gmail a la URL del túnel (D17; lo usa el kit de la expo).

    cd backend && .venv/Scripts/python.exe -m scripts.pubsub_endpoint <url del túnel>

Crea la suscripción si no existe y si existe cambia su endpoint y audiencia
(gcloud pubsub subscriptions modify-push-config). El tema y la cuenta de servicio salen de la
configuración del backend (GMAIL_PUBSUB_TOPIC, PUBSUB_PUSH_SERVICE_ACCOUNT) y no se imprimen.
La audiencia del backend se pasa al arrancarlo: PUBSUB_PUSH_AUDIENCE=<url>/gmail/push.
Necesita gcloud instalado y con sesión (gcloud init).
"""

import shutil
import subprocess
import sys

from app.config import settings

SUBSCRIPTION = "gmail-fsf-push"


def commands(url: str, exists: bool) -> list[list[str]]:
    endpoint = url.rstrip("/") + "/gmail/push"
    project = settings.gmail_pubsub_topic.split("/")[1]  # projects/<id>/topics/<tema>
    auth = [
        f"--push-endpoint={endpoint}",
        f"--push-auth-service-account={settings.pubsub_push_service_account}",
        f"--push-auth-token-audience={endpoint}",
        f"--project={project}",
    ]
    if exists:
        return [["pubsub", "subscriptions", "modify-push-config", SUBSCRIPTION, *auth]]
    return [
        [
            "pubsub",
            "subscriptions",
            "create",
            SUBSCRIPTION,
            f"--topic={settings.gmail_pubsub_topic}",
            "--ack-deadline=60",
            *auth,
        ]
    ]


def main(argv: list[str]) -> None:
    if len(argv) != 1 or not argv[0].startswith("https://"):
        sys.exit("Uso: python -m scripts.pubsub_endpoint https://<túnel>")
    gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if not gcloud:
        sys.exit("No encuentro gcloud: instálalo e inicia sesión (gcloud init)")
    project = settings.gmail_pubsub_topic.split("/")[1]
    exists = (
        subprocess.run(
            [
                gcloud,
                "pubsub",
                "subscriptions",
                "describe",
                SUBSCRIPTION,
                f"--project={project}",
            ],
            check=False,
            capture_output=True,
        ).returncode
        == 0
    )
    for cmd in commands(argv[0], exists):
        r = subprocess.run([gcloud, *cmd], check=False, capture_output=True, text=True)
        if r.returncode != 0:
            # Solo la última línea: el error de gcloud no lleva secretos, pero sí rutas largas.
            sys.exit(f"gcloud falló: {r.stderr.strip().splitlines()[-1:]}")
    print(
        f"suscripción {SUBSCRIPTION} {'actualizada' if exists else 'creada'}: {argv[0]}/gmail/push"
    )


if __name__ == "__main__":
    main(sys.argv[1:])
