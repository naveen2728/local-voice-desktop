import unittest
from unittest.mock import Mock, patch

from voiceflow_app.ai_client import (
    GenerationError,
    clean_chat_output,
    clean_generated_output,
    friendly_generation_error,
    generate,
    read_screen,
)


class ApiError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class AiClientTests(unittest.TestCase):
    def test_strips_outer_markdown_code_fence(self):
        output = "```java\npublic class Main {}\n```"
        self.assertEqual(clean_generated_output(output), "public class Main {}")

    def test_keeps_plain_text_unchanged(self):
        self.assertEqual(clean_generated_output(" hello world "), "hello world")

    def test_strips_common_assistant_preamble(self):
        output = 'I can help with that.\n\n"Hey Dad, I will not be able to make it. Sorry about that."'
        self.assertEqual(clean_generated_output(output), "Hey Dad, I will not be able to make it. Sorry about that.")

    def test_strips_single_line_surrounding_quotes(self):
        self.assertEqual(clean_generated_output('"Hey Dad, I cannot make it."'), "Hey Dad, I cannot make it.")

    def test_keeps_valid_single_line_content_that_starts_similarly(self):
        self.assertEqual(clean_generated_output("Sure decisions take time."), "Sure decisions take time.")

    def test_chat_output_converts_markdown_asterisk_bullets_to_dot_bullets(self):
        output = "* First item\n  * Nested item\nNormal line"
        self.assertEqual(clean_chat_output(output), "• First item\n  • Nested item\nNormal line")

    def test_classifies_common_groq_errors(self):
        self.assertIn("invalid", friendly_generation_error(ApiError("unauthorized", 401)))
        self.assertIn("too large", friendly_generation_error(ApiError("Request too large", 413)))
        self.assertIn("limit reached", friendly_generation_error(ApiError("rate_limit_exceeded", 429)))
        self.assertIn("connect", friendly_generation_error(ApiError("Connection timed out")))

    def test_generate_raises_friendly_error_and_logs_original(self):
        client = Mock()
        client.chat.completions.create.side_effect = ApiError("Request too large", 413)
        log_error = Mock()
        with self.assertRaisesRegex(GenerationError, "too large"):
            generate(client, "prompt", log_error)
        log_error.assert_called_once()

    def test_generate_uses_answer_only_system_prompt(self):
        client = Mock()
        client.chat.completions.create.return_value.choices = [
            Mock(message=Mock(content="result"))
        ]
        self.assertEqual(generate(client, "prompt", Mock()), "result")
        messages = client.chat.completions.create.call_args.kwargs["messages"]
        self.assertIn("Never add acknowledgements", messages[0]["content"])

    def test_read_screen_sends_image_and_question_to_vision_model(self):
        client = Mock()
        client.chat.completions.create.return_value.choices = [
            Mock(message=Mock(content="The screen shows an error."))
        ]
        with patch("voiceflow_app.ai_client._image_data_url", return_value="data:image/jpeg;base64,abc"):
            result = read_screen(client, "What is wrong?", "screen.png", Mock())
        self.assertEqual(result, "The screen shows an error.")
        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "meta-llama/llama-4-scout-17b-16e-instruct")
        content = kwargs["messages"][0]["content"]
        self.assertIn("What is wrong?", content[0]["text"])
        self.assertEqual(content[1]["image_url"]["url"], "data:image/jpeg;base64,abc")


if __name__ == "__main__":
    unittest.main()
