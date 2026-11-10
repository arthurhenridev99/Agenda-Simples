"""Envio de modelo aprovado via WhatsApp Cloud API (Meta)."""
import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

def enviar_codigo_whatsapp(telefone, codigo):
    token = os.environ.get("WHATSAPP_ACCESS_TOKEN", "").strip()
    phone_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    template = os.environ.get("WHATSAPP_TEMPLATE_NAME", "").strip()
    idioma = os.environ.get("WHATSAPP_TEMPLATE_LANGUAGE", "pt_BR").strip()
    version = os.environ.get("WHATSAPP_GRAPH_VERSION", "v22.0").strip()
    if not all((token, phone_id, template)) or not version.startswith("v"):
        return False
    payload = {
        "messaging_product": "whatsapp",
        "to": "55" + telefone,
        "type": "template",
        "template": {
            "name": template,
            "language": {"code": idioma},
            "components": [{"type": "body", "parameters": [{"type": "text", "text": codigo}]}],
        },
    }
    req = Request(
        f"https://graph.facebook.com/{version}/{phone_id}/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=10) as response:
            return 200 <= response.status < 300
    except (HTTPError, URLError, TimeoutError, ValueError):
        return False
