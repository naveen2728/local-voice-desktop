import unittest

from voiceflow_app.overlay import BLDS, CX, CY, ORB_H, ORB_W, OUTER_RING_RADIUS, Overlay, PULSE_PADDING, R


class FakePanel:
    def __init__(self):
        self.events = []

    def winfo_exists(self):
        return True

    def attributes(self, *args):
        self.events.append(("attributes", args))

    def geometry(self, value):
        self.events.append(("geometry", value))

    def deiconify(self):
        self.events.append(("deiconify",))

    def lift(self):
        self.events.append(("lift",))

    def focus_set(self):
        self.events.append(("focus_set",))


class OverlayGeometryTests(unittest.TestCase):
    def test_orb_and_pulse_have_canvas_padding(self):
        self.assertEqual(OUTER_RING_RADIUS, R + PULSE_PADDING)
        self.assertGreaterEqual(CX - OUTER_RING_RADIUS, 0)
        self.assertLessEqual(CX + OUTER_RING_RADIUS, ORB_W)
        self.assertGreaterEqual(CY - OUTER_RING_RADIUS, 0)
        self.assertLessEqual(CY + OUTER_RING_RADIUS, ORB_H)

    def test_waveform_bars_stay_inside_inner_circle_width(self):
        inner_radius = R - 8
        for bar in BLDS:
            self.assertGreaterEqual(bar["dx"], -inner_radius)
            self.assertLessEqual(bar["dx"] + bar["w"], inner_radius)

    def test_panel_is_fully_configured_before_becoming_visible(self):
        overlay = Overlay.__new__(Overlay)
        overlay._panel_geometry = lambda _panel: (760, 720, 100, 40)
        panel = FakePanel()

        overlay._present_panel(panel)

        self.assertEqual(
            panel.events,
            [
                ("attributes", ("-topmost", True)),
                ("geometry", "760x720+100+40"),
                ("deiconify",),
                ("lift",),
                ("focus_set",),
            ],
        )


if __name__ == "__main__":
    unittest.main()
