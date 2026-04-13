"""Quick async tests for smart-tier async client wrappers (no live API calls).

Run: PYTHONPATH=. python3 -m unittest backend.test_smart_async_clients -v
"""

import asyncio
import inspect
import unittest
from unittest.mock import patch


class TestSmartAsyncClients(unittest.TestCase):
    def test_call_gemini_smart_async_delegates_to_sync(self):
        fake = {
            "executor_text": "e",
            "advisor_text": "advisor-out",
            "executor_tokens": 1,
            "advisor_tokens": 2,
        }

        async def _run():
            with patch(
                "backend.models.google_client.call_gemini_smart",
                return_value=fake,
            ) as m:
                from backend.models.google_client import call_gemini_smart_async

                r = await call_gemini_smart_async([{"role": "user", "content": "hi"}], "sys")
                self.assertEqual(r["advisor_text"], "advisor-out")
                m.assert_called_once_with([{"role": "user", "content": "hi"}], system="sys")

        asyncio.run(_run())

    def test_call_gpt_smart_async_delegates_to_sync(self):
        fake = {
            "executor_text": "e",
            "advisor_text": "gpt-adv",
            "executor_tokens": 3,
            "advisor_tokens": 4,
        }

        async def _run():
            with patch("backend.models.openai_client.call_gpt_smart", return_value=fake) as m:
                from backend.models.openai_client import call_gpt_smart_async

                r = await call_gpt_smart_async([], None)
                self.assertEqual(r["advisor_text"], "gpt-adv")
                m.assert_called_once_with([], system=None)

        asyncio.run(_run())

    def test_call_claude_smart_async_delegates_to_sync(self):
        fake = {
            "executor_text": "e",
            "advisor_text": "claude-adv",
            "executor_tokens": 5,
            "advisor_tokens": 6,
        }

        async def _run():
            with patch("backend.models.anthropic_client.call_claude_smart", return_value=fake) as m:
                from backend.models.anthropic_client import call_claude_smart_async

                r = await call_claude_smart_async([{"role": "user", "content": "x"}], "s")
                self.assertEqual(r["advisor_text"], "claude-adv")
                m.assert_called_once_with([{"role": "user", "content": "x"}], system="s")

        asyncio.run(_run())

    def test_main_call_with_retry_async_is_coroutine(self):
        from backend.main import _call_with_retry_async

        self.assertTrue(inspect.iscoroutinefunction(_call_with_retry_async))


if __name__ == "__main__":
    unittest.main()
