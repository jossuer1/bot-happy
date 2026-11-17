import hashlib
import hmac
import json
import os
import unittest
from unittest.mock import Mock, patch

with patch.dict(os.environ, {"MONGODB_URI": "", "PYTHON_DOTENV_DISABLED": "1"}):
    from fastapi.testclient import TestClient
    from app import intake, main, workflow
from test_intake import MemoryCollection


class FlowCollection(MemoryCollection):
    def aggregate(self, pipeline):
        sender = pipeline[0]["$match"]["from_number"]
        counts = {}
        for record in self.documents.values():
            if record["from_number"] == sender:
                counts[record["type"]] = counts.get(record["type"], 0) + 1
        return [{"_id": kind, "total": count} for kind, count in counts.items()]


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.db = FlowCollection()
        self.client = TestClient(main.app)
        self.sequence = 0

    def receive(self, kind, **fields):
        self.sequence += 1
        message = {"id": f"wamid.{self.sequence}", "from": "593000000000", "timestamp": "123",
                   "type": kind, **fields}
        body = json.dumps({"object": "whatsapp_business_account", "entry": [{"changes": [
            {"value": {"messages": [message]}}]}]}).encode()
        signature = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
        response = self.client.post("/webhook", content=body, headers={"X-Hub-Signature-256": signature})
        self.assertEqual(response.status_code, 200, response.text)
        return body, signature

    def test_signed_webhook_complete_real_transport_path(self):
        response = Mock(status_code=200)
        response.json.return_value = {"messages": [{"id": "wamid.outbound"}]}
        env = {"WHATSAPP_APP_SECRET": "secret", "WHATSAPP_PHONE_NUMBER_ID": "phone",
               "WHATSAPP_TOKEN": "token", "TEST_TEMPLATE_NAME": "approved_test",
               "TEST_TEMPLATE_LANGUAGE": "es", "TEST_TEMPLATE_PARAMS": '["Cliente"]'}
        with patch.dict(os.environ, env), patch.object(intake, "submissions_collection", self.db), \
             patch.object(intake, "transcribe_audio", return_value="Necesito ayuda") as transcribe, \
             patch("app.messaging.requests.post", return_value=response) as post:
            self.receive("text", text={"body": "hola"})
            self.assertEqual(post.call_args.kwargs["json"]["interactive"]["type"], "button")
            self.receive("interactive", interactive={"type": "button_reply", "button_reply": {"id": "tipos", "title": "ignorar"}})
            self.assertEqual(post.call_args.kwargs["json"]["interactive"]["type"], "list")
            self.receive("interactive", interactive={"type": "list_reply", "list_reply": {"id": "ubicacion", "title": "ignorar"}})
            self.assertEqual(post.call_args.kwargs["json"]["interactive"]["action"]["name"], "send_location")
            self.receive("location", location={"latitude": -2.17, "longitude": -79.92})
            self.assertIn("Paso 2", post.call_args.kwargs["json"]["text"]["body"])
            self.receive("audio", audio={"id": "123"})
            self.assertIn("Necesito ayuda", post.call_args.kwargs["json"]["text"]["body"])
            for kind in ("image", "video", "document"):
                self.receive(kind, **{kind: {"id": "456", "mime_type": "test/type"}})
                self.assertEqual(post.call_args.kwargs["json"][kind]["id"], "456")
            self.receive("text", text={"body": "enlace"})
            self.assertEqual(post.call_args.kwargs["json"]["interactive"]["type"], "cta_url")
            self.receive("text", text={"body": "mapa"})
            self.assertEqual(post.call_args.kwargs["json"]["type"], "location")
            self.receive("text", text={"body": "plantilla"})
            self.assertEqual(post.call_args.kwargs["json"]["template"]["name"], "approved_test")
            body, signature = self.receive("text", text={"body": "resumen"})
            self.assertIn("image: 1", post.call_args.kwargs["json"]["text"]["body"])
            calls = post.call_count
            self.client.post("/webhook", content=body, headers={"X-Hub-Signature-256": signature})
            self.assertEqual(post.call_count, calls)
            transcribe.assert_called_once_with("123")
            self.assertEqual(calls, 12)
            self.assertTrue(all(row["response_state"] == "sent" for row in self.db.documents.values()))
            self.assertTrue(all("whatsapp_response" in row for row in self.db.documents.values()))

    def test_summary_is_scoped_to_sender(self):
        self.db.documents = {"other": {"from_number": "other", "type": "image"}}
        self.assertNotIn("image:", workflow.route("resumen", "me", self.db)["text"]["body"])

    def test_template_missing_or_invalid_configuration_is_explained(self):
        with patch.dict(os.environ, {"TEST_TEMPLATE_NAME": ""}):
            self.assertIn("TEST_TEMPLATE_NAME", workflow.route("plantilla", "me", self.db)["text"]["body"])
        with patch.dict(os.environ, {"TEST_TEMPLATE_NAME": "test", "TEST_TEMPLATE_PARAMS": '{}'}):
            self.assertIn("TEST_TEMPLATE_PARAMS", workflow.route("plantilla", "me", self.db)["text"]["body"])

    def test_template_without_parameters_omits_components(self):
        with patch.dict(os.environ, {"TEST_TEMPLATE_NAME": "test", "TEST_TEMPLATE_PARAMS": '[]'}):
            self.assertNotIn("components", workflow.route("plantilla", "me", self.db)["template"])

    def test_unsupported_interactive_reply_returns_menu(self):
        choice = workflow.selection({"type": "interactive", "interactive": {"type": "unknown"}})
        self.assertEqual(workflow.route(choice, "me", self.db)["interactive"]["type"], "button")

    def test_simulated_web_routes_are_removed(self):
        self.assertEqual(self.client.get("/demo").status_code, 404)
