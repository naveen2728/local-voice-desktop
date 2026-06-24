import unittest
from unittest.mock import Mock, patch

from voiceflow_app.app import VoiceFlowApp
from voiceflow_app.ai_client import GenerationError
from voiceflow_app.config import AppSettings


class AppRewriteTests(unittest.TestCase):
    def make_app(self):
        with patch("voiceflow_app.app.load_settings", return_value=AppSettings()), patch("voiceflow_app.app.HistoryStore"):
            app = VoiceFlowApp()
        app.state.client = object()
        app.show_toast = Mock()
        app.set_orb = Mock()
        app._record_history = Mock()
        return app

    def test_rewrite_copies_and_records_generated_text(self):
        app = self.make_app()
        with patch("pyperclip.paste", return_value="rough notes"), patch("pyperclip.copy") as copy, patch("voiceflow_app.app.ai_client.generate", return_value="clean notes"), patch("voiceflow_app.app.time.sleep"):
            app._rewrite_clipboard("Turn into notes")
        copy.assert_called_once_with("clean notes")
        app._record_history.assert_called_once_with("clean notes", mode="rewrite", used_clipboard=True, request="Turn into notes")
        app.show_toast.assert_any_call("Rewritten text copied.")

    def test_rewrite_rejects_empty_clipboard(self):
        app = self.make_app()
        with patch("pyperclip.paste", return_value=" "), patch("voiceflow_app.app.time.sleep"):
            app._rewrite_clipboard("Fix grammar")
        app.show_toast.assert_any_call("Clipboard is empty. Copy text first.")

    def test_rewrite_rejects_more_than_100_lines(self):
        app = self.make_app()
        content = "\n".join(f"line {number}" for number in range(101))
        with patch("pyperclip.paste", return_value=content), patch("voiceflow_app.app.ai_client.generate") as generate, patch("voiceflow_app.app.time.sleep"):
            app._rewrite_clipboard("Fix grammar")
        generate.assert_not_called()
        app.show_toast.assert_any_call("Copied content is 101 lines. Copy 100 lines or fewer and try again.")

    def test_rewrite_surfaces_friendly_ai_error(self):
        app = self.make_app()
        with patch("pyperclip.paste", return_value="notes"), patch("pyperclip.copy") as copy, patch("voiceflow_app.app.ai_client.generate", side_effect=GenerationError("Groq limit reached. Try again shortly.")), patch("voiceflow_app.app.time.sleep"):
            app._rewrite_clipboard("Fix grammar")
        copy.assert_not_called()
        app.show_toast.assert_any_call("Groq limit reached. Try again shortly.")

    def test_rewrite_reconnects_when_startup_api_connect_failed(self):
        app = self.make_app()
        app.state.client = None
        client = object()
        with patch("pyperclip.paste", return_value="notes"), patch("pyperclip.copy") as copy, patch(
            "voiceflow_app.app.load_api_key", return_value="key"
        ), patch("voiceflow_app.app.ai_client.connect", return_value=client) as connect, patch(
            "voiceflow_app.app.ai_client.generate", return_value="clean notes"
        ), patch("voiceflow_app.app.time.sleep"):
            app._rewrite_clipboard("Fix grammar")
        connect.assert_called_once_with()
        self.assertIs(app.state.client, client)
        copy.assert_called_once_with("clean notes")


if __name__ == "__main__":
    unittest.main()
