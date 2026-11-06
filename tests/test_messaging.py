from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from app import messaging


class MediaTests(unittest.TestCase):
    def metadata(self, **fields):
        response = Mock()
        response.json.return_value = {"url": "https://lookaside.fbsbx.com/media", **fields}
        return response

    def test_location_request_uses_whatsapp_location_button(self):
        with patch.object(messaging, "send_payload") as send:
            messaging.request_location("593000000000")
        payload = send.call_args.args[1]
        self.assertEqual(payload["interactive"]["action"]["name"], "send_location")
        self.assertEqual(payload["interactive"]["type"], "location_request_message")

    def test_download_rejects_oversized_audio_before_download(self):
        with patch.object(messaging, "auth_headers", return_value={}), patch.object(messaging.requests, "get", return_value=self.metadata(file_size=100)) as get:
            with self.assertRaises(messaging.AudioInputError):
                messaging.download_audio("123", Path("unused.audio"), 10)
        self.assertEqual(get.call_count, 1)

    def test_download_rejects_untrusted_url_without_forwarding_token(self):
        with patch.object(messaging, "auth_headers", return_value={}), patch.object(messaging.requests, "get", return_value=self.metadata(url="https://example.com/audio")) as get:
            with self.assertRaises(ValueError):
                messaging.download_audio("123", Path("unused.audio"), 10)
        self.assertEqual(get.call_count, 1)

    def test_streaming_enforces_size_even_without_metadata_size(self):
        stream = Mock()
        stream.status_code = 200
        stream.iter_content.return_value = [b"123456", b"789012"]
        response = Mock()
        response.__enter__ = Mock(return_value=stream)
        response.__exit__ = Mock(return_value=False)
        with TemporaryDirectory() as directory, patch.object(messaging, "auth_headers", return_value={}), patch.object(messaging.requests, "get", side_effect=[self.metadata(), response]):
            with self.assertRaises(messaging.AudioInputError):
                messaging.download_audio("123", Path(directory) / "audio", 10)
