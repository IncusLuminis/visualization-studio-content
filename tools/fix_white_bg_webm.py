#!/usr/bin/env python3
"""Re-encode webm files with white/transparent matte onto Telemetry dark background."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ANIM = ROOT / "media-site" / "animations"

# Telemetry standard HUD background RGB(2, 7, 13)
DARK_BG_FILTER = (
    "[0:v]split=2[base][key];"
    "[key]colorkey=0xFFFFFF:0.14:0.06,format=rgba[fg];"
    "[base]geq=r=2:g=7:b=13[bg];"
    "[bg][fg]overlay=shortest=1,format=yuv420p[v]"
)


def corner_is_white(webm: Path) -> bool:
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp = f.name
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(webm), "-vframes", "1", tmp],
            check=True,
            capture_output=True,
        )
        img = Image.open(tmp).convert("RGBA")
        corners = [img.getpixel((5, 5)), img.getpixel((img.width - 5, 5)), img.getpixel((5, img.height - 5))]
        avg = tuple(sum(c[i] for c in corners) // 3 for i in range(3))
        return avg[0] > 200 and avg[1] > 200 and avg[2] > 200
    finally:
        os.unlink(tmp)


def fix_webm(src: Path) -> None:
    tmp = src.with_name(src.stem + ".tmp.webm")
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-filter_complex", DARK_BG_FILTER,
        "-map", "[v]",
        "-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0",
        str(tmp),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    if not tmp.exists() or tmp.stat().st_size == 0:
        raise RuntimeError("empty output")
    tmp.replace(src)


def main() -> int:
    webms = sorted(ANIM.rglob("*.webm"))
    targets = [p for p in webms if corner_is_white(p)]
    if not targets:
        print("No white-background webm files found.")
        return 0

    print(f"Fixing {len(targets)} file(s) ...\n")
    failed = []
    for i, path in enumerate(targets, 1):
        rel = path.relative_to(ANIM).as_posix()
        try:
            fix_webm(path)
            print(f"[{i}/{len(targets)}] OK  {rel}")
        except Exception as exc:
            failed.append((rel, str(exc)))
            print(f"[{i}/{len(targets)}] FAIL {rel}: {exc}", file=sys.stderr)

    print(f"\nDone: {len(targets) - len(failed)} fixed, {len(failed)} failed")
    if failed:
        for rel, err in failed:
            print(f"  {rel}: {err}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
