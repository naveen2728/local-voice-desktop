import unittest
from unittest.mock import patch

from pynput import keyboard as kb
from pynput import mouse as ms

from voiceflow_app.config import AppSettings
from voiceflow_app.hotkeys import HotkeyListener
from voiceflow_app.state import RuntimeState, STATE_RECORDING


class HotkeyTests(unittest.TestCase):
    def setUp(self):
        self.state = RuntimeState(AppSettings())
        self.started_modes = []
        self.stop_calls = 0
        self.cancel_calls = 0
        self.close_calls = 0
        self.voice_chat_active = False
        self.voice_chat_start_calls = 0
        self.voice_chat_stop_calls = 0
        self.log_errors = []

        def start_recording(mode):
            self.started_modes.append(mode)
            self.state.recording_mode = mode
            self.state.recording_state = STATE_RECORDING

        def stop_and_process():
            self.stop_calls += 1

        def cancel_recording():
            self.cancel_calls += 1

        def close_app():
            self.close_calls += 1

        def start_voice_chat():
            self.voice_chat_start_calls += 1
            self.voice_chat_active = True

        def stop_voice_chat():
            self.voice_chat_stop_calls += 1
            self.voice_chat_active = False

        def is_voice_chat_active():
            return self.voice_chat_active

        def log_error(message, exc=None):
            self.log_errors.append((message, exc))

        with patch("voiceflow_app.hotkeys.kb.Listener"), patch("voiceflow_app.hotkeys.MouseSideButtonHook"):
            self.listener = HotkeyListener(
                self.state,
                start_recording,
                stop_and_process,
                cancel_recording,
                close_app,
                start_voice_chat,
                stop_voice_chat,
                is_voice_chat_active,
                log_error,
            )

    def test_shift_alone_does_not_start_command(self):
        self.listener.on_press(kb.Key.shift)
        self.listener.on_release(kb.Key.shift)
        self.assertEqual(self.started_modes, [])

    def test_ctrl_shift_space_starts_command(self):
        with patch("voiceflow_app.hotkeys.time.monotonic", return_value=10.0):
            self.listener.on_press(kb.Key.ctrl)
            self.listener.on_press(kb.Key.shift)
            self.listener.on_press(kb.Key.space)
        self.assertEqual(self.started_modes, ["command"])

    def test_ctrl_space_starts_dictation(self):
        with patch("voiceflow_app.hotkeys.time.monotonic", return_value=10.0):
            self.listener.on_press(kb.Key.ctrl)
            self.listener.on_press(kb.Key.space)
        self.assertEqual(self.started_modes, ["dictation"])

    def test_key_repeat_does_not_trigger_twice(self):
        with patch("voiceflow_app.hotkeys.time.monotonic", return_value=10.0):
            self.listener.on_press(kb.Key.ctrl)
            self.listener.on_press(kb.Key.space)
            self.listener.on_press(kb.Key.space)
        self.assertEqual(self.started_modes, ["dictation"])

    def test_release_stops_dictation(self):
        self.listener.on_press(kb.Key.ctrl)
        self.listener.on_press(kb.Key.space)
        self.listener.on_release(kb.Key.space)
        self.assertEqual(self.started_modes, ["dictation"])
        self.assertEqual(self.stop_calls, 1)

    def test_command_chord_stops_when_shift_is_released_first(self):
        self.listener.on_press(kb.Key.ctrl)
        self.listener.on_press(kb.Key.shift)
        self.listener.on_press(kb.Key.space)
        self.listener.on_release(kb.Key.shift)
        self.assertEqual(self.started_modes, ["command"])
        self.assertEqual(self.stop_calls, 1)

    def test_backspace_cancels_recording(self):
        self.state.recording_state = STATE_RECORDING
        self.listener.on_press(kb.Key.backspace)
        self.assertEqual(self.cancel_calls, 1)
        self.assertEqual(self.stop_calls, 0)

    def test_single_escape_does_not_close_app(self):
        with patch("voiceflow_app.hotkeys.time.monotonic", return_value=10.0):
            self.listener.on_press(kb.Key.esc)
        self.listener.on_release(kb.Key.esc)
        self.assertEqual(self.close_calls, 0)

    def test_double_escape_closes_app(self):
        with patch("voiceflow_app.hotkeys.time.monotonic", side_effect=[10.0, 10.5]):
            self.listener.on_press(kb.Key.esc)
            self.listener.on_release(kb.Key.esc)
            self.listener.on_press(kb.Key.esc)
        self.assertEqual(self.close_calls, 1)

    def test_holding_escape_does_not_close_app(self):
        with patch("voiceflow_app.hotkeys.time.monotonic", return_value=10.0):
            self.listener.on_press(kb.Key.esc)
            self.listener.on_press(kb.Key.esc)
        self.assertEqual(self.close_calls, 0)

    def test_slow_escape_taps_do_not_close_app(self):
        with patch("voiceflow_app.hotkeys.time.monotonic", side_effect=[10.0, 11.0]):
            self.listener.on_press(kb.Key.esc)
            self.listener.on_release(kb.Key.esc)
            self.listener.on_press(kb.Key.esc)
        self.assertEqual(self.close_calls, 0)

    def test_mouse_listener_does_not_start_when_setting_disabled(self):
        with patch("voiceflow_app.hotkeys.MouseSideButtonHook") as mouse_listener:
            self.listener.refresh_mouse_listener()
        mouse_listener.assert_not_called()

    def test_mouse_listener_starts_when_setting_enabled(self):
        self.state.settings.mouse_side_button_mic = True
        with patch("voiceflow_app.hotkeys.MouseSideButtonHook") as mouse_listener:
            self.listener.refresh_mouse_listener()
        mouse_listener.assert_called_once_with(self.listener.handle_mouse_button_event, self.listener.log_error)
        mouse_listener.return_value.start.assert_called_once()

    def test_mouse_button_ignored_when_setting_disabled(self):
        handled = self.listener.handle_mouse_button_event(ms.Button.x2, True)
        self.assertFalse(handled)
        self.assertEqual(self.started_modes, [])
        self.assertEqual(self.voice_chat_start_calls, 0)

    def test_mouse_back_button_starts_and_releases_dictation_when_enabled(self):
        self.state.settings.mouse_side_button_mic = True
        self.assertTrue(self.listener.handle_mouse_button_event(ms.Button.x1, True))
        self.assertEqual(self.started_modes, ["dictation"])
        self.assertEqual(self.voice_chat_start_calls, 0)
        self.assertTrue(self.listener.handle_mouse_button_event(ms.Button.x1, False))
        self.assertEqual(self.stop_calls, 1)

    def test_mouse_forward_button_starts_and_releases_ai_command_when_enabled(self):
        self.state.settings.mouse_side_button_mic = True
        self.assertTrue(self.listener.handle_mouse_button_event(ms.Button.x2, True))
        self.assertEqual(self.started_modes, ["command"])
        self.assertEqual(self.voice_chat_start_calls, 0)
        self.assertTrue(self.listener.handle_mouse_button_event(ms.Button.x2, False))
        self.assertEqual(self.voice_chat_stop_calls, 0)
        self.assertEqual(self.stop_calls, 1)

    def test_duplicate_mouse_sources_do_not_stop_recording_early(self):
        self.state.settings.mouse_side_button_mic = True
        self.listener.handle_mouse_button_event(ms.Button.x2, True, source="mouse")
        self.listener.handle_mouse_button_event(ms.Button.x2, True, source="keyboard")
        self.assertEqual(self.started_modes, ["command"])

        self.listener.handle_mouse_button_event(ms.Button.x2, False, source="keyboard")
        self.assertEqual(self.stop_calls, 0)

        self.listener.handle_mouse_button_event(ms.Button.x2, False, source="mouse")
        self.assertEqual(self.stop_calls, 1)

    def test_releasing_mouse_button_does_not_stop_keyboard_recording(self):
        self.state.settings.mouse_side_button_mic = True
        self.state.recording_state = STATE_RECORDING
        self.state.recording_mode = "dictation"
        self.listener.handle_mouse_button_event(ms.Button.x2, False)
        self.assertEqual(self.stop_calls, 0)

    def test_mouse_release_does_not_stop_keyboard_dictation(self):
        self.state.recording_state = STATE_RECORDING
        self.state.recording_mode = "dictation"
        self.listener.on_click(0, 0, ms.Button.x1, False)
        self.assertEqual(self.stop_calls, 0)


if __name__ == "__main__":
    unittest.main()
