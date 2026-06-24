import unittest

from voiceflow_app.overlay import looks_like_screen_question, scaled_crop_box


class OverlayCropTests(unittest.TestCase):
    def test_scaled_crop_box_maps_preview_selection_to_original_image(self):
        self.assertEqual(
            scaled_crop_box(20, 30, 120, 90, 0.5, 400, 300),
            (40, 60, 240, 180),
        )

    def test_scaled_crop_box_rejects_tiny_selection(self):
        self.assertIsNone(scaled_crop_box(10, 10, 12, 12, 1.0, 400, 300))

    def test_detects_short_screen_follow_up_questions(self):
        self.assertTrue(looks_like_screen_question("what is it"))
        self.assertTrue(looks_like_screen_question("explain this"))
        self.assertTrue(looks_like_screen_question("what is on this screen?"))
        self.assertFalse(looks_like_screen_question("write an email to Rahul"))

    def test_regular_follow_up_can_use_active_screen_context(self):
        self.assertFalse(looks_like_screen_question("what do you think"))


if __name__ == "__main__":
    unittest.main()
