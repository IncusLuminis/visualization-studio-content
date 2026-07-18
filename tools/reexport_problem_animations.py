#!/usr/bin/env python3
"""Re-export problem overlay/HUD animations with stable dark backgrounds."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = Path("/Users/mloktionov/anaconda3/bin/python")

GIF_SAVE_BLOCK = re.compile(
    r'OUT = OUT_DIR / "(?P<name>[^"]+)\.gif"\s+'
    r'frames\[0\]\.save\(\s+'
    r'OUT,\s+'
    r'save_all=True,\s+'
    r'append_images=frames\[1:\],\s+'
    r'duration=int\(1000 / FPS\),\s+'
    r'loop=0,\s+'
    r'disposal=2,\s+'
    r'transparency=0,\s+'
    r'\)\s+'
    r'print\(f"Saved: \{OUT\}"\)',
    re.DOTALL,
)

WEBM_EXPORT_BLOCK = '''import numpy as np
from vizlib.animation_export import export_animation

saved = export_animation(
    [np.asarray(frame.convert("RGBA")) for frame in frames],
    OUT_DIR,
    "{name}",
    "webm",
    FPS,
)
print(f"Saved: {{saved}}")'''


def load_nb(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_nb(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def cell_text(cell: dict) -> str:
    src = cell.get("source", [])
    return src if isinstance(src, str) else "".join(src)


def set_cell_text(cell: dict, text: str) -> None:
    cell["source"] = [line + "\n" for line in text.splitlines(True)]


def run_cell(nb_path: Path, cell_idx: int) -> None:
    data = load_nb(nb_path)
    cell = data["cells"][cell_idx]
    code = cell_text(cell)
    label = f"{nb_path.name} cell {cell_idx}"
    print(f"\n{'=' * 60}\n[RUN] {label}\n{'=' * 60}")
    proc = subprocess.run([str(PY), "-c", code], cwd=ROOT, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{label} failed with exit {proc.returncode}")


def patch_telemetry_1() -> list[int]:
    nb_path = ROOT / "Telemetry_1.ipynb"
    data = load_nb(nb_path)
    patched = []

    signal_helper = '''def save_signal_anim(mode, animation_name):
    frames = [render_frame(i, mode=mode) for i in range(FRAMES)]
    import numpy as np
    from vizlib.animation_export import export_animation
    saved = export_animation(
        [np.asarray(frame.convert("RGBA")) for frame in frames],
        OUT_DIR,
        animation_name,
        "webm",
        FPS,
    )
    print(f"Saved: {saved}")


save_signal_anim("reveal", "signal_intercept_reveal")
save_signal_anim("idle", "signal_intercept_idle")
save_signal_anim("reveal", "signal_intercept")

print("Done.")'''

    for i, cell in enumerate(data["cells"]):
        if cell.get("cell_type") != "code":
            continue
        text = cell_text(cell)
        if "save_signal_gif(" in text:
            text = re.sub(
                r"# Save helper.*?print\(\"Done\.\"\)",
                "# Save helper\n" + signal_helper,
                text,
                flags=re.DOTALL,
            )
            set_cell_text(cell, text)
            patched.append(i)
            continue

        new_text, n = GIF_SAVE_BLOCK.subn(
            lambda m: WEBM_EXPORT_BLOCK.format(name=Path(m.group("name")).stem),
            text,
        )
        if n:
            set_cell_text(cell, new_text)
            patched.append(i)

    save_nb(nb_path, data)
    print(f"Patched Telemetry_1.ipynb: cells {patched}")
    return patched


def patch_telemetry_6() -> None:
    nb_path = ROOT / "Telemetry_6.ipynb"
    data = load_nb(nb_path)
    for cell in data["cells"]:
        if cell.get("cell_type") != "code":
            continue
        text = cell_text(cell)
        if 'OUTPUT_FORMAT = "gif"' in text and "telemetry_celestial_sphere_3d" in text:
            text = text.replace('OUTPUT_FORMAT = "gif"', 'OUTPUT_FORMAT = "webm"')
            text = text.replace(
                "    d.polygon(pts, fill=(*SA_CYAN, 32))\n",
                "    # outline only — avoid solid cyan disc fill in webm\n",
            )
            set_cell_text(cell, text)
    save_nb(nb_path, data)
    print("Patched Telemetry_6.ipynb")


def patch_telemetry_14() -> list[int]:
    nb_path = ROOT / "Telemetry_14.ipynb"
    data = load_nb(nb_path)
    patched = []
    replacements = [
        (
            "panel_bg = Rectangle(\n\n    (panel_x, panel_y),\n\n    panel_w,\n\n    panel_h,\n\n    fill=True,\n",
            "panel_bg = Rectangle(\n\n    (panel_x, panel_y),\n\n    panel_w,\n\n    panel_h,\n\n    fill=False,\n",
        ),
        (
            "frame = Rectangle(\n\n    (0.8, 1.0),\n\n    14.4,\n\n    7.0,\n\n    fill=True,\n",
            "frame = Rectangle(\n\n    (0.8, 1.0),\n\n    14.4,\n\n    7.0,\n\n    fill=False,\n",
        ),
        (
            "planet_fill = Circle(\n\n    CENTER,\n\n    R,\n\n    fill=True,\n",
            "planet_fill = Circle(\n\n    CENTER,\n\n    R,\n\n    fill=False,\n",
        ),
        (
            "sweep_sector = Wedge(\n\n    CENTER,\n\n    R_MAX,\n\n    theta1=0,\n\n    theta2=38,\n\n    facecolor=COL,\n\n    edgecolor=None,\n\n    alpha=0.08,\n",
            "sweep_sector = Wedge(\n\n    CENTER,\n\n    R_MAX,\n\n    theta1=0,\n\n    theta2=38,\n\n    facecolor=COL,\n\n    edgecolor=None,\n\n    alpha=0.0,\n\n    fill=False,\n",
        ),
    ]

    for i, cell in enumerate(data["cells"]):
        if cell.get("cell_type") != "code":
            continue
        text = cell_text(cell)
        original = text
        for old, new in replacements:
            text = text.replace(old, new)
        if text != original:
            set_cell_text(cell, text)
            patched.append(i)

    save_nb(nb_path, data)
    print(f"Patched Telemetry_14.ipynb: cells {patched}")
    return patched


def main() -> int:
    t1_cells = patch_telemetry_1()
    patch_telemetry_6()
    t14_cells = patch_telemetry_14()

    # Telemetry_1 overlays with gif disposal flicker
    for idx in [4, 6, 8, 12, 18]:
        run_cell(ROOT / "Telemetry_1.ipynb", idx)

    run_cell(ROOT / "Telemetry_6.ipynb", 0)

    for idx in [3, 8, 12]:
        run_cell(ROOT / "Telemetry_14.ipynb", idx)

    print("\nAll re-exports finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
