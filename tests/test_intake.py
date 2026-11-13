from copy import deepcopy
import unittest
from unittest.mock import patch

with patch.dict("os.environ", {"MONGODB_URI": "", "PYTHON_DOTENV_DISABLED": "1"}):
    from app import intake
    from app.messaging import AudioInputError


class MemoryCollection:
    def __init__(self):
        self.documents = {}

    def find_one(self, query):
        return deepcopy(self.documents.get(query["_id"]))

    def find_one_and_update(self, query, update):
        document = self.documents.get(query["_id"])
        if document is None or document.get("acknowledged") or "response_state" in document:
            return None
        previous = deepcopy(document)
        document.update(update["$set"])
        return previous

    def update_one(self, query, update, upsert=False):
        key = query["_id"]
        if key not in self.documents and upsert:
            self.documents[key] = deepcopy(update.get("$setOnInsert", {}))
        if key in self.documents:
            self.documents[key].update(update.get("$set", {}))


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.db = MemoryCollection()
        self.patches = [
            patch.object(intake, "submissions_collection", self.db),
            patch.object(intake, "send_text"),
            patch.object(intake, "request_location"),
            patch.object(intake, "transcribe_audio", return_value="Necesito ayuda en esta dirección."),
        ]
        _, self.send, self.request_location, self.transcribe = [p.start() for p in self.patches]
        for p in self.patches:
            self.addCleanup(p.stop)

    def message(self, kind, **fields):
        return {"id": "wamid.test", "from": "593000000000", "timestamp": "123", "type": kind, **fields}

    def test_text_requests_location_without_storing_text(self):
        intake.process_message(self.message("text", text={"body": "hola"}))
        self.request_location.assert_called_once_with("593000000000")
        self.assertNotIn("text", self.db.documents["wamid.test"])

    def test_location_saved_with_sender_and_coordinates(self):
        intake.process_message(self.message("location", location={"latitude": -2.17, "longitude": -79.92, "address": "Guayaquil"}))
        saved = self.db.documents["wamid.test"]
        self.assertEqual(saved["location"]["latitude"], -2.17)
        self.assertEqual(saved["location"]["longitude"], -79.92)
        self.assertEqual(saved["location"]["address"], "Guayaquil")
        self.assertTrue(saved["acknowledged"])

    def test_invalid_coordinates_are_not_saved(self):
        for value in [91, float("nan"), float("inf")]:
            with self.assertRaises(ValueError):
                intake.location_fields({"latitude": value, "longitude": 0})

    def test_audio_saves_only_transcript_and_duplicate_does_not_transcribe(self):
        message = self.message("audio", audio={"id": "1234", "mime_type": "audio/ogg"})
        intake.process_message(message)
        intake.process_message(message)
        self.transcribe.assert_called_once_with("1234")
        self.send.assert_called_once()
        saved = self.db.documents["wamid.test"]
        self.assertEqual(saved["transcription"], "Necesito ayuda en esta dirección.")
        self.assertNotIn("audio", saved)
        self.assertNotIn("media_id", saved)

    def test_uncertain_confirmation_is_not_resent_on_late_retry(self):
        message = self.message("audio", audio={"id": "1234"})
        self.send.side_effect = RuntimeError("Meta no disponible")
        with self.assertRaises(RuntimeError):
            intake.process_message(message)
        self.assertFalse(self.db.documents["wamid.test"]["acknowledged"])
        self.send.side_effect = None
        intake.process_message(message)
        self.transcribe.assert_called_once()
        self.assertFalse(self.db.documents["wamid.test"]["acknowledged"])
        self.assertEqual(self.db.documents["wamid.test"]["response_state"], "unknown")
        self.send.assert_called_once()

    def test_concurrent_delivery_cannot_send_a_second_response(self):
        record = {"_id": "pending", "reply": "ok", "acknowledged": False}
        self.db.documents["pending"] = deepcopy(record)
        self.send.side_effect = lambda *args: intake.deliver_response("593000000000", record)
        intake.deliver_response("593000000000", record)
        self.send.assert_called_once()
        self.assertEqual(self.db.documents["pending"]["response_state"], "sent")

    def test_transcription_network_failure_does_not_record_success(self):
        self.transcribe.side_effect = RuntimeError("Modelo local no disponible")
        with self.assertRaises(RuntimeError):
            intake.process_message(self.message("audio", audio={"id": "1234"}))
        self.assertFalse(self.db.documents)
        self.send.assert_not_called()

    def test_unreadable_audio_explains_problem_without_transcript(self):
        self.transcribe.side_effect = AudioInputError("Envía otra nota de voz.")
        intake.process_message(self.message("audio", audio={"id": "1234"}))
        self.assertNotIn("transcription", self.db.documents["wamid.test"])
        self.send.assert_called_once_with("593000000000", "Envía otra nota de voz.")

    def test_images_and_videos_are_not_downloaded_or_saved(self):
        for kind in ["image", "video"]:
            with self.subTest(kind=kind):
                intake.process_message({**self.message(kind), "id": kind, kind: {"id": "1234"}})
                self.assertNotIn(kind, self.db.documents[kind])
        self.transcribe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
