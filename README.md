# Bot Happy: ubicaciones y transcripciones de WhatsApp

FastAPI recibe webhooks de WhatsApp Cloud API y guarda información en MongoDB.
El catálogo anterior deja de ser el flujo activo; sus colecciones no se borran ni modifican.

## Flujo

1. Envía hola (o cualquier texto) al número del bot.
2. El bot pide tu ubicación mediante el botón de WhatsApp. También puedes usar Adjuntar > Ubicación.
3. Al compartirla, guarda latitud, longitud, nombre/dirección si WhatsApp los incluye y un enlace de Google Maps.
4. Envía una nota de voz. Se descarga temporalmente, se convierte a MP3 con FFmpeg y se envía a la API de OpenAI para transcribirla. Solo el texto se guarda en MongoDB; los archivos temporales se eliminan incluso si hay errores. La conservación de datos en el proveedor depende de sus políticas.
5. Las fotos y videos reciben un aviso de que el almacenamiento todavía no está habilitado. No se descargan ni guardan sus archivos. Cloudinary queda pendiente.

No necesitas enviar la ubicación antes de un audio: ambos se guardan de forma independiente y se relacionan por from_number. Aún no existe agrupación por caso o reporte, ni panel para consultar datos.

## Configuración

Copia .env.example a .env solo si no tienes uno y completa:

- VERIFY_TOKEN: el mismo token configurado al verificar el webhook en Meta.
- WHATSAPP_TOKEN y WHATSAPP_PHONE_NUMBER_ID: credenciales de WhatsApp Cloud API.
- WHATSAPP_APP_SECRET: secreto de la aplicación de Meta para verificar la firma de cada POST. Es diferente del token de verificación.
- WHATSAPP_API_VERSION: versión habilitada en tu aplicación de Meta.
- MONGODB_URI y MONGODB_DB_NAME: base de datos existente o nueva.
- OPENAI_API_KEY: clave de API de OpenAI con acceso al modelo y saldo disponible. Se obtiene en https://platform.openai.com/api-keys y se configura en Render > Environment.
- OPENAI_TRANSCRIPTION_MODEL: gpt-transcribe por defecto. Solo necesitas agregar esta variable si quieres usar otro modelo compatible con tu cuenta.
- FFMPEG_BINARY: ffmpeg por defecto. Docker lo instala automáticamente.

Las antiguas variables WHISPER_* ya no se usan. La transcripción por API tiene costo por uso. El .env existente no se modifica automáticamente.

No publiques .env ni pegues credenciales en el código. El .env existente no se modifica automáticamente.

## Arranque

Con Docker y una instancia de MongoDB accesible desde el contenedor:

    docker compose build
    docker compose up

localhost dentro de Docker apunta al contenedor web. Para MongoDB instalado en Windows, usa mongodb://host.docker.internal:27017 o la URI de MongoDB Atlas. Compose no inicia MongoDB automáticamente. FFmpeg se instala en la imagen. No se descargan modelos de voz en el servidor.

Sin Docker, instala Python 3.11 o superior y el ejecutable FFmpeg disponible en PATH:

    pip install -r requirements.txt
    uvicorn app.main:app --host 0.0.0.0 --port 8000

Ejecuta desde bot-happy. Configura una URL HTTPS pública terminada en /webhook en Meta y suscribe el campo messages.

## Datos guardados

Colección submissions, un documento por ID de mensaje de WhatsApp (_id):

- from_number, type, whatsapp_timestamp, received_at (UTC).
- location: coordenadas y enlace de mapa para mensajes de ubicación.
- transcription: texto reconocido para mensajes de audio.
- reply o request_location, y acknowledged: respuesta y estado de envío.

Los saludos y avisos generan metadatos para controlar reintentos, pero no se guarda el cuerpo de los mensajes de texto ni archivos de foto/video. Consultas de ejemplo en MongoDB Compass: { "type": "location" } o { "transcription": { "$exists": true } }. Puedes filtrar por from_number.

El archivo de audio tiene un límite de 20 MB tanto antes como después de convertirlo. No se publica una ruta de descarga ni endpoints abiertos para enviar mensajes. Las solicitudes HTTP tienen tiempos máximos. La conversión tiene un tiempo máximo de 120 segundos y la respuesta de la API un timeout de lectura de 120 segundos. Los errores de infraestructura devuelven 503 para permitir reintentos; los mensajes ya guardados no se vuelven a transcribir en reintentos secuenciales.

## Pruebas y límites

    python -m unittest discover -s tests -v

Las pruebas unitarias usan dobles de MongoDB, Meta y la API de transcripción: no envían mensajes reales ni consumen saldo. El webhook procesa todos los mensajes de cada evento en un hilo de trabajo, pero espera la transcripción antes de responder. Se procesa un audio a la vez por proceso para limitar el uso de memoria. Para alto volumen se necesita una cola persistente con workers; entregas simultáneas del mismo audio todavía pueden repetir el trabajo de transcripción aunque el registro final sea único. Una confirmación puede repetirse si el proceso se corta justo después de enviarla.

No ejecutes app.scripts.seed_catalog para este flujo: es una herramienta antigua que borra y reemplaza el catálogo.

Referencias: [transcripción de OpenAI](https://developers.openai.com/api/docs/guides/speech-to-text), [descarga de medios de Meta](https://www.postman.com/meta/whatsapp-business-platform/request/zsq66eh/download-media).

## Render

1. Despliega el código actualizado usando el Dockerfile para instalar FFmpeg y las dependencias ligeras.
2. Conserva tus variables de WhatsApp y MongoDB y agrega OPENAI_API_KEY en Environment. OPENAI_TRANSCRIPTION_MODEL es opcional.
3. Puedes eliminar WHISPER_MODEL, WHISPER_CPU_THREADS y las demás WHISPER_*.
4. Espera a que el despliegue esté activo y envía una nueva nota de voz corta.
5. Los logs mostrarán la descarga, conversión y solicitud a la API. Un error HTTP 401 apunta a la clave o autorización; HTTP 429 puede indicar cuota, saldo o límite de solicitudes y requiere revisar la cuenta del proveedor.

Las pruebas automatizadas simulan la API. La prueba de extremo a extremo requiere una clave configurada y el servicio desplegado.
