# Local Voice Desktop

Local Voice Desktop is a Windows-first, local voice productivity assistant. It provides offline speech-to-text, global dictation hotkeys, optional AI rewriting and commands, realtime OpenAI voice conversations, add direct screenshots, and an optional Gmail assistant.

> **Legacy-name notice:** Some internal modules, storage paths, screenshots, and UI strings still use the former working name `VoiceFlow`. They are retained temporarily for compatibility and will be migrated incrementally. This project is not affiliated with Voiceflow, Inc.

## Status

The project is usable but still being prepared for a wider public release. APIs and user-facing behavior may change. Google Gemini Live support is planned; it is not implemented yet.

## Features

- Offline transcription with `faster-whisper`
- Hold-to-dictate and AI-command global hotkeys
- Optional Groq-powered cleanup, commands, and text chat
- OpenAI Realtime speech-to-speech conversations with interruption support
- Optional Gmail search, drafting, and sending
- Windows Credential Manager storage for API keys and OAuth tokens
- Portable Windows executable and installer build scripts

## Requirements

- Windows 10 or 11, 64-bit
- Python 3.11 or 3.12, 64-bit
- A working microphone
- Optional provider API keys for cloud AI features

The source code is free and open source. Cloud providers may charge for API usage. A ChatGPT or Gemini consumer subscription does not necessarily include API credits.

## Run from source

```powershell
git clone https://github.com/naveen2728/local-voice-desktop.git
cd local-voice-desktop
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

The first run downloads the Whisper `base.en` model unless a bundled model is present. API keys entered through the application are stored in Windows Credential Manager, not in the repository.

## Main controls

- Hold `Ctrl+Space` to dictate; release to paste.
- Hold `Ctrl+Shift+Space` to record an AI command; release to run it.
- Optional mouse workflow: map one mouse button to `Ctrl+Space` for dictation and another to `Ctrl+Shift+Space` for AI commands.
- Press `Backspace` while recording to cancel.
- Press `Escape` twice quickly to quit.
- Right-click the floating orb for settings, diagnostics, AI keys, Gmail actions, and realtime voice chat.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Build a Windows executable

```powershell
.\.venv\Scripts\Activate.ps1
python build.py
```

The build downloads the speech model and creates `dist\VoiceFlow.exe`. Generated models, executables, installers, and local output are intentionally excluded from Git. See [README_BUILD.md](README_BUILD.md) for packaging details.

## Privacy

Basic transcription runs locally. Features backed by Groq, OpenAI, Pollinations, or Google send the content needed for that feature to the selected provider. Gmail sync stores a local searchable index under `%APPDATA%\VoiceFlow`. Review [PRIVACY.md](PRIVACY.md) before enabling cloud or Gmail features.

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and the [Code of Conduct](CODE_OF_CONDUCT.md) before opening a contribution.

## License

The project source is licensed under the [Apache License 2.0](LICENSE). Third-party packages and downloaded model files remain under their respective licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
