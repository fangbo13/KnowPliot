from django.conf import settings
from django.test import SimpleTestCase


class DeepAnswerModeFlagTest(SimpleTestCase):
    def test_deep_answer_mode_is_default_off(self):
        self.assertFalse(settings.DEEP_ANSWER_MODE)
