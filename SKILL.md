---
name: safe-image-preflight
description: "Preflight and sanitize local image files before Codex views them. Use when a user provides an image path that may freeze chat preview or asks to inspect, open, view, upload, or analyze images safely, especially GPT-generated or downloaded PNGs with C2PA/JUMBF/caBX metadata, HEIC, TIFF, WEBP, very large images, malformed metadata, or requests like 'do not read the raw image', 'sanitize first', 'safe copy', or 'preflight image'."
---

# Safe Image Preflight

## Overview

Preflight risky local images without triggering chat preview or image rendering. Create a sanitized copy first, then use only that copy for any visual inspection.

## Critical Rule

Do not call `view_image`, embed the raw image in Markdown, or otherwise preview the original file before sanitizing it. If the user directly attaches an image and the UI has already rendered it, continue with the available context, but for path-based images always sanitize first.

## Workflow

1. Ask for or use a local absolute image path. Prefer a path over an uploaded attachment when the user says an image may freeze the chat.
2. Inspect only filesystem and container metadata first: `stat`, `ls -lhO@`, `mdls`, `file`, `xxd -l 128`, or the bundled sanitizer script. Avoid tools that decode and display pixels.
3. Run `scripts/sanitize_image.py` on the image path. Put the output in the current workspace unless the user asks for another location.
4. Report the original size, detected format, sanitized output path, and removed metadata or conversion mode.
5. Only after the sanitized copy exists, use the sanitized copy for `view_image`, visual analysis, conversion, or upload.

## Bundled Script

Use:

```bash
python3 /Users/yz/.codex/skills/safe-image-preflight/scripts/sanitize_image.py /path/to/image.png --output /safe/output/path.png
```

For PNG files, the script parses chunks without decoding pixels. It keeps only essential image chunks (`IHDR`, `PLTE`, `tRNS`, `IDAT`, `IEND`) and drops metadata chunks such as `caBX`, `iTXt`, `zTXt`, `tEXt`, `eXIf`, `iCCP`, and other nonessential chunks. This removes C2PA/JUMBF payloads that can make some chat previews hang.

For non-PNG formats, the script uses macOS `sips` to re-encode a normal JPEG or PNG copy, stripping problematic container metadata through rasterization.

Useful options:

- `--output PATH`: write the sanitized copy to a specific path.
- `--format jpeg|png`: choose the output format for non-PNG inputs.
- `--max-dimension N`: limit the longest side when rasterizing non-PNG files.
- `--json`: print a machine-readable report.

## Safety Notes

- A prompt or skill cannot stop the frontend from previewing an image that the user already dragged into chat. Tell users to provide local file paths when a file is known to freeze the chat.
- Do not overwrite the original image.
- If the sanitizer reports malformed chunks, CRC mismatches, or a failed conversion, do not preview the original; explain the failure and offer a safer conversion route.
- Sanitized PNG copies may drop color profiles and content-credential metadata. That is expected for this safety workflow.

## Example User Requests

- "This GPT-generated PNG freezes chat; sanitize it before opening."
- "Do not read this image directly. First remove C2PA metadata and make a safe copy."
- "Here is `/Users/me/Downloads/image.heic`; convert it to a safe previewable copy."
