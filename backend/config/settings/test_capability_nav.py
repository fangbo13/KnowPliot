# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Pure environment parsing contracts for the capability navigation flag."""

from django.test import SimpleTestCase

try:
    from config.settings.parsing import env_bool
except ImportError:  # RED: parsing helper is introduced with CAPABILITY_NAV.
    env_bool = None


class CapabilityNavigationFlagTest(SimpleTestCase):
    def test_flag_defaults_false_when_environment_value_is_absent(self):
        self.assertIsNotNone(env_bool)
        self.assertFalse(env_bool("CAPABILITY_NAV", default=False, environ={}))

    def test_flag_accepts_only_explicit_true_spellings(self):
        for value in ("1", "true", "TRUE", " yes ", "on"):
            with self.subTest(value=value):
                self.assertTrue(
                    env_bool("CAPABILITY_NAV", default=False, environ={"CAPABILITY_NAV": value})
                )
        for value in ("0", "false", "no", "off", "unexpected", ""):
            with self.subTest(value=value):
                self.assertFalse(
                    env_bool("CAPABILITY_NAV", default=True, environ={"CAPABILITY_NAV": value})
                )
