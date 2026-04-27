# safe-image-preflight

Codex skill for sanitizing risky local image files before viewing them.

Use this when a generated or downloaded image may freeze chat preview, especially PNG files with C2PA/JUMBF/`caBX` metadata, or HEIC/TIFF/WEBP files that should be converted before inspection.

## Install

Clone this repository directly into your global Codex skills directory:

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/Mrzhiyao/safe-image-preflight.git ~/.codex/skills/safe-image-preflight
```

If you already have it installed:

```bash
cd ~/.codex/skills/safe-image-preflight
git pull
```

## Use

Ask Codex to use the skill before viewing an image path:

```text
Use $safe-image-preflight to sanitize /Users/yz/Downloads/image.png before viewing it.
```

The important rule is to provide a local path instead of dragging a risky original image into chat. A skill cannot stop the chat frontend from previewing an attachment before Codex receives the message.

## Script

Run the sanitizer directly:

```bash
python3 scripts/sanitize_image.py /path/to/image.png --output /path/to/image-sanitized.png
```

For PNG files, the script rewrites chunks without decoding pixels and keeps only essential image chunks. For non-PNG files, it uses macOS `sips` to rasterize a safer JPEG or PNG copy.
