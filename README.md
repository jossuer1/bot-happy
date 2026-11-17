# Bot Happy: flujo real de prueba en WhatsApp

FastAPI recibe los webhooks firmados de Meta, responde por WhatsApp Cloud API y guarda registros en MongoDB. No hay página de simulación ni modo dry-run. Escribe **hola** al número del bot para comenzar.

## Recorrido completo

1. **Hola**: recibe un menú con tres botones: Iniciar recorrido, Ver opciones y Mi resumen.
2. **Ver opciones**: abre una lista real para elegir qué tipo de mensaje probar.
3. **Iniciar recorrido**: solicita ubicación con el selector nativo de WhatsApp.
4. **Comparte tu ubicación**: guarda coordenadas, nombre/dirección si existen y enlace de Google Maps. Responde con el enlace y pide una nota de voz.
5. **Envía una nota de voz**: descarga temporalmente el audio, lo convierte con FFmpeg y lo transcribe con Groq. Guarda y devuelve el texto reconocido, y pide una foto.
6. **Envía una foto**: guarda metadatos y devuelve la misma imagen por su ID de Meta; el pie pide un video.
7. **Envía un video**: devuelve el mismo video; el pie pide un documento.
8. **Envía un documento**: devuelve el mismo documento, incluyendo su nombre si existe; el pie indica escribir enlace.
9. **Escribe enlace**: recibe un botón con una URL HTTPS. Ábrelo y regresa al chat. El enlace no realiza pagos y su apertura no genera una selección para el webhook.
10. **Escribe mapa**: recibe un punto de prueba en Quito como mensaje nativo de ubicación. No se calcula el servicio más cercano.
11. **Escribe plantilla**: envía una plantilla real configurada y aprobada en tu cuenta de Meta. Si falta configuración, explica qué variable completar.
12. **Escribe resumen**: muestra cantidades de mensajes guardados de tu propio número, incluyendo pruebas anteriores.

Puedes escribir **menú** en cualquier momento, o **opciones** para abrir la lista. También funcionan los comandos ubicación, audio, foto, video y documento. Cada mensaje se procesa de forma independiente: puedes saltar pasos o repetirlos. El recorrido se guía mediante respuestas; no impone una máquina de estados ni agrupa los datos en casos.

Los envíos y la transcripción son reales y pueden consumir las cuotas de tus proveedores. No hay consultas de saldo, cobros ni transacciones financieras implementadas.

## Configuración

Conserva tu `.env`. Usa `.env.example` como referencia sin reemplazar tus credenciales:

- `VERIFY_TOKEN`: token de verificación del webhook en Meta.
- `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`: credenciales de envío.
- `WHATSAPP_APP_SECRET`: secreto de la aplicación para validar la firma de los POST.
- `WHATSAPP_API_VERSION`: versión habilitada en tu aplicación.
- `MONGODB_URI`, `MONGODB_DB_NAME`: conexión de MongoDB.
- `GROQ_API_KEY`: clave para transcribir notas de voz.
- `GROQ_TRANSCRIPTION_MODEL`: `whisper-large-v3-turbo` por defecto.
- `FFMPEG_BINARY`: `ffmpeg` por defecto; Docker instala el ejecutable.
- `TEST_LINK_URL`: URL HTTPS para el botón; por defecto abre `https://www.whatsapp.com/`.
- `TEST_TEMPLATE_NAME`: nombre exacto de una plantilla aprobada. Sin esta variable, solo se omite la prueba de plantilla.
- `TEST_TEMPLATE_LANGUAGE`: idioma exacto aprobado, por defecto `es`.
- `TEST_TEMPLATE_PARAMS`: lista JSON de textos para los parámetros del cuerpo, en orden; por ejemplo `["Cliente"]`. Usa `[]` si no tiene variables.

La prueba de plantilla admite cuerpo con parámetros de texto; no construye cabeceras multimedia ni botones dinámicos. Si tu cuenta dispone de `hello_world` en `en_US`, puedes configurar ese nombre, ese idioma y `[]`; confirma primero que esté disponible en tu cuenta. La aceptación y entrega dependen de Meta. El flujo no programa mensajes fuera de la ventana de atención.

`DEMO_ENABLED` ya no se utiliza. Las rutas `/demo` no existen.

## Ejecución y Render

Desde `bot-happy`, con Python 3.11 o superior y FFmpeg instalado:

    pip install -r requirements.txt
    uvicorn app.main:app --host 0.0.0.0 --port 8000

Con Docker:

    docker compose build
    docker compose up

Compose no inicia MongoDB. Para una instancia de Windows usa una URI accesible desde el contenedor, como `mongodb://host.docker.internal:27017`, o MongoDB Atlas.

En Render despliega este código con el Dockerfile, conserva las variables actuales y configura las opciones `TEST_*` que quieras usar. En Meta configura la URL HTTPS terminada en `/webhook`, suscribe `messages` y usa tu teléfono como destinatario autorizado si trabajas con un número de prueba. Cuando el servicio esté activo, envía **hola** por WhatsApp. No hace falta habilitar una demo.

## Datos y trazabilidad

La colección `submissions` guarda un documento por ID de mensaje de WhatsApp:

- Remitente, tipo, fecha de recepción y timestamp de WhatsApp.
- Ubicación validada o transcripción, según el tipo.
- `media`: ID, MIME, hash y nombre/pie cuando existen para fotos, videos y documentos.
- `selection`: comando o ID de la opción elegida. El texto libre puede quedar aquí hasta 256 caracteres.
- `reply` o `response_payload`: contenido de la respuesta.
- `response_state`, `acknowledged` y `whatsapp_response`: reserva de envío, aceptación e ID devuelto por Meta.

Los archivos de foto, video y documento se devuelven usando su ID de Meta: no se descargan ni se almacenan en Cloudinary o en disco. Los ID no constituyen un archivo permanente. Solo se conserva el texto del audio; sus archivos temporales se eliminan incluso si ocurre un error. El audio tiene un límite de 20 MB antes y después de convertirlo.

Los logs JSON permiten seguir `webhook.received`, `message.processing`, `message.saved`, `whatsapp.request`, `whatsapp.response` y `response.sent`. Filtra por `trace_id` o `message_id`. Las notificaciones de estado de Meta se registran en el evento entrante y no generan respuestas. `acknowledged` significa aceptación por Meta, no entrega al teléfono.

`LOG_JSON_PAYLOADS=true` muestra cuerpos completos, incluidos teléfonos y datos enviados. Usa `false` para ocultar los cuerpos en los eventos. No se registran cabeceras Authorization ni archivos binarios.

Cada respuesta se reserva atómicamente antes de enviarla. Los estados `sending`, `sent` y `unknown` impiden repetir envíos por reintentos del mismo mensaje. Ante un timeout, revisa el registro antes de reenviar manualmente. Envía un mensaje nuevo para repetir una prueba.

La transcripción se ejecuta mientras el webhook espera. Para alto volumen se requiere una cola persistente. Dos entregas simultáneas del mismo audio todavía pueden repetir la transcripción, aunque la reserva evita una segunda respuesta. Las colecciones antiguas del catálogo se conservan; no ejecutes `app.scripts.seed_catalog`, que borra y reemplaza el catálogo.

## Pruebas

    pip install -r requirements-dev.txt
    python -m unittest discover -s tests -v

Las pruebas sustituyen MongoDB, Meta y Groq. El recorrido automatizado entra por el webhook firmado y verifica los JSON que se enviarían por el transporte HTTP real, sin enviar mensajes a personas. La validación en un teléfono requiere desplegar el servicio con las credenciales configuradas.

Referencia: [mensajes de documento por ID en la colección oficial de Meta](https://www.postman.com/meta/whatsapp-business-platform/request/zjtbdpz/send-document-message-by-id).