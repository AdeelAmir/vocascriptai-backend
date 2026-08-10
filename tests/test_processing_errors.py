import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import uuid

from app.services.by_youtube import extract_video_id
from app.services.processing_errors import (
    ERROR_MESSAGES,
    ProcessingError,
    classify_processing_exception,
)
from app.services.pricing_entitlements import PricingEntitlementService


class ProcessingErrorTests(unittest.TestCase):
    def test_all_public_error_codes_have_messages(self) -> None:
        for code, message in ERROR_MESSAGES.items():
            error = ProcessingError(code)
            self.assertEqual(error.public_message, message)
            self.assertEqual(error.public_payload()["code"], code)

    def test_provider_error_classification(self) -> None:
        self.assertEqual(classify_processing_exception(RuntimeError("no speech detected")).code, "NO_AUDIO_OR_SPEECH")
        self.assertEqual(classify_processing_exception(RuntimeError("audio quality too poor")).code, "POOR_AUDIO_QUALITY")
        self.assertEqual(classify_processing_exception(RuntimeError("unsupported codec")).code, "UNSUPPORTED_OR_CORRUPTED_MEDIA")
        self.assertEqual(classify_processing_exception(TimeoutError("request timed out")).code, "PROCESSING_TIMEOUT")

    def test_youtube_id_validation(self) -> None:
        expected = "dQw4w9WgXcQ"
        self.assertEqual(extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), expected)
        self.assertEqual(extract_video_id("youtu.be/dQw4w9WgXcQ"), expected)
        self.assertEqual(extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ"), expected)

        with self.assertRaises(ProcessingError) as context:
            extract_video_id("https://youtube.com/watch?v=short-id")
        self.assertEqual(context.exception.code, "INVALID_YOUTUBE_URL")

    def test_guest_usage_is_not_transferred_by_ip_only(self) -> None:
        db = AsyncMock()
        user = SimpleNamespace(role=2, id=uuid.uuid4())

        import asyncio

        asyncio.run(
            PricingEntitlementService.transfer_guest_usage_to_user(
                None,
                "203.0.113.10",
                user,
                db,
            )
        )

        db.execute.assert_not_awaited()

    def test_guest_transfer_requires_an_unclaimed_visitor_record(self) -> None:
        db = AsyncMock()
        query_result = MagicMock()
        query_result.scalars.return_value.all.return_value = []
        db.execute.return_value = query_result
        user = SimpleNamespace(role=2, id=uuid.uuid4())
        visitor_id = uuid.uuid4()

        import asyncio

        asyncio.run(
            PricingEntitlementService.transfer_guest_usage_to_user(
                visitor_id,
                "203.0.113.10",
                user,
                db,
            )
        )

        statement = db.execute.await_args.args[0]
        where_sql = str(statement.whereclause)
        self.assertIn("guest_visitors.user_id IS NULL", where_sql)
        self.assertNotIn("guest_visitors.ip_address", where_sql)


if __name__ == "__main__":
    unittest.main()
