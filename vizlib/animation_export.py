from __future__ import annotations

from pathlib import Path
from typing import Iterable, Literal
import shutil
import subprocess

import numpy as np
import imageio.v2 as imageio


OutputFormat = Literal["webm", "gif", "mp4"]


def normalize_output_format(fmt: str) -> OutputFormat:
    fmt = fmt.lower().strip()

    if fmt not in {"webm", "gif", "mp4"}:
        raise ValueError("output_format must be one of: webm, gif, mp4")

    return fmt  # type: ignore[return-value]


def ensure_out_dir(path: str | Path) -> Path:
    out_dir = Path(path)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg not found. Install it first:\n"
            "  macOS: brew install ffmpeg\n"
            "  conda: conda install -c conda-forge ffmpeg"
        )


def _validate_frames(frames: list[np.ndarray], *, alpha: bool) -> None:
    if not frames:
        raise ValueError("frames list is empty")

    first_shape = frames[0].shape

    if len(first_shape) != 3 or first_shape[2] not in {3, 4}:
        raise ValueError(
            "frames must be RGB/RGBA uint8 arrays with shape (H, W, 3) or (H, W, 4)"
        )

    if alpha and first_shape[2] != 4:
        raise ValueError(
            "alpha=True requires RGBA frames with shape (H, W, 4). "
            "Current frames do not contain an alpha channel."
        )

    for i, frame in enumerate(frames):
        if frame.dtype != np.uint8:
            raise ValueError(f"frame #{i} dtype must be uint8, got {frame.dtype}")

        if frame.shape != first_shape:
            raise ValueError(
                f"all frames must have the same shape. "
                f"frame #0={first_shape}, frame #{i}={frame.shape}"
            )


def _frames_to_temp_pngs(
    frames: Iterable[np.ndarray],
    frame_dir: Path,
) -> None:
    frame_dir.mkdir(parents=True, exist_ok=True)

    for i, frame in enumerate(frames):
        imageio.imwrite(frame_dir / f"frame_{i:04d}.png", frame)


def _export_webm_ffmpeg(
    frame_dir: Path,
    out_file: Path,
    fps: int,
    crf: int = 32,
    alpha: bool = False,
) -> None:
    require_ffmpeg()

    pix_fmt = "yuva420p" if alpha else "yuv420p"

    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", str(frame_dir / "frame_%04d.png"),
        "-c:v", "libvpx-vp9",
        "-crf", str(crf),
        "-b:v", "0",
        "-pix_fmt", pix_fmt,
        "-row-mt", "1",
    ]

    if alpha:
        cmd += [
            "-auto-alt-ref", "0",
        ]

    cmd.append(str(out_file))

    subprocess.run(cmd, check=True)


def _export_mp4_ffmpeg(
    frame_dir: Path,
    out_file: Path,
    fps: int,
    crf: int = 20,
) -> None:
    require_ffmpeg()

    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", str(frame_dir / "frame_%04d.png"),
        "-c:v", "libx264",
        "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(out_file),
    ]

    subprocess.run(cmd, check=True)


def _export_gif_imageio(
    frames: list[np.ndarray],
    out_file: Path,
    fps: int,
) -> None:
    imageio.mimsave(
        out_file,
        frames,
        fps=fps,
        loop=0,
    )


def export_animation(
    frames: list[np.ndarray],
    out_dir: str | Path,
    animation_name: str,
    output_format: str,
    fps: int,
    cleanup_frames: bool = True,
    webm_crf: int = 32,
    mp4_crf: int = 20,
    alpha: bool = False,
) -> Path:
    """
    Export animation frames to webm/gif/mp4.

    Expected frame format:
      - list[np.ndarray]
      - RGB uint8 frames: shape (H, W, 3)
      - RGBA uint8 frames: shape (H, W, 4)

    Alpha support:
      - webm + alpha=True supports transparency via VP9 + yuva420p
      - mp4 does not support transparency in this H.264 export path
      - gif alpha is not recommended for HUD overlays

    Output:
      <out_dir>/<animation_name>.<format>
    """

    fmt = normalize_output_format(output_format)
    _validate_frames(frames, alpha=alpha)

    if alpha and fmt != "webm":
        raise ValueError(
            "alpha=True is supported only for output_format='webm'. "
            "Use webm for transparent HUD overlays."
        )

    out_dir = ensure_out_dir(out_dir)
    out_file = out_dir / f"{animation_name}.{fmt}"

    if fmt == "gif":
        _export_gif_imageio(frames, out_file, fps)
        return out_file

    frame_dir = out_dir / "_frames_export"

    if frame_dir.exists():
        shutil.rmtree(frame_dir)

    try:
        _frames_to_temp_pngs(frames, frame_dir)

        if fmt == "webm":
            _export_webm_ffmpeg(
                frame_dir=frame_dir,
                out_file=out_file,
                fps=fps,
                crf=webm_crf,
                alpha=alpha,
            )

        elif fmt == "mp4":
            _export_mp4_ffmpeg(
                frame_dir=frame_dir,
                out_file=out_file,
                fps=fps,
                crf=mp4_crf,
            )

    finally:
        if cleanup_frames:
            shutil.rmtree(frame_dir, ignore_errors=True)

    return out_file