from datetime import datetime, timezone
import math

from app.db import submissions_collection
from app.messaging import AudioInputError, request_location, send_text
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
            record["reply"] = "Ubicación guardada. Ahora puedes enviar una nota de voz para guardar lo que digas como texto."
    elif kind == "audio":
        try:
            record["transcription"] = transcribe_audio(message["audio"]["id"])
        except AudioInputError as error:
            record["reply"] = str(error)
        else:
            record["reply"] = "Transcripción guardada. El archivo de audio no se conserva en este servidor."
    elif kind in {"image", "video"}:
        record["reply"] = "El guardado de fotos y videos todavía no está habilitado. Por ahora puedes compartir tu ubicación o una nota de voz."
    else:
        record["request_location"] = True

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
        if record.get("request_location"):
            request_location(sender)
        else:
            send_text(sender, record["reply"])
    except Exception as error:
        submissions_collection.update_one({"_id": record["_id"]}, {"$set": {"response_state": "unknown"}})
        event("response.unknown", error_type=type(error).__name__)
        raise
    submissions_collection.update_one({"_id": record["_id"]}, {"$set": {"acknowledged": True, "response_state": "sent"}})
    event("response.sent", source_message_id=record["_id"])
