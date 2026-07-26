import os
import requests
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

# Cargar variables de entorno locales
load_dotenv()

app = FastAPI(title="WhatsApp Bot API")

TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")


@app.get("/")
def read_root():
    return {"status": "ok", "message": "Servidor de WhatsApp activo"}


# ------------------------------------------------------------------
# 1. VERIFICACIÓN DEL WEBHOOK (Meta envía una petición GET)
# ------------------------------------------------------------------
@app.get("/webhook")
def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token")
):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        print("Webhook verificado con éxito!")
        return PlainTextResponse(content=hub_challenge, status_code=200)
    
    raise HTTPException(status_code=403, detail="Token de verificación inválido")


# ------------------------------------------------------------------
# 2. RECEPCIÓN DE MENSAJES (Meta envía una petición POST)
# ------------------------------------------------------------------
@app.post("/webhook")
async def receive_webhook(request: Request):
    data = await request.json()
    print("Payload recibido:", data)
    
    try:
        # Extraer el mensaje si existe en la estructura de Meta
        entries = data.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                messages = value.get("messages", [])
                
                if messages:
                    msg = messages[0]
                    from_number = msg.get("from")  # Número del remitente
                    msg_body = msg.get("text", {}).get("body")  # Texto enviado
                    
                    print(f"Mensaje de {from_number}: {msg_body}")
                    
                    # AQUÍ PUEDES RESPONDER AUTOMÁTICAMENTE
                    # Por ejemplo, si te escriben "hola", responder un saludo.

    except Exception as e:
        print(f"Error procesando webhook: {e}")

    return {"status": "success"}


# ------------------------------------------------------------------
# 3. FUNCIÓN PARA ENVIAR MENSAJES
# ------------------------------------------------------------------
@app.post("/send-message")
def send_whatsapp_message(to_number: str, message_text: str):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_number,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": message_text
        }
    }
    
    response = requests.post(url, json=payload, headers=headers)
    return response.json()