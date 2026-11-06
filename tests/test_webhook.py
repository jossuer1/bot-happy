import hashlib
import hmac
import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

with patch.dict("os.environ", {"MONGODB_URI": "", "PYTHON_DOTENV_DISABLED": "1"}):
    from app import main


class WebhookTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict("os.environ", {"WHATSAPP_APP_SECRET": "test-secret"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def request(self, messages=None, signature=True, statuses=False):
        value = {"statuses": []} if statuses else {"messages": messages or []}
        payload = {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": value}]}]}
        body = json.dumps(payload).encode()
        signed = "sha256=" + hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
        headers = [(b"x-hub-signature-256", signed.encode())] if signature else []

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        return Request({"type": "http", "method": "POST", "path": "/webhook", "headers": headers}, receive)

    async def test_all_messages_are_processed(self):
        messages = [{"id": "one"}, {"id": "two"}]
        with patch.object(main, "process_message") as process:
            result = await main.receive_webhook(self.request(messages))
        self.assertEqual(result["status"], "success")
        self.assertEqual([call.args[0] for call in process.call_args_list], messages)

    async def test_unsigned_request_is_rejected(self):
        with patch.object(main, "process_message") as process:
            with self.assertRaises(HTTPException) as error:
                await main.receive_webhook(self.request(signature=False))
        self.assertEqual(error.exception.status_code, 403)
        process.assert_not_called()

    async def test_failure_returns_retryable_status_and_other_messages_continue(self):
        with patch.object(main, "process_message", side_effect=[RuntimeError("failure"), None]) as process:
            with self.assertRaises(HTTPException) as error:
                await main.receive_webhook(self.request([{"id": "one"}, {"id": "two"}]))
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(process.call_count, 2)

    async def test_status_notification_is_ignored(self):
        with patch.object(main, "process_message") as process:
            await main.receive_webhook(self.request(statuses=True))
        process.assert_not_called()

    def test_verification_requires_configured_token(self):
        with patch.dict("os.environ", {"VERIFY_TOKEN": ""}):
            with self.assertRaises(HTTPException):
                main.verify_webhook("subscribe", "challenge", None)

    def test_valid_verification_returns_plain_challenge(self):
        with patch.dict("os.environ", {"VERIFY_TOKEN": "test"}):
            result = main.verify_webhook("subscribe", "challenge", "test")
        self.assertEqual(result.body, b"challenge")
