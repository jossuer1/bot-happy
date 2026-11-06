import hashlib
import hmac
import json
import logging
import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse

from app.intake import process_message

app = FastAPI(title="Bot Happy - Ubicaciones y notas de voz")
logger = logging.getLogger(__name__)


@app.get("/")
def read_root():
    return {"status": "ok", "message": "Servidor de WhatsApp activo"}


@app.get("/webhook")
def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    token = os.getenv("VERIFY_TOKEN")
    if token and hub_mode == "subscribe" and hub_verify_token == token and hub_challenge:
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403, detail="Verificación inválida")


@app.post("/webhook")
async def receive_webhook(request: Request):
    secret = os.getenv("WHATSAPP_APP_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="Falta configurar WHATSAPP_APP_SECRET")
    body = await request.body()
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(request.headers.get("x-hub-signature-256", ""), expected):
        raise HTTPException(status_code=403, detail="Firma inválida")
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="JSON inválido")
    if not isinstance(data, dict) or data.get("object") != "whatsapp_business_account":
        raise HTTPException(status_code=400, detail="Evento de WhatsApp inválido")

    failed = False
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                try:
                    await run_in_threadpool(process_message, message)
                except Exception:
                    # No registrar teléfonos, ubicaciones, audio ni transcripciones.
                    logger.error("No se pudo procesar un mensaje de WhatsApp")
                    failed = True
    if failed:
        raise HTTPException(status_code=503, detail="No se procesaron todos los mensajes; reintentar")
    return {"status": "success"}
