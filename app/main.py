import os
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from app.messaging import send_text, send_buttons
from app.catalog import (
    get_categories,
    get_category_by_id,
    get_products_by_category,
    get_product_by_id,
)

load_dotenv()

app = FastAPI(title="WhatsApp Bot API")

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
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        print("Webhook verificado con éxito!")
        return PlainTextResponse(content=hub_challenge, status_code=200)

    raise HTTPException(status_code=403, detail="Token de verificación inválido")


# ------------------------------------------------------------------
# 2. LÓGICA DEL MENÚ / CATÁLOGO
# ------------------------------------------------------------------
def enviar_menu_categorias(from_number: str):
    categorias = get_categories(limit=3)

    if not categorias:
        send_text(from_number, "Todavía no hay categorías cargadas en el catálogo.")
        return

    buttons = [
        {"id": f"cat_{str(c['_id'])}", "title": c["name"]} for c in categorias
    ]
    send_buttons(from_number, "¡Hola! Elige una categoría para ver el catálogo:", buttons)


def enviar_productos_de_categoria(from_number: str, category_id: str):
    categoria = get_category_by_id(category_id)
    productos = get_products_by_category(category_id, limit=3)

    if not productos:
        send_text(from_number, "No hay productos en esta categoría todavía.")
        return

    nombre_categoria = categoria["name"] if categoria else "esta categoría"

    # WhatsApp buttons no soportan descripción/precio en el botón,
    # así que mandamos un resumen en texto y luego los botones para elegir.
    resumen = f"Productos en *{nombre_categoria}*:\n\n"
    for p in productos:
        resumen += f"• {p['name']} - ${p.get('price', 'N/D')}\n"
    send_text(from_number, resumen)

    buttons = [
        {"id": f"prod_{str(p['_id'])}", "title": p["name"]} for p in productos
    ]
    send_buttons(from_number, "Toca un producto para ver el detalle:", buttons)


def enviar_detalle_producto(from_number: str, product_id: str):
    producto = get_product_by_id(product_id)

    if not producto:
        send_text(from_number, "No encontré ese producto.")
        return

    detalle = (
        f"*{producto['name']}*\n"
        f"{producto.get('description', 'Sin descripción disponible.')}\n"
        f"Precio: ${producto.get('price', 'N/D')}"
    )
    send_text(from_number, detalle)

    buttons = [{"id": "menu", "title": "Ver menú"}]
    send_buttons(from_number, "¿Quieres ver otra categoría?", buttons)


# ------------------------------------------------------------------
# 3. RECEPCIÓN DE MENSAJES (Meta envía una petición POST)
# ------------------------------------------------------------------
@app.post("/webhook")
async def receive_webhook(request: Request):
    data = await request.json()
    print("Payload recibido:", data)

    try:
        entries = data.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                messages = value.get("messages", [])

                if not messages:
                    continue

                msg = messages[0]
                from_number = msg.get("from")
                msg_type = msg.get("type")

                if msg_type == "text":
                    # Cualquier texto entrante muestra el menú de categorías
                    enviar_menu_categorias(from_number)

                elif msg_type == "interactive":
                    interactive = msg.get("interactive", {})
                    if interactive.get("type") == "button_reply":
                        button_id = interactive["button_reply"]["id"]

                        if button_id == "menu":
                            enviar_menu_categorias(from_number)
                        elif button_id.startswith("cat_"):
                            category_id = button_id.replace("cat_", "", 1)
                            enviar_productos_de_categoria(from_number, category_id)
                        elif button_id.startswith("prod_"):
                            product_id = button_id.replace("prod_", "", 1)
                            enviar_detalle_producto(from_number, product_id)

    except Exception as e:
        print(f"Error procesando webhook: {e}")

    return {"status": "success"}


# ------------------------------------------------------------------
# 4. FUNCIÓN PARA ENVIAR MENSAJES (uso manual / pruebas)
# ------------------------------------------------------------------
@app.post("/send-message")
def send_whatsapp_message(to_number: str, message_text: str):
    return send_text(to_number, message_text)
