# image-gen skill v1.0

Codex/Claude skill for generating images through Codex's built-in `image_gen` tool by spawning a fresh `codex exec` session.

The main workflow is documented in [`SKILL.md`](SKILL.md). The short version:

- Uses ChatGPT OAuth via Codex, not an `OPENAI_API_KEY` fallback.
- Spawns a fresh Codex session per call to keep image prompts isolated from the caller's long-running context (do **not** use `--ephemeral` — the session rollout must persist for extraction).
- codex v0.140.0 no longer writes `~/.codex/generated_images/<session_id>/ig_*.png`; the image arrives as inline base64 in the session rollout jsonl. [`scripts/extract_imagegen.py`](scripts/extract_imagegen.py) decodes it deterministically to a real PNG instead of trusting model-reported paths.
- Uses a stable transparent PNG contract: generate on solid `#FF00FF` or `#00FF00`, then run [`scripts/chroma_key_transparent.py`](scripts/chroma_key_transparent.py).
- Includes experimental batch and continuation scripts under [`scripts/`](scripts/).

## Install

From Codex skill installer workflows, install this repository as a root skill:

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo aldegad/image-gen \
  --path .
```

For local umbrella installs, keep this repository as the public upstream and symlink/copy it through your own agent-skill installer.

## Requirements

```bash
which codex
codex login status
codex features list | grep image_generation
```

Transparent PNG post-processing requires Python Pillow (`PIL`). ImageMagick (`magick`) remains useful for optional inspection.

## License

MIT
