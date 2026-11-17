"""Recorrido real de prueba en WhatsApp; una respuesta por mensaje recibido."""
import json
import os


def text(body):
    return {"type": "text", "text": {"body": body[:4096], "preview_url": False}}


def buttons(body, options):
    return {"type": "interactive", "interactive": {
        "type": "button", "body": {"text": body},
        "action": {"buttons": [{"type": "reply", "reply": {"id": key, "title": title}}
                               for key, title in options]}}}


def menu():
    return buttons("¡Hola! Este recorrido usa mensajes reales de WhatsApp. Puedes probar cada tipo y volver escribiendo menú.",
                   [("iniciar", "Iniciar recorrido"), ("tipos", "Ver opciones"), ("resumen", "Mi resumen")])


def choices():
    rows = [("ubicacion", "Ubicación"), ("audio", "Nota de voz"), ("foto", "Foto"),
            ("video", "Video"), ("documento", "Documento"), ("enlace", "Botón con enlace"),
            ("mapa", "Recibir mapa"), ("plantilla", "Recibir plantilla"), ("resumen", "Mi resumen")]
    return {"type": "interactive", "interactive": {"type": "list",
        "body": {"text": "Elige qué quieres probar. Escribe menú para regresar."},
        "action": {"button": "Elegir prueba", "sections": [{"title": "Pruebas de WhatsApp",
            "rows": [{"id": key, "title": title} for key, title in rows]}]}}}


def location_request():
    return {"type": "interactive", "interactive": {"type": "location_request_message",
        "body": {"text": "Paso 1: comparte tu ubicación con el botón. Guardaré las coordenadas y después probaremos una nota de voz."},
        "action": {"name": "send_location"}}}


def route(choice, sender, collection):
    if choice in {"iniciar", "ubicacion", "tecnico"}:
        return location_request()
    if choice in {"tipos", "pagos"}:
        return choices()
    prompts = {
        "audio": "Graba y envía una nota de voz. La transcribiré con Groq y te devolveré el texto.",
        "foto": "Adjunta una foto. Te devolveré la misma imagen para comprobar recepción y envío.",
        "video": "Adjunta un video. Te devolveré el mismo video para comprobar el reproductor.",
        "documento": "Adjunta un documento de prueba, por ejemplo un PDF. Te lo devolveré por WhatsApp.",
    }
    if choice in prompts:
        return text(prompts[choice])
    if choice in {"enlace", "medios"}:
        url = os.getenv("TEST_LINK_URL", "https://www.whatsapp.com/")
        if not url.startswith("https://"):
            return text("Configura TEST_LINK_URL con una dirección HTTPS válida. Escribe opciones para continuar.")
        return {"type": "interactive", "interactive": {"type": "cta_url",
            "body": {"text": "Abre el enlace y vuelve al chat. Luego escribe mapa para recibir un punto, o plantilla para probar una plantilla. El enlace no realiza pagos."},
            "action": {"name": "cta_url", "parameters": {"display_text": "Abrir enlace", "url": url}}}}
    if choice == "mapa":
        return {"type": "location", "location": {"latitude": -0.1807, "longitude": -78.4678,
            "name": "Punto de prueba en Quito", "address": "Punto de ejemplo. Escribe plantilla para continuar."}}
    if choice == "plantilla":
        name = os.getenv("TEST_TEMPLATE_NAME")
        if not name:
            return text("Para esta prueba configura TEST_TEMPLATE_NAME y TEST_TEMPLATE_LANGUAGE con una plantilla aprobada en tu cuenta de Meta. Después escribe plantilla. Escribe resumen para terminar.")
        try:
            params = json.loads(os.getenv("TEST_TEMPLATE_PARAMS", "[]"))
            if not isinstance(params, list) or not all(isinstance(p, str) for p in params):
                raise ValueError()
        except (ValueError, TypeError):
            return text("TEST_TEMPLATE_PARAMS debe ser una lista JSON de textos. Escribe menú para continuar.")
        template = {"name": name, "language": {"code": os.getenv("TEST_TEMPLATE_LANGUAGE", "es")}}
        if params:
            template["components"] = [{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}]
        return {"type": "template", "template": template}
    if choice == "resumen":
        pipeline = [{"$match": {"from_number": sender}}, {"$group": {"_id": "$type", "total": {"$sum": 1}}}]
        counts = sorted(collection.aggregate(pipeline), key=lambda row: str(row["_id"]))
        return text("Mensajes guardados de tu número (incluye pruebas anteriores):\n" +
                    "\n".join(f"{row['_id']}: {row['total']}" for row in counts) + "\nEscribe menú para reiniciar.")
    return menu()


def selection(message):
    if message.get("type") == "interactive":
        interactive = message.get("interactive", {})
        kind = interactive.get("type")
        if kind in {"button_reply", "list_reply"}:
            return interactive.get(kind, {}).get("id", "")
        return ""
    if message.get("type") == "button":
        return message.get("button", {}).get("payload", "")
    body = message.get("text", {}).get("body", "").strip().lower()
    return {"opciones": "tipos", "menú": "menu", "hola": "menu", "imagen": "foto"}.get(body, body)
