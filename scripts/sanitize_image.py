#!/usr/bin/env python3
"""Create a safer image copy before previewing an untrusted local image."""

from __future__ import annotations

import argparse
import binascii
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SAFE_PNG_CHUNKS = {b"IHDR", b"PLTE", b"tRNS", b"IDAT", b"IEND"}


class SanitizeError(RuntimeError):
    pass


def detect_format(path: Path) -> str:
    with path.open("rb") as f:
        head = f.read(32)
    if head.startswith(PNG_SIGNATURE):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brands = head[8:32]
        if any(brand in brands for brand in (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1")):
            return "heic"
    return "unknown"


def default_output_path(src: Path, detected: str, output_format: str) -> Path:
    if detected == "png":
        suffix = ".png"
    else:
        suffix = ".jpg" if output_format == "jpeg" else ".png"
    return src.with_name(f"{src.stem}-sanitized{suffix}")


def read_exact(f, n: int, label: str) -> bytes:
    data = f.read(n)
    if len(data) != n:
        raise SanitizeError(f"Unexpected end of file while reading {label}")
    return data


def sanitize_png(src: Path, dst: Path) -> dict:
    dropped: list[dict] = []
    kept: list[dict] = []
    total_chunks = 0
    saw_iend = False

    with src.open("rb") as f, dst.open("wb") as out:
        signature = read_exact(f, 8, "PNG signature")
        if signature != PNG_SIGNATURE:
            raise SanitizeError("Input is not a PNG")
        out.write(signature)

        while True:
            offset = f.tell()
            length_bytes = f.read(4)
            if not length_bytes:
                break
            if len(length_bytes) != 4:
                raise SanitizeError("Truncated PNG chunk length")

            length = struct.unpack(">I", length_bytes)[0]
            chunk_type = read_exact(f, 4, "PNG chunk type")
            if len(chunk_type) != 4 or not all(65 <= b <= 122 for b in chunk_type):
                raise SanitizeError(f"Invalid PNG chunk type at offset {offset}")

            data = read_exact(f, length, chunk_type.decode("latin-1"))
            crc_bytes = read_exact(f, 4, "PNG chunk CRC")
            expected_crc = struct.unpack(">I", crc_bytes)[0]
            actual_crc = binascii.crc32(chunk_type + data) & 0xFFFFFFFF
            chunk_name = chunk_type.decode("latin-1")

            if expected_crc != actual_crc:
                raise SanitizeError(f"CRC mismatch in PNG chunk {chunk_name} at offset {offset}")

            total_chunks += 1
            record = {"type": chunk_name, "length": length, "offset": offset}
            if chunk_type in SAFE_PNG_CHUNKS:
                out.write(struct.pack(">I", length))
                out.write(chunk_type)
                out.write(data)
                out.write(struct.pack(">I", actual_crc))
                kept.append(record)
            else:
                dropped.append(record)

            if chunk_type == b"IEND":
                saw_iend = True
                break

    if not saw_iend:
        raise SanitizeError("PNG ended before IEND chunk")

    return {
        "mode": "png_chunk_rewrite",
        "input": str(src),
        "output": str(dst),
        "input_size": src.stat().st_size,
        "output_size": dst.stat().st_size,
        "chunks_seen": total_chunks,
        "chunks_kept": kept,
        "chunks_dropped": dropped,
    }


def rasterize_with_sips(src: Path, dst: Path, output_format: str, max_dimension: int) -> dict:
    sips = shutil.which("sips")
    if not sips:
        raise SanitizeError("macOS sips command is not available for non-PNG conversion")

    cmd = [
        sips,
        "-s",
        "format",
        output_format,
        "-Z",
        str(max_dimension),
        str(src),
        "--out",
        str(dst),
    ]
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise SanitizeError((proc.stderr or proc.stdout or "sips conversion failed").strip())

    return {
        "mode": "sips_rasterize",
        "input": str(src),
        "output": str(dst),
        "format": output_format,
        "max_dimension": max_dimension,
        "input_size": src.stat().st_size,
        "output_size": dst.stat().st_size,
    }


def print_report(report: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print(f"mode={report['mode']}")
    print(f"input={report['input']}")
    print(f"output={report['output']}")
    print(f"input_size={report['input_size']}")
    print(f"output_size={report['output_size']}")
    if report["mode"] == "png_chunk_rewrite":
        dropped = report["chunks_dropped"]
        if dropped:
            rendered = ", ".join(f"{item['type']}({item['length']})" for item in dropped)
            print(f"dropped={rendered}")
        else:
            print("dropped=")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Create a sanitized image copy before previewing.")
    parser.add_argument("input", help="Local image path to sanitize")
    parser.add_argument("--output", "-o", help="Output path for the sanitized image")
    parser.add_argument("--format", choices=("jpeg", "png"), default="jpeg", help="Output format for non-PNG inputs")
    parser.add_argument("--max-dimension", type=int, default=4096, help="Longest side limit for non-PNG rasterization")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    args = parser.parse_args(argv)

    src = Path(args.input).expanduser().resolve()
    if not src.exists():
        raise SanitizeError(f"Input does not exist: {src}")
    if not src.is_file():
        raise SanitizeError(f"Input is not a regular file: {src}")

    detected = detect_format(src)
    dst = Path(args.output).expanduser().resolve() if args.output else default_output_path(src, detected, args.format)
    if dst == src:
        raise SanitizeError("Output path must not be the same as input path")
    dst.parent.mkdir(parents=True, exist_ok=True)

    if detected == "png":
        report = sanitize_png(src, dst)
    else:
        report = rasterize_with_sips(src, dst, args.format, args.max_dimension)
        report["detected_format"] = detected

    print_report(report, args.json)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except SanitizeError as exc:
        print(f"error={exc}", file=sys.stderr)
        raise SystemExit(2)
