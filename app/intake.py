from datetime import datetime, timezone
import math

from app.db import submissions_collection
from app.messaging import AudioInputError, request_location, send_text, send_payload
from app import workflow
from app.transcription import transcribe_audio
from app.tracing import event


def location_fields(location):
    try:
        latitude = float(location["latitude"])
        longitude = float(location["longitude"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("Ubicación inválida")
    if not math.isfinite(latitude) or not math.isfinite(longitude) or not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Coordenadas inválidas")
    return {
        "latitude": latitude,
        "longitude": longitude,
        "name": location.get("name"),
        "address": location.get("address"),
        "maps_url": f"https://www.google.com/maps?q={latitude},{longitude}",
    }


def process_message(message):
    sender = message.get("from")
    message_id = message.get("id")
    if not sender or not message_id:
        return
    if submissions_collection is None:
        raise RuntimeError("Falta configurar MONGODB_URI")

    previous = submissions_collection.find_one({"_id": message_id})
    if previous:
        event("message.duplicate", acknowledged=previous.get("acknowledged"), response_state=previous.get("response_state"))
        # Un reintento no vuelve a transcribir ni a guardar la ubicación.
        if not previous.get("acknowledged"):
            deliver_response(sender, previous)
        return

    kind = message.get("type")
    record = {
        "_id": message_id,
        "from_number": sender,
        "type": kind,
        "whatsapp_timestamp": message.get("timestamp"),
        "received_at": datetime.now(timezone.utc),
        "acknowledged": False,
    }
    if kind == "location":
        try:
            record["location"] = location_fields(message.get("location", {}))
        except ValueError:
            record["reply"] = "No pude leer esa ubicación. Compártela nuevamente desde Adjuntar > Ubicación."
        else:
            record["reply"] = "Ubicación guardada: " + record["location"]["maps_url"] + "\nPaso 2: envía una nota de voz. Te devolveré la transcripción."
    elif kind == "audio":
        try:
            record["transcription"] = transcribe_audio(message["audio"]["id"])
        except AudioInputError as error:
            record["reply"] = str(error)
        else:
            record["reply"] = "Transcripción guardada:\n" + record["transcription"][:3500] + "\nPaso 3: envía una foto. El archivo de audio no se conserva en este servidor."
    elif kind in {"image", "video", "document"}:
        media = message.get(kind, {})
        media_id = media.get("id", "")
        if not isinstance(media_id, str) or not media_id.isdigit():
            record["reply"] = "No pude leer el archivo. Vuelve a adjuntarlo o escribe menú."
        else:
            record["media"] = {key: media[key] for key in ("id", "mime_type", "sha256", "filename", "caption") if key in media}
            next_step = {"image": "Paso 4: envía un video.", "video": "Paso 5: envía un documento PDF.",
                         "document": "Paso 6: escribe enlace para probar un botón con URL."}[kind]
            outgoing = {"id": media_id, "caption": "Archivo recibido y devuelto por el bot. " + next_step}
            if kind == "document" and media.get("filename"):
                outgoing["filename"] = media["filename"]
            record["response_payload"] = {"type": kind, kind: outgoing}
    else:
        choice = workflow.selection(message)
        record["selection"] = choice[:256]
        record["response_payload"] = workflow.route(choice, sender, submissions_collection)

    # El _id de WhatsApp impide duplicar registros si Meta reenvía un evento.
    submissions_collection.update_one({"_id": message_id}, {"$setOnInsert": record}, upsert=True)
    event("message.saved", payload=record)
    deliver_response(sender, submissions_collection.find_one({"_id": message_id}))


def deliver_response(sender, record):
    # Reserva persistente y atómica, compartida por todos los workers/reinicios.
    # Un timeout puede ocurrir DESPUÉS de que Meta haya aceptado el mensaje.
    claimed = submissions_collection.find_one_and_update(
        {"_id": record["_id"], "acknowledged": {"$ne": True}, "response_state": {"$exists": False}},
        {"$set": {"response_state": "sending", "response_attempted_at": datetime.now(timezone.utc)}},
    )
    if claimed is None:
        event("response.skipped", reason="already_attempted", source_message_id=record["_id"])
        return
    try:
        if record.get("response_payload"):
            result = send_payload(sender, record["response_payload"])
        elif record.get("request_location"):
            result = request_location(sender)
        else:
            result = send_text(sender, record["reply"])
    except Exception as error:
        submissions_collection.update_one({"_id": record["_id"]}, {"$set": {"response_state": "unknown"}})
        event("response.unknown", error_type=type(error).__name__)
        raise
    fields = {"acknowledged": True, "response_state": "sent"}
    if isinstance(result, dict):
        fields["whatsapp_response"] = result
    submissions_collection.update_one({"_id": record["_id"]}, {"$set": fields})
    event("response.sent", source_message_id=record["_id"])
