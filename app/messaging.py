import os
import requests

TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
GRAPH_URL = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}


def send_text(to_number: str, message_text: str):
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_number,
        "type": "text",
        "text": {"preview_url": False, "body": message_text},
    }
    response = requests.post(GRAPH_URL, json=payload, headers=HEADERS)
    return response.json()


def send_buttons(to_number: str, body_text: str, buttons: list):
    """
    buttons: lista de dicts [{"id": "cat_123", "title": "Ropa"}, ...]
    Máximo 3 botones. title máximo 20 caracteres (WhatsApp lo trunca/rechaza si es más largo).
    """
    button_objects = [
        {
            "type": "reply",
            "reply": {"id": b["id"], "title": b["title"][:20]},
        }
        for b in buttons[:3]
    ]

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body_text},
            "action": {"buttons": button_objects},
        },
    }
    response = requests.post(GRAPH_URL, json=payload, headers=HEADERS)
    return response.json()
