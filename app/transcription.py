import os
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

from app.messaging import AudioInputError, download_audio

MAX_AUDIO_BYTES = 20 * 1024 * 1024
# Un modelo por proceso y una transcripción a la vez para limitar memoria en CPU.
_transcription_lock = Lock()


@lru_cache(maxsize=1)
def get_model():
    from faster_whisper import WhisperModel

    return WhisperModel(
        os.getenv("WHISPER_MODEL", "small"),
        device="cpu",
        compute_type="int8",
        download_root=os.getenv("WHISPER_DOWNLOAD_ROOT", "models"),
        cpu_threads=int(os.getenv("WHISPER_CPU_THREADS", "4")),
        local_files_only=os.getenv("WHISPER_LOCAL_FILES_ONLY", "false").lower() == "true",
    )


def decode_recording(path):
    from av.error import FFmpegError
    from faster_whisper.audio import decode_audio

    try:
        return decode_audio(str(path), sampling_rate=16000)
    except (FFmpegError, ValueError, EOFError) as error:
        raise AudioInputError("No pude leer ese audio. Envía otra nota de voz.") from error


def transcribe_audio(media_id: str):
    # Se borran los archivos temporales al terminar y ante cualquier error.
    with TemporaryDirectory(prefix="bot-happy-audio-") as directory:
        source = Path(directory) / "source.audio"
        download_audio(media_id, source, MAX_AUDIO_BYTES)
        with _transcription_lock:
            audio = decode_recording(source)
            max_seconds = int(os.getenv("WHISPER_MAX_AUDIO_SECONDS", "300"))
            if len(audio) > max_seconds * 16000:
                raise AudioInputError(f"El audio es demasiado largo. Envía uno de hasta {max_seconds} segundos.")
            language = os.getenv("WHISPER_LANGUAGE", "es")
            segments, _ = get_model().transcribe(
                audio,
                language=None if language == "auto" else language,
                beam_size=5,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            # faster-whisper genera segmentos de forma diferida: consumirlos antes
            # de liberar el bloqueo y de eliminar el archivo temporal.
            text = " ".join(segment.text.strip() for segment in segments).strip()
        if not text:
            raise AudioInputError("No pude identificar palabras en el audio. Envía otra nota de voz más clara.")
        return text
