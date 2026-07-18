#!/usr/bin/env python3
"""Batch-convert media-site GIF animations to WebM for CDN."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANIM = ROOT / "media-site" / "animations"

# Telemetry's own notebooks now live here (moved to IncusLuminis).
NOTEBOOKS_DIR = ROOT / "notebooks"

# Nebulacast has NOT moved — it's a separate project, still at its original
# PycharmProjects location. Hardcoded (not derived via parents[]) because that
# relative relationship no longer holds now that Telemetry lives elsewhere.
# Scanning both roots keeps this script finding notebook sources on both sides,
# same as before the move (a single REPO root can no longer reach both).
NEBULACAST_ROOT = Path("/Users/mloktionov/PycharmProjects/Stellar_Attractor/ANIM")

SEARCH_ROOTS = [NOTEBOOKS_DIR, NEBULACAST_ROOT]


def ffmpeg_gif_to_webm(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-pix_fmt", "yuv420p",
        str(dst),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def notebook_sources() -> dict[str, list[str]]:
    """Map animation stem -> notebook paths (code cells only).

    Scans both search roots (Telemetry's own notebooks/, plus Nebulacast at its
    old location) since they're no longer under one common ancestor.
    """
    mapping: dict[str, list[str]] = {}
    for search_root in SEARCH_ROOTS:
        if not search_root.exists():
            continue
        for nb in search_root.rglob("*.ipynb"):
            try:
                data = json.loads(nb.read_text(encoding="utf-8"))
            except Exception:
                continue
            code = []
            for cell in data.get("cells", []):
                if cell.get("cell_type") == "code":
                    src = cell.get("source", [])
                    code.append(src if isinstance(src, str) else "".join(src))
            text = "\n".join(code)
            rel = str(nb.relative_to(search_root))
            for line in text.splitlines():
                if ".gif" in line or "ANIMATION_NAME" in line:
                    for token in ('"', "'"):
                        parts = line.split(token)
                        for part in parts:
                            if part.endswith(".gif"):
                                stem = Path(part).stem
                                mapping.setdefault(stem, [])
                                if rel not in mapping[stem]:
                                    mapping[stem].append(rel)
    return mapping


def main() -> int:
    gifs = sorted(ANIM.rglob("*.gif"))
    if not gifs:
        print("No GIF files found.")
        return 0

    nb_map = notebook_sources()
    ok, failed, no_source = [], [], []

    print(f"Converting {len(gifs)} GIF -> WebM ...\n")
    for i, gif in enumerate(gifs, 1):
        rel = gif.relative_to(ANIM).as_posix()
        webm = gif.with_suffix(".webm")
        stem = gif.stem
        sources = nb_map.get(stem, [])
        tag = sources[0] if sources else "NO_SOURCE"

        try:
            ffmpeg_gif_to_webm(gif, webm)
            if not webm.exists() or webm.stat().st_size == 0:
                raise RuntimeError("empty output")
            gif.unlink()
            ok.append((rel, webm.stat().st_size, gif.stat().st_size if gif.exists() else 0, tag))
            print(f"[{i}/{len(gifs)}] OK  {rel}  ({tag})")
        except Exception as exc:
            failed.append((rel, str(exc), tag))
            print(f"[{i}/{len(gifs)}] FAIL {rel}: {exc}", file=sys.stderr)
            continue

        if not sources:
            no_source.append(rel)

    print(f"\nDone: {len(ok)} converted, {len(failed)} failed")
    if no_source:
        print(f"\n=== NO NOTEBOOK SOURCE ({len(no_source)}) ===")
        for p in no_source:
            print(p)
    if failed:
        print(f"\n=== FAILED ({len(failed)}) ===")
        for p, err, _ in failed:
            print(f"{p}: {err}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
