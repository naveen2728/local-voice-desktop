import base64
import io


MODEL = "llama-3.1-8b-instant"
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
MAX_VISION_IMAGE_BYTES = 3_500_000
ASSISTANT_PREAMBLES = (
    "sure",
    "sure thing",
    "certainly",
    "of course",
    "absolutely",
    "i can help with that",
    "i'd be happy to help",
    "here is the requested output",
    "here's the requested output",
    "here is the result",
    "here's the result",
    "here is the rewritten text",
    "here's the rewritten text",
    "here is the updated code",
    "here's the updated code",
)
ANSWER_ONLY_SYSTEM_PROMPT = (
    "Return only the final content the user can directly paste. "
    "Never add acknowledgements, offers to help, explanations, commentary, labels, preambles, "
    "follow-up questions, markdown fences, or surrounding quotes. "
    "Do not say phrases such as 'Sure', 'I can help with that', or 'Here is'. "
    "If the user asks for a message, return only the message. "
    "If the user asks for code, return only the code. "
    "If the user asks for a rewrite or translation, return only the rewritten or translated content."
)
CHAT_SYSTEM_PROMPT = (
    "You are VoiceFlow AI, a concise, helpful desktop assistant. "
    "Answer naturally in a short conversational style. "
    "Do not add markdown fences unless the user asks for code. "
    "When giving steps, keep them practical and brief. "
    "When writing bullet lists, use the bullet character '•' instead of markdown asterisks."
)


class GenerationError(RuntimeError):
    pass


def clean_generated_output(text):
    result = text.strip()
    if result.startswith("```"):
        lines = result.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            result = "\n".join(lines[1:-1]).strip()
    lines = result.splitlines()
    while len(lines) > 1 and _is_assistant_preamble(lines[0]):
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    result = "\n".join(lines).strip()
    if len(result) >= 2 and result[0] == result[-1] == '"' and "\n" not in result:
        result = result[1:-1].strip()
    return result


def clean_chat_output(text):
    result = clean_generated_output(text)
    lines = []
    for line in result.splitlines():
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        if stripped.startswith("* "):
            lines.append(f"{indent}• {stripped[2:]}")
        else:
            lines.append(line)
    return "\n".join(lines).strip()


def _is_assistant_preamble(line):
    normalized = line.strip().lower().rstrip(".!:")
    return normalized in ASSISTANT_PREAMBLES


def friendly_generation_error(exc):
    message = str(exc).lower()
    status_code = getattr(exc, "status_code", None)
    if status_code in (401, 403) or "invalid api key" in message or "authentication" in message:
        return "Groq API key is invalid. Update it from the context menu."
    if status_code == 413 or "request too large" in message or "requested" in message and "tokens" in message:
        return "The AI request is too large. Copy less text and try again."
    if status_code == 429 or "rate limit" in message or "rate_limit" in message:
        return "Groq limit reached. Try again shortly."
    if "connection" in message or "timed out" in message or "timeout" in message:
        return "Could not connect to Groq. Check your internet connection."
    return "AI request failed. Try again."


def connect():
    from groq import Groq

    client = Groq()
    client.chat.completions.create(
        model=MODEL,
        max_tokens=1,
        messages=[{"role": "user", "content": "hi"}],
    )
    return client


def cleanup(client, text, prompt, log_error):
    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=1024,
            messages=[
                {
                    "role": "system",
                    "content": "Fix errors as instructed. NEVER rewrite or change meaning. Return ONLY corrected text.",
                },
                {"role": "user", "content": f"{prompt}\n\nText: {text}"},
            ],
        )
        result = response.choices[0].message.content.strip()
        return result if len(result) <= len(text) * 1.5 else text
    except Exception as exc:
        log_error("Cleanup failed", exc)
        return text


def generate(client, prompt, log_error):
    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=2048,
            messages=[
                {
                    "role": "system",
                    "content": ANSWER_ONLY_SYSTEM_PROMPT,
                },
                {"role": "user", "content": prompt},
            ],
        )
        return clean_generated_output(response.choices[0].message.content)
    except Exception as exc:
        log_error("Generation failed", exc)
        raise GenerationError(friendly_generation_error(exc)) from exc


def chat(client, messages, log_error):
    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=2048,
            messages=[{"role": "system", "content": CHAT_SYSTEM_PROMPT}] + messages,
        )
        return clean_chat_output(response.choices[0].message.content)
    except Exception as exc:
        log_error("Chat failed", exc)
        raise GenerationError(friendly_generation_error(exc)) from exc


def _image_data_url(path):
    from PIL import Image

    with Image.open(path) as image:
        image = image.convert("RGB")
        max_side = 1600
        if max(image.size) > max_side:
            image.thumbnail((max_side, max_side))

        quality = 85
        while quality >= 45:
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=quality, optimize=True)
            data = buffer.getvalue()
            if len(data) <= MAX_VISION_IMAGE_BYTES:
                encoded = base64.b64encode(data).decode("ascii")
                return f"data:image/jpeg;base64,{encoded}"
            quality -= 10

    raise GenerationError("Screenshot is too large to send. Try capturing a smaller screen area later.")


def read_screen(client, question, screenshot_path, log_error):
    try:
        image_url = _image_data_url(screenshot_path)
        prompt = (
            f"{question}\n\n"
            "Read the screenshot carefully. If there is visible text, quote the important parts exactly enough "
            "to help the user. If it shows an error or app UI, explain what is happening and what to do next. "
            "Keep the answer concise and practical."
        )
        response = client.chat.completions.create(
            model=VISION_MODEL,
            max_tokens=900,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
        )
        return response.choices[0].message.content.strip()
    except GenerationError:
        raise
    except Exception as exc:
        log_error("Screen vision failed", exc)
        raise GenerationError(friendly_generation_error(exc)) from exc
