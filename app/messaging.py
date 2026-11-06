import os
from pathlib import Path
from urllib.parse import urlparse

import requests


class AudioInputError(ValueError):
    """Audio que el usuario debe volver a enviar corregido."""


def graph_base():
    version = os.getenv("WHATSAPP_API_VERSION", "v23.0")
    return f"https://graph.facebook.com/{version}"


def auth_headers():
    token = os.getenv("WHATSAPP_TOKEN")
    if not token:
        raise RuntimeError("Falta WHATSAPP_TOKEN")
    return {"Authorization": f"Bearer {token}"}


def send_payload(to_number: str, content: dict):
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    if not phone_id:
        raise RuntimeError("Falta WHATSAPP_PHONE_NUMBER_ID")
    response = requests.post(
        f"{graph_base()}/{phone_id}/messages",
        headers=auth_headers(),
        json={"messaging_product": "whatsapp", "recipient_type": "individual", "to": to_number, **content},
        timeout=(10, 30),
    )
    response.raise_for_status()
    return response.json()


def send_text(to_number: str, message_text: str):
    return send_payload(to_number, {"type": "text", "text": {"preview_url": False, "body": message_text}})


def request_location(to_number: str):
    return send_payload(to_number, {
        "type": "interactive",
        "interactive": {
            "type": "location_request_message",
            "body": {"text": "¡Hola! Comparte tu ubicación para guardarla. También puedes enviar una nota de voz: la convertiré a texto y guardaré solo la transcripción."},
            "action": {"name": "send_location"},
        },
    })


def download_audio(media_id: str, destination: Path, max_bytes: int):
    if not media_id.isdigit():
        raise ValueError("Identificador de audio inválido")
    metadata = requests.get(f"{graph_base()}/{media_id}", headers=auth_headers(), timeout=(10, 30))
    metadata.raise_for_status()
    info = metadata.json()
    if int(info.get("file_size", 0)) > max_bytes:
        raise AudioInputError("El audio es demasiado grande. Envía uno más corto (máximo 20 MB).")
    # La URL proviene de Meta, nunca directamente del webhook.
    url = info["url"]
    parsed = urlparse(url)
    host = parsed.hostname or ""
    allowed_domains = ("facebook.com", "fbcdn.net", "fbsbx.com")
    if parsed.scheme != "https" or not any(host == domain or host.endswith("." + domain) for domain in allowed_domains):
        raise ValueError("URL de descarga de Meta inválida")
    with requests.get(url, headers=auth_headers(), timeout=(10, 60), stream=True, allow_redirects=False) as response:
        response.raise_for_status()
        if response.status_code != 200:
            raise RuntimeError("No se pudo descargar el audio")
        size = 0
        with destination.open("wb") as target:
            for chunk in response.iter_content(chunk_size=65536):
                size += len(chunk)
                if size > max_bytes:
                    raise AudioInputError("El audio es demasiado grande. Envía uno más corto (máximo 20 MB).")
                target.write(chunk)
    if size == 0:
        raise AudioInputError("El audio está vacío. Envía otra nota de voz.")
