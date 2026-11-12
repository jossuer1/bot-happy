from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch

from app import transcription
from app.messaging import AudioInputError


class TranscriptionTests(unittest.TestCase):
    def setUp(self):
        self.paths = []
        self.response = Mock(status_code=200)
        self.response.json.return_value = {"text": " Necesito ayuda. "}
        self.patches = [
            patch.dict("os.environ", {"OPENAI_API_KEY": "test-key", "OPENAI_TRANSCRIPTION_MODEL": "test-model"}),
            patch.object(transcription, "download_audio", side_effect=self.download),
            patch.object(transcription.subprocess, "run", side_effect=self.convert),
            patch.object(transcription.requests, "post", return_value=self.response),
        ]
        _, self.download_mock, self.convert_mock, self.post = [item.start() for item in self.patches]
        for item in self.patches:
            self.addCleanup(item.stop)

    def download(self, media_id, destination, maximum):
        self.paths.append(destination)
        destination.write_bytes(b"fake ogg")

    def convert(self, args, **kwargs):
        destination = Path(args[-1])
        self.paths.append(destination)
        destination.write_bytes(b"fake mp3")

    def test_transcribes_via_api_and_removes_temporary_audio(self):
        self.assertEqual(transcription.transcribe_audio("123"), "Necesito ayuda.")
        self.assertEqual(self.post.call_args.args[0], "https://api.openai.com/v1/audio/transcriptions")
        self.assertEqual(self.post.call_args.kwargs["data"], {"model": "test-model"})
        self.assertEqual(self.post.call_args.kwargs["headers"]["Authorization"], "Bearer test-key")
        self.assertTrue(all(not path.exists() for path in self.paths))

    def test_conversion_failure_cleans_audio_without_calling_api(self):
        self.convert_mock.side_effect = subprocess.CalledProcessError(1, "ffmpeg")
        with self.assertRaises(AudioInputError):
            transcription.transcribe_audio("123")
        self.post.assert_not_called()
        self.assertTrue(all(not path.exists() for path in self.paths))

    def test_api_failure_cleans_audio_and_remains_retryable(self):
        self.response.status_code = 429
        self.response.raise_for_status.side_effect = RuntimeError("rate limit")
        with self.assertRaises(RuntimeError):
            transcription.transcribe_audio("123")
        self.assertTrue(all(not path.exists() for path in self.paths))

    def test_timeout_also_cleans_audio(self):
        self.post.side_effect = transcription.requests.Timeout()
        with self.assertRaises(transcription.requests.Timeout):
            transcription.transcribe_audio("123")
        self.assertTrue(all(not path.exists() for path in self.paths))

    def test_missing_key_does_not_download_or_call_api(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            with self.assertRaises(AudioInputError):
                transcription.transcribe_audio("123")
        self.download_mock.assert_not_called()
        self.post.assert_not_called()

    def test_empty_transcription_is_reported(self):
        self.response.json.return_value = {"text": "  "}
        with self.assertRaises(AudioInputError):
            transcription.transcribe_audio("123")
        self.assertTrue(all(not path.exists() for path in self.paths))

    def test_empty_conversion_does_not_call_api(self):
        def empty(args, **kwargs):
            Path(args[-1]).touch()
        self.convert_mock.side_effect = empty
        with self.assertRaises(AudioInputError):
            transcription.transcribe_audio("123")
        self.post.assert_not_called()

    def test_download_failure_does_not_call_api(self):
        self.download_mock.side_effect = RuntimeError("Meta unavailable")
        with self.assertRaises(RuntimeError):
            transcription.transcribe_audio("123")
        self.post.assert_not_called()
