#!/usr/bin/env python3
"""Patch source cells and regenerate large Telemetry animations."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # Infographics/Telemetry
ANIM = ROOT / "media-site" / "animations"
PY = Path("/Users/mloktionov/anaconda3/bin/python")


def load_nb(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_nb(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def cell_source(cell: dict) -> str:
    src = cell.get("source", [])
    return src if isinstance(src, str) else "".join(src)


def set_cell_source(cell: dict, text: str) -> None:
    cell["source"] = [line + "\n" for line in text.splitlines(True)]


def find_cell(nb: dict, needle: str) -> tuple[int, dict]:
    for i, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") == "code" and needle in cell_source(cell):
            return i, cell
    raise KeyError(f"cell not found: {needle!r}")


def run_code(code: str, cwd: Path, label: str) -> None:
    print(f"\n{'=' * 60}\n[RUN] {label}\n{'=' * 60}")
    proc = subprocess.run([str(PY), "-c", code], cwd=cwd, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{label} failed with exit {proc.returncode}")


def ffmpeg_transcode(src: Path, dst: Path, kind: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if kind == "gif2webm":
        cmd = [
            "ffmpeg", "-y", "-i", str(src),
            "-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-pix_fmt", "yuv420p",
            str(dst),
        ]
    elif kind == "webm2mp4":
        cmd = [
            "ffmpeg", "-y", "-i", str(src),
            "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(dst),
        ]
    else:
        raise ValueError(kind)
    print(f"[FFMPEG] {src.name} -> {dst.name}")
    subprocess.run(cmd, check=True, capture_output=True)


def patch_telemetry2_magnetic(nb_path: Path) -> None:
    data = load_nb(nb_path)
    try:
        _, cell = find_cell(data, 'OUT = OUT_DIR / "magnetic_field_mapper.gif"')
    except KeyError:
        _, cell = find_cell(data, 'export_animation(_arrays, OUT_DIR, "magnetic_field_mapper"')
    src = cell_source(cell)
    if 'export_animation(_arrays, OUT_DIR, "magnetic_field_mapper"' in src:
        return
    src = src.replace(
        'OUT = OUT_DIR / "magnetic_field_mapper.gif"\n\nframes[0].save(\n'
        '    OUT,\n'
        '    save_all=True,\n'
        '    append_images=frames[1:],\n'
        '    duration=int(1000 / FPS),\n'
        '    loop=0,\n'
        '    disposal=2,\n'
        '    transparency=0,\n'
        ')\n\nprint(f"Saved: {OUT}")',
        'import numpy as _np\n'
        'from vizlib.animation_export import export_animation\n\n'
        '_arrays = [_np.array(f.convert("RGB")) for f in frames]\n'
        'saved = export_animation(_arrays, OUT_DIR, "magnetic_field_mapper", "webm", FPS)\n'
        'print(f"Saved: {saved}")',
    )
    set_cell_source(cell, src)
    save_nb(nb_path, data)


def patch_output_format(nb_path: Path, needle: str, new_fmt: str) -> str:
    data = load_nb(nb_path)
    _, cell = find_cell(data, needle)
    src = cell_source(cell)
    src = re.sub(
        r'OUTPUT_FORMAT\s*=\s*["\'](?:gif|webm|mp4)["\']',
        f'OUTPUT_FORMAT = "{new_fmt}"',
        src,
        count=1,
    )
    set_cell_source(cell, src)
    save_nb(nb_path, data)
    return src


def patch_imageio_webm_export(nb_path: Path, needle: str) -> None:
    """Telemetry_11/12: add webm branch via vizlib."""
    data = load_nb(nb_path)
    _, cell = find_cell(data, needle)
    src = cell_source(cell)
    if 'elif OUTPUT_FORMAT == "webm":' in src:
        return
    pattern = re.compile(
        r'if OUTPUT_FORMAT == "gif":\s*\n'
        r'\s*imageio\.mimsave\(\s*\n'
        r'\s*OUT_FILE,\s*\n'
        r'\s*frames,\s*\n'
        r'\s*fps=FPS,\s*\n'
        r'\s*loop=0,\s*\n'
        r'\s*\)\s*\n'
        r'else:\s*\n'
        r'\s*imageio\.mimsave\(\s*\n'
        r'\s*OUT_FILE,\s*\n'
        r'\s*frames,\s*\n'
        r'\s*fps=FPS,\s*\n'
        r'\s*quality=9,\s*\n'
        r'\s*macro_block_size=1,\s*\n'
        r'\s*\)',
        re.MULTILINE,
    )
    replacement = (
        'if OUTPUT_FORMAT == "gif":\n'
        '    imageio.mimsave(\n'
        '        OUT_FILE,\n'
        '        frames,\n'
        '        fps=FPS,\n'
        '        loop=0,\n'
        '    )\n'
        'elif OUTPUT_FORMAT == "webm":\n'
        '    from vizlib.animation_export import export_animation\n'
        '    export_animation(frames, OUT_DIR, ANIMATION_NAME, "webm", FPS)\n'
        '    OUT_FILE = OUT_DIR / f"{ANIMATION_NAME}.webm"\n'
        'else:\n'
        '    imageio.mimsave(\n'
        '        OUT_FILE,\n'
        '        frames,\n'
        '        fps=FPS,\n'
        '        quality=9,\n'
        '        macro_block_size=1,\n'
        '    )'
    )
    new_src, n = pattern.subn(replacement, src, count=1)
    if n != 1:
        raise ValueError(f"export block not found in {nb_path.name} ({needle})")
    set_cell_source(cell, new_src)
    save_nb(nb_path, data)


def patch_nebulacast_gif_cell(nb_path: Path, gif_name: str, subdir: str) -> str:
    data = load_nb(nb_path)
    _, cell = find_cell(data, gif_name)
    src = cell_source(cell)
    webm_name = gif_name.replace(".gif", ".webm")
    media_out = f'Path("Infographics/Telemetry/media-site/animations/{subdir}")'
    src = re.sub(
        r'OUT_DIR\s*=\s*Path\("animations"\)',
        f"OUT_DIR = {media_out}",
        src,
        count=1,
    )
    src = src.replace(
        f'GIF_PATH = OUT_DIR / "{gif_name}"',
        f'WEBM_PATH = OUT_DIR / "{webm_name}"',
    )
    src = src.replace("from matplotlib.animation import FuncAnimation, PillowWriter",
                      "from matplotlib.animation import FuncAnimation, FFMpegWriter")
    src = src.replace(
        "writer = PillowWriter(fps=FPS)\nanim.save(GIF_PATH, writer=writer)",
        'writer = FFMpegWriter(fps=FPS, codec="libvpx-vp9", extra_args=["-crf", "32", "-b:v", "0", "-pix_fmt", "yuv420p"])\n'
        "anim.save(WEBM_PATH, writer=writer)",
    )
    src = src.replace("display(Image(filename=str(GIF_PATH)))", "print(f\"Saved: {WEBM_PATH}\")")
    src = src.replace('print(f"Saved: {GIF_PATH}")', 'print(f"Saved: {WEBM_PATH}")')
    src = src.replace('print("Saved:", GIF_PATH)', 'print("Saved:", WEBM_PATH)')
    set_cell_source(cell, src)
    save_nb(nb_path, data)
    return src


def exec_cell(nb_path: Path, needle: str, cwd: Path) -> None:
    data = load_nb(nb_path)
    _, cell = find_cell(data, needle)
    run_code(cell_source(cell), cwd, f"{nb_path.name} :: {needle}")


def main() -> int:
    # Telemetry moved to IncusLuminis (products/visualization-studio/visualization-studio-content).
    # Nebulacast has since ALSO moved (was PycharmProjects/Stellar_Attractor/ANIM/Nebulacast, now
    # products/nebulacast/nebulacast-content/content/my/) — updated here to match. Hardcoded
    # (rather than derived via parents[]) since the two projects live under unrelated roots and
    # there's no stable relative path between them.
    repo = Path("/Users/mloktionov/Projects/IncusLuminis/products/nebulacast/nebulacast-content/content")

    NOTEBOOKS = ROOT / "notebooks"

    # --- patch ---
    patch_telemetry2_magnetic(NOTEBOOKS / "Telemetry_2.ipynb")
    patch_imageio_webm_export(NOTEBOOKS / "Telemetry_11.ipynb", 'ANIMATION_NAME = "gravitational_wave_grid"')
    patch_output_format(NOTEBOOKS / "Telemetry_11.ipynb", 'ANIMATION_NAME = "gravitational_wave_grid"', "webm")
    patch_imageio_webm_export(NOTEBOOKS / "Telemetry_12.ipynb", 'ANIMATION_NAME = "parker_spiral"')
    patch_output_format(NOTEBOOKS / "Telemetry_12.ipynb", 'ANIMATION_NAME = "parker_spiral"', "webm")
    patch_output_format(NOTEBOOKS / "Telemetry_8.ipynb", 'ANIMATION_NAME = "stellar_evolution_very_massive_star"', "webm")
    patch_output_format(NOTEBOOKS / "Telemetry_9.ipynb", 'ANIMATION_NAME = "math_hopf_fibration_rotation"', "mp4")
    patch_output_format(NOTEBOOKS / "Telemetry_9.ipynb", 'ANIMATION_NAME = "math_magnetar_field_hud"', "mp4")

    repo_nb = repo / "my"  # Nebulacast's content now lives in content/my/, not a "Nebulacast" folder
    patch_nebulacast_gif_cell(repo_nb / "Exoplanets.ipynb", "exoplanet_signal_in_white_noise.gif", "exoplanets")
    patch_nebulacast_gif_cell(repo_nb / "Exoplanets.ipynb", "exoplanet_2d_coronagraph_physical_noise.gif", "exoplanets")
    patch_nebulacast_gif_cell(repo_nb / "Enceladus.ipynb", "tidal_interaction_galaxy_demo.gif", "tidal_interaction")
    patch_nebulacast_gif_cell(repo_nb / "BORG.ipynb", "blue_monsters_deep_field_layer.gif", "blue_monsters")

    # --- regenerate (Telemetry notebooks execute with cwd=ROOT, where vizlib/ is a real
    # top-level sibling — no need for the notebooks/vizlib symlink here, that's only for
    # interactive Jupyter use where cwd = the notebook's own directory)
    sys.path.insert(0, str(ROOT))
    exec_cell(NOTEBOOKS / "Telemetry_2.ipynb", "magnetic_field_mapper", ROOT)
    exec_cell(NOTEBOOKS / "Telemetry_11.ipynb", 'ANIMATION_NAME = "gravitational_wave_grid"', ROOT)
    exec_cell(NOTEBOOKS / "Telemetry_12.ipynb", 'ANIMATION_NAME = "parker_spiral"', ROOT)
    exec_cell(NOTEBOOKS / "Telemetry_8.ipynb", 'ANIMATION_NAME = "stellar_evolution_very_massive_star"', ROOT)

    # PyVista cells: full re-render is very slow; transcode after format patch in notebook
    for name in ("math_hopf_fibration_rotation", "math_magnetar_field_hud", "math_magnetar_pulsar_telemetry_hud"):
        folder = ANIM / name
        webm = folder / f"{name}.webm"
        mp4 = folder / f"{name}.mp4"
        if webm.exists():
            ffmpeg_transcode(webm, mp4, "webm2mp4")

    # Orphan gif (notebook already outputs mp4/webm)
    hr_gif = ANIM / "telemetry_hr_diagram_v2" / "telemetry_hr_diagram_v2.gif"
    hr_webm = ANIM / "telemetry_hr_diagram_v2" / "telemetry_hr_diagram_v2_reencoded.webm"
    if hr_gif.exists():
        ffmpeg_transcode(hr_gif, hr_webm, "gif2webm")

    # Nebulacast from repo root
    exec_cell(repo_nb / "Exoplanets.ipynb", "exoplanet_signal_in_white_noise.webm", repo)
    exec_cell(repo_nb / "Exoplanets.ipynb", "exoplanet_2d_coronagraph_physical_noise.webm", repo)
    exec_cell(repo_nb / "Enceladus.ipynb", "tidal_interaction_galaxy_demo.webm", repo)
    exec_cell(repo_nb / "BORG.ipynb", "blue_monsters_deep_field_layer.webm", repo)

    # --- report ---
    threshold = 25 * 1024 * 1024
    large = []
    for path in sorted(ANIM.rglob("*")):
        if path.is_file():
            size = path.stat().st_size
            if size >= threshold:
                large.append((size, path.relative_to(ANIM)))

    print("\n" + "=" * 60)
    print(f"Files >= 25 MB remaining: {len(large)}")
    for size, rel in sorted(large, reverse=True):
        print(f"  {size / 1048576:.1f} MB\t{rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
