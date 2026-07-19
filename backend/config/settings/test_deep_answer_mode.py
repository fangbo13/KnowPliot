from django.conf import settings
from django.test import SimpleTestCase


class DeepAnswerModeFlagTest(SimpleTestCase):
    def test_model_and_thinking_rollouts_are_default_off(self):
        self.assertFalse(settings.DEEP_ANSWER_MODE)
        self.assertFalse(settings.THINKING_MODE)

    def test_legacy_chat_aliases_share_one_runtime_value(self):
        self.assertEqual(settings.QWEN_CHAT_MODEL, settings.RAG_LLM_MODEL)
