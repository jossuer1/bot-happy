import json
import unittest
from unittest.mock import patch

from app import tracing


class TracingTests(unittest.TestCase):
    def test_json_payload_and_correlation_are_logged(self):
        token = tracing.trace_id.set("trace-test")
        try:
            with patch.dict("os.environ", {"LOG_JSON_PAYLOADS": "true"}), patch.object(tracing.logger, "info") as log:
                tracing.event("webhook.received", payload={"text": "hola"})
            record = json.loads(log.call_args.args[0])
            self.assertEqual(record["trace_id"], "trace-test")
            self.assertEqual(record["payload"], {"text": "hola"})
        finally:
            tracing.trace_id.reset(token)

    def test_payload_can_be_disabled_without_losing_events(self):
        with patch.dict("os.environ", {"LOG_JSON_PAYLOADS": "false"}), patch.object(tracing.logger, "info") as log:
            tracing.event("whatsapp.request", payload={"to": "593000000000"})
        record = json.loads(log.call_args.args[0])
        self.assertNotIn("payload", record)
        self.assertEqual(record["event"], "whatsapp.request")
