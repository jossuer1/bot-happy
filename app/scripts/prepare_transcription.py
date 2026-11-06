"""Descarga y comprueba el modelo local sin recibir audios de WhatsApp."""
from dotenv import load_dotenv

load_dotenv()

from app.transcription import get_model

if __name__ == "__main__":
    get_model()
    print("Modelo de transcripción local listo.")
