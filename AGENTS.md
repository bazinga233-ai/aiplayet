# Repository Guidelines

## Project Structure & Module Organization
This repository is a small, script-first Python workspace for converting short videos into draft scripts. `video2script.py` is the main pipeline: audio extraction with `ffmpeg`, ASR with FunASR, keyframe analysis with Qwen, and final script assembly. `tests/test_asr.py` is a smoke test for the ASR model. `convert_to_html.py` and `convert_ansi.py` are utility scripts for converting saved conversation logs to HTML. Store source videos in `videos/` and generated JSON/TXT outputs in `output/`.

## Build, Test, and Development Commands
There is no formal build step. Use the scripts directly:

- `python video2script.py videos/01.mp4` runs the full pipeline for one file.
- `python video2script.py` processes every `.mp4` in `videos/`.
- `python -m tests.test_asr <audio.wav>` validates that FunASR loads and returns timestamps.
- `python convert_to_html.py` regenerates `conversation.html`.
- `python convert_ansi.py` regenerates `conversation_ansi.html`.
- `run.bat` launches the pipeline through a local Anaconda environment, but its paths are machine-specific and should be updated before reuse.

## Coding Style & Naming Conventions
Follow the existing Python style: 4-space indentation, `snake_case` for functions/variables, and `UPPER_CASE` for configuration constants such as `KEYFRAME_INTERVAL`. Prefer `pathlib.Path` for filesystem work and keep helper functions focused on one pipeline step. Match the current repo tone: concise Chinese docstrings, readable `print()` progress logs, and minimal comments only where the flow is non-obvious.

## Testing Guidelines
Testing is currently lightweight and manual. Add focused smoke tests as `tests/test_*.py` scripts unless a larger test suite is introduced. When changing ASR, frame extraction, or script synthesis, run `python -m tests.test_asr <audio.wav>` and at least one end-to-end sample with `python video2script.py <video>`. Verify that both `*_dialogues.json` and `*_script.txt` are produced and readable. No coverage gate is configured.

## Commit & Pull Request Guidelines
This workspace does not include `.git` history, so no local commit convention can be inferred. Use short imperative commit subjects such as `Add CLI flag for input directory` or `Fix keyframe timestamp export`. PRs should describe the sample input used, note any model or GPU assumptions, list changed absolute paths, and include representative output snippets or screenshots when converter scripts affect HTML rendering.

## Configuration Tips
Several scripts hardcode Windows paths, CUDA device settings, and local model locations. Keep new configuration centralized, prefer environment variables or CLI arguments for new paths, and avoid committing large generated artifacts or private local paths unless they are intentional fixtures.
