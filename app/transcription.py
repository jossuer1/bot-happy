import logging
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from threading import Lock

import requests

from app.messaging import AudioInputError, download_audio

MAX_AUDIO_BYTES = 20 * 1024 * 1024
logger = logging.getLogger("uvicorn.error")
# Limita conversiones y solicitudes simultáneas en servicios con poca RAM.
_audio_lock = Lock()


def transcribe_audio(media_id: str):
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise AudioInputError("La transcripción aún no está configurada. Contacta al administrador para habilitarla.")
    with _audio_lock, TemporaryDirectory(prefix="bot-happy-audio-") as directory:
        source = Path(directory) / "source.audio"
        converted = Path(directory) / "voice.mp3"
        logger.info("Descargando audio de WhatsApp")
        download_audio(media_id, source, MAX_AUDIO_BYTES)
        logger.info("Convirtiendo audio para transcripción")
        try:
            subprocess.run(
                [os.getenv("FFMPEG_BINARY", "ffmpeg"), "-nostdin", "-v", "error", "-y",
                 "-threads", "1", "-protocol_whitelist", "file,pipe", "-i", str(source),
                 "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", "-threads", "1",
                 "-fs", str(MAX_AUDIO_BYTES + 1), str(converted)],
                check=True, capture_output=True, timeout=120,
            )
        except subprocess.CalledProcessError as error:
            raise AudioInputError("No pude leer ese audio. Envía otra nota de voz.") from error
        if not converted.exists() or converted.stat().st_size == 0:
            raise AudioInputError("El audio está vacío. Envía otra nota de voz.")
        if converted.stat().st_size > MAX_AUDIO_BYTES:
            raise AudioInputError("El audio es demasiado largo. Envía una nota de voz más corta.")
        logger.info("Solicitando transcripción a la API")
        with converted.open("rb") as audio:
            response = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {key}"},
                data={
                    "model": os.getenv("GROQ_TRANSCRIPTION_MODEL", "whisper-large-v3-turbo"),
                    "language": "es",
                    "response_format": "json",
                },
                files={"file": ("voice.mp3", audio, "audio/mpeg")},
                timeout=(10, 120),
            )
        if response.status_code >= 400:
            logger.error("La API de transcripción respondió HTTP %s", response.status_code)
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            detail = payload.get("error", {}) if isinstance(payload, dict) else {}
            if not isinstance(detail, dict):
                detail = {}
            code = detail.get("code")
            # Registrar solo códigos conocidos, sin cuerpos de respuesta ni claves.
            known_codes = {"rate_limit_exceeded", "invalid_api_key", "model_not_found"}
            if isinstance(code, str) and code in known_codes:
                logger.error("Código de la API de transcripción: %s", code)
            if response.status_code in {401, 403}:
                logger.error("Revisar GROQ_API_KEY y los permisos del modelo en Groq")
                raise AudioInputError(
                    "El servicio de transcripción está temporalmente inhabilitado. "
                    "Contacta al administrador y vuelve a enviar el audio cuando esté habilitado."
                )
        response.raise_for_status()
        text = response.json().get("text", "").strip()
        if not text:
            raise AudioInputError("No pude identificar palabras en el audio. Envía otra nota de voz más clara.")
        logger.info("Transcripción recibida; eliminando audio temporal")
        return text
