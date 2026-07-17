from django.test import SimpleTestCase, override_settings

from config.settings import base


class ChatTurnIdempotencyFlagTest(SimpleTestCase):
    def test_rollout_flag_defaults_off(self):
        self.assertFalse(base.CHAT_TURN_IDEMPOTENCY)

    @override_settings(CHAT_TURN_IDEMPOTENCY=True)
    def test_rollout_flag_can_be_enabled(self):
        from django.conf import settings
        self.assertTrue(settings.CHAT_TURN_IDEMPOTENCY)
