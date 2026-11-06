from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
import wave

from app import transcription
from app.messaging import AudioInputError


class TranscriptionTests(unittest.TestCase):
    def setUp(self):
        self.paths = []
        self.model = Mock()
        self.model.transcribe.return_value = (
            iter([SimpleNamespace(text=" Necesito ayuda. "), SimpleNamespace(text=" Estoy en casa. ")]), None
        )
        self.download_patch = patch.object(transcription, "download_audio", side_effect=self.download)
        self.decode_patch = patch.object(transcription, "decode_recording", return_value=[0.0] * 160)
        self.model_patch = patch.object(transcription, "get_model", return_value=self.model)
        for item in [self.download_patch, self.decode_patch, self.model_patch]:
            item.start()
            self.addCleanup(item.stop)

    def download(self, media_id, destination, maximum):
        self.paths.append(destination)
        destination.write_bytes(b"fake ogg")

    def test_transcribes_locally_and_removes_temporary_audio(self):
        with patch.dict("os.environ", {"WHISPER_LANGUAGE": "es"}):
            text = transcription.transcribe_audio("1234")
        self.assertEqual(text, "Necesito ayuda. Estoy en casa.")
        self.assertEqual(self.model.transcribe.call_args.kwargs["language"], "es")
        self.assertTrue(all(not path.exists() for path in self.paths))

    def test_lazy_segments_consumed_before_deleting_audio(self):
        def segments():
            self.assertTrue(self.paths[0].exists())
            yield SimpleNamespace(text="Texto local")
        self.model.transcribe.return_value = (segments(), None)
        self.assertEqual(transcription.transcribe_audio("1234"), "Texto local")
        self.assertFalse(self.paths[0].exists())

    def test_model_failure_also_removes_audio(self):
        self.model.transcribe.side_effect = RuntimeError("Modelo no disponible")
        with self.assertRaises(RuntimeError):
            transcription.transcribe_audio("1234")
        self.assertTrue(all(not path.exists() for path in self.paths))

    def test_invalid_audio_is_cleaned_up(self):
        transcription.decode_recording.side_effect = AudioInputError("Audio inválido")
        with self.assertRaises(AudioInputError):
            transcription.transcribe_audio("1234")
        self.model.transcribe.assert_not_called()
        self.assertTrue(all(not path.exists() for path in self.paths))

    def test_silence_does_not_produce_transcript(self):
        self.model.transcribe.return_value = (iter([]), None)
        with self.assertRaises(AudioInputError):
            transcription.transcribe_audio("1234")
        self.assertFalse(self.paths[0].exists())

    def test_long_audio_is_rejected_before_loading_model(self):
        transcription.decode_recording.return_value = [0] * 16001
        with patch.dict("os.environ", {"WHISPER_MAX_AUDIO_SECONDS": "1"}):
            with self.assertRaises(AudioInputError):
                transcription.transcribe_audio("1234")
        transcription.get_model.assert_not_called()
        self.assertFalse(self.paths[0].exists())

    def test_language_auto_is_supported(self):
        with patch.dict("os.environ", {"WHISPER_LANGUAGE": "auto"}):
            transcription.transcribe_audio("1234")
        self.assertIsNone(self.model.transcribe.call_args.kwargs["language"])


class ModelConfigurationTests(unittest.TestCase):
    def tearDown(self):
        transcription.get_model.cache_clear()

    def test_cpu_int8_model_is_reused(self):
        with patch.dict("os.environ", {"WHISPER_MODEL": "small", "WHISPER_CPU_THREADS": "2", "WHISPER_LOCAL_FILES_ONLY": "true", "WHISPER_DOWNLOAD_ROOT": "test-model-cache"}), patch("faster_whisper.WhisperModel") as constructor:
            transcription.get_model.cache_clear()
            first = transcription.get_model()
            second = transcription.get_model()
        self.assertIs(first, second)
        constructor.assert_called_once_with("small", device="cpu", compute_type="int8", download_root="test-model-cache", cpu_threads=2, local_files_only=True)


class AudioDecodingTests(unittest.TestCase):
    def test_real_decoder_reads_wav_without_external_ffmpeg(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "voice.audio"
            with wave.open(str(path), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(16000)
                output.writeframes(b"\x00\x00" * 1600)
            audio = transcription.decode_recording(path)
        self.assertEqual(len(audio), 1600)

    def test_real_decoder_reports_corrupt_recording(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "voice.audio"
            path.write_bytes(b"not a recording")
            with self.assertRaises(AudioInputError):
                transcription.decode_recording(path)
