"""Paso 15 (D17): la suscripción push apunta al túnel con su audiencia."""

from app.config import settings
from scripts.pubsub_endpoint import commands


def test_modifies_or_creates_with_endpoint_and_audience(monkeypatch):
    monkeypatch.setattr(
        settings, "gmail_pubsub_topic", "projects/proyecto-x/topics/gmail-fsf"
    )
    monkeypatch.setattr(
        settings, "pubsub_push_service_account", "sa@proyecto-x.iam.gserviceaccount.com"
    )
    [modify] = commands("https://uno-dos.trycloudflare.com/", exists=True)
    assert modify[:4] == [
        "pubsub",
        "subscriptions",
        "modify-push-config",
        "gmail-fsf-push",
    ]
    assert "--push-endpoint=https://uno-dos.trycloudflare.com/gmail/push" in modify
    assert (
        "--push-auth-token-audience=https://uno-dos.trycloudflare.com/gmail/push"
        in modify
    )
    assert "--project=proyecto-x" in modify
    [create] = commands("https://uno-dos.trycloudflare.com", exists=False)
    assert (
        create[2] == "create"
        and "--topic=projects/proyecto-x/topics/gmail-fsf" in create
    )
    assert "--push-auth-service-account=sa@proyecto-x.iam.gserviceaccount.com" in create
