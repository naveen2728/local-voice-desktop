import unittest

from voiceflow_app.settings_window import sensitivity_label


class SettingsWindowTests(unittest.TestCase):
    def test_uses_nearest_sensitivity_label(self):
        self.assertEqual(sensitivity_label(0.0000001), "High - quieter speech")
        self.assertEqual(sensitivity_label(0.000001), "Normal")
        self.assertEqual(sensitivity_label(0.0003), "Low - noisy rooms")


if __name__ == "__main__":
    unittest.main()
