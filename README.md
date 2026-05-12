# image-gen skill

Codex/Claude skill for generating images through Codex's built-in `image_gen` tool by spawning a fresh `codex exec` session.

The main workflow is documented in [`SKILL.md`](SKILL.md). The short version:

- Uses ChatGPT OAuth via Codex, not an `OPENAI_API_KEY` fallback.
- Spawns an ephemeral Codex session to keep image prompts isolated from the caller's long-running context.
- Verifies generated PNGs from `~/.codex/generated_images/<session_id>/ig_*.png` instead of trusting model-reported paths.
- Includes transparent-background workarounds using chroma key, ImageMagick, and PIL.
- Includes experimental batch and continuation scripts under [`scripts/`](scripts/).

## Install

From Codex skill installer workflows, install this repository as a root skill:

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo aldegad/image-gen-skill \
  --path .
```

For local umbrella installs, keep this repository as the public upstream and symlink/copy it through your own agent-skill installer.

## Requirements

```bash
which codex
codex login status
codex features list | grep image_generation
```

Optional post-processing workflows use ImageMagick (`magick`) and Python Pillow (`PIL`).

## License

MIT
