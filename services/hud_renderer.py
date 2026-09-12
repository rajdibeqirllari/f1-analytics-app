from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import re
import shutil
import subprocess
import zipfile
from typing import Any, Callable

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


CANVAS_DEFAULT = (1080, 1920)
HUD_SIZE_PRESETS = {"Small": 360, "Medium": 460, "Large": 560}
POSITION_PRESETS = ("Bottom left", "Bottom center", "Bottom right", "Custom")

# Native HUD art is 345x345. The source speed and label sprites include some
# baked dynamic center text, so those center zones are cleared and dynamic
# values are drawn exactly once from code below.
HUD_NATIVE_SIZE = (345, 345)
CENTER_DYNAMIC_CLEAR_BOX = (88, 78, 258, 300)
SPEED_SPRITE_CLEAR_BOX = (92, 84, 258, 168)

HUD_TEXT_LAYOUT = {
    # Clean vertical center stack, in native 345px coordinates.
    "speed_center_y": 126,
    "kmh_center_y": 170,
    "rpm_value_center_y": 211,
    "rpm_label_center_y": 240,
    "gear_center_y": 276,
}
HUD_FONT_SIZES = {
    "speed": 58,
    "kmh": 16,
    "rpm": 30,
    "rpm_label": 14,
    "gear": 28,
}


@dataclass
class HUDExportResult:
    output_path: Path | None
    frames_dir: Path
    frame_count: int
    duration_sec: float
    fps: int
    format_label: str
    filename: str
    ffmpeg_command: list[str] | None = None
    ffmpeg_stdout: str = ""
    ffmpeg_stderr: str = ""


def _first_column(frame: pd.DataFrame, *names: str) -> str | None:
    lookup = {str(column).lower(): column for column in frame.columns}
    for name in names:
        if name.lower() in lookup:
            return lookup[name.lower()]
    for name in names:
        wanted = name.lower()
        for lowered, column in lookup.items():
            if wanted in lowered:
                return column
    return None


def _time_to_seconds(series: pd.Series) -> pd.Series:
    if pd.api.types.is_timedelta64_dtype(series):
        values = series.dt.total_seconds()
    else:
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().sum() >= max(1, len(series) // 2):
            values = numeric.astype(float)
        else:
            timedeltas = pd.to_timedelta(series, errors="coerce")
            if timedeltas.notna().any():
                values = timedeltas.dt.total_seconds()
            else:
                timestamps = pd.to_datetime(series, errors="coerce", utc=True)
                values = (timestamps - timestamps.iloc[0]).dt.total_seconds()
    if values.notna().any():
        values = values - float(values.dropna().iloc[0])
    return values


def _bool_like(value: Any) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return str(value).strip().lower() in {"true", "yes", "on", "active"}


def _drs_active(value: Any) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    try:
        numeric = int(float(value))
        return numeric in {1, 10, 12, 14}
    except (TypeError, ValueError):
        return _bool_like(value)


def _brake_percent(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().any():
        max_value = float(numeric.max(skipna=True) or 0)
        unique = set(numeric.dropna().astype(float).unique().tolist())
        if max_value <= 1.0 or unique.issubset({0.0, 1.0}):
            return numeric.fillna(0).map(lambda value: 100.0 if value > 0 else 0.0)
        return numeric.fillna(0).clip(0, 100)
    return series.map(lambda value: 100.0 if _bool_like(value) else 0.0)


def normalize_hud_telemetry(frame: pd.DataFrame, source: str = "Telemetry") -> pd.DataFrame:
    """Normalize FastF1/OpenF1/uploaded data to the compact HUD schema.

    Output columns are:
    t, speed_kmh, rpm, gear, throttle, brake, drs, x, y, z, source.
    """
    if frame is None or frame.empty:
        raise ValueError("The selected source returned no telemetry rows.")

    data = frame.copy()
    time_col = _first_column(data, "t", "time_sec", "Time", "SessionTime", "session_time", "Date")
    speed_col = _first_column(data, "speed_kmh", "Speed", "speed")
    if time_col is None or speed_col is None:
        raise ValueError("HUD telemetry needs at least a time column and a speed column.")

    def numeric(*names: str, default: float = 0.0) -> pd.Series:
        column = _first_column(data, *names)
        if column is None:
            return pd.Series([default] * len(data), index=data.index, dtype="float64")
        return pd.to_numeric(data[column], errors="coerce").fillna(default)

    gear = numeric("gear", "nGear", "n_gear", default=1).round().clip(1, 8).astype(int)
    throttle = numeric("throttle", "throttle_pct", "Throttle", default=0).clip(0, 100)
    brake_col = _first_column(data, "brake", "brake_active", "Brake")
    brake = _brake_percent(data[brake_col]) if brake_col else pd.Series([0.0] * len(data), index=data.index)
    drs_col = _first_column(data, "drs", "drs_active", "drs_raw", "DRS")
    drs = data[drs_col].map(_drs_active) if drs_col else pd.Series([False] * len(data), index=data.index)

    normalized = pd.DataFrame(
        {
            "t": _time_to_seconds(data[time_col]),
            "speed_kmh": pd.to_numeric(data[speed_col], errors="coerce"),
            "rpm": numeric("rpm", "RPM", default=0),
            "gear": gear,
            "throttle": throttle,
            "brake": brake.clip(0, 100),
            "drs": drs.astype(bool),
            "x": numeric("x", "X", default=0),
            "y": numeric("y", "Y", default=0),
            "z": numeric("z", "Z", default=0),
            "source": source,
        }
    )
    normalized = (
        normalized.dropna(subset=["t", "speed_kmh"])
        .sort_values("t")
        .drop_duplicates("t", keep="last")
        .reset_index(drop=True)
    )
    if normalized.empty:
        raise ValueError("Telemetry was loaded, but no valid timestamped HUD rows remained.")
    return normalized


def telemetry_duration(frame: pd.DataFrame) -> float:
    if frame is None or frame.empty or "t" not in frame:
        return 0.0
    return max(0.0, float(pd.to_numeric(frame["t"], errors="coerce").max() or 0.0))


def frame_count_for_duration(duration_sec: float, fps: int) -> int:
    return max(1, int(round(float(duration_sec) * int(fps))))


def sample_telemetry_at(frame: pd.DataFrame, t: float) -> dict[str, Any]:
    if frame is None or frame.empty:
        raise ValueError("Cannot sample an empty telemetry frame.")
    data = frame.sort_values("t").reset_index(drop=True)
    times = data["t"].astype(float).to_numpy()
    if len(times) == 1:
        row = data.iloc[0].to_dict()
        row["t"] = float(t)
        return row

    clamped_t = float(np.clip(t, times[0], times[-1]))
    continuous = {}
    for column in ("speed_kmh", "rpm", "throttle", "brake", "x", "y", "z"):
        continuous[column] = float(np.interp(clamped_t, times, pd.to_numeric(data[column], errors="coerce").fillna(0)))

    nearest_index = int(np.abs(times - clamped_t).argmin())
    nearest = data.iloc[nearest_index]
    return {
        "t": clamped_t,
        **continuous,
        "gear": int(np.clip(int(nearest.get("gear", 1) or 1), 1, 8)),
        "drs": bool(nearest.get("drs", False)),
        "source": nearest.get("source", "Telemetry"),
    }


def _scan_numbered_assets(assets_dir: Path, prefix: str) -> dict[int, Path]:
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)\.png$", re.IGNORECASE)
    matches: dict[int, Path] = {}
    for path in assets_dir.glob(f"{prefix}_*.png"):
        found = pattern.match(path.name)
        if found:
            matches[int(found.group(1))] = path
    return dict(sorted(matches.items()))


def _load_rgba(path: Path | None) -> Image.Image | None:
    if path is None or not path.exists():
        return None
    return Image.open(path).convert("RGBA")


def _clear_box(image: Image.Image | None, box: tuple[int, int, int, int]) -> Image.Image | None:
    """Return a copy with one rectangular zone made transparent."""
    if image is None:
        return None
    cleaned = image.copy()
    transparent = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), (0, 0, 0, 0))
    cleaned.paste(transparent, box)
    return cleaned


def _clear_boxes(image: Image.Image | None, boxes: list[tuple[int, int, int, int]]) -> Image.Image | None:
    cleaned = image
    for box in boxes:
        cleaned = _clear_box(cleaned, box)
    return cleaned


def _font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "arialbd.ttf" if bold else "arial.ttf",
        "segoeuib.ttf" if bold else "segoeui.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


class SpriteHUD:
    def __init__(self, assets_dir: Path):
        self.assets_dir = Path(assets_dir)
        self.background = _load_rgba(self.assets_dir / "background.png")
        label_asset = _load_rgba(
            self.assets_dir / "labels_clean.png"
            if (self.assets_dir / "labels_clean.png").exists()
            else self.assets_dir / "labels.png"
        )
        self.labels = _clear_box(label_asset, CENTER_DYNAMIC_CLEAR_BOX)
        self.speed_assets = {
            idx: _clear_box(_load_rgba(path), SPEED_SPRITE_CLEAR_BOX)
            for idx, path in _scan_numbered_assets(self.assets_dir, "speed").items()
        }
        self.throttle_assets = {idx: _load_rgba(path) for idx, path in _scan_numbered_assets(self.assets_dir, "throttle").items()}
        self.brake_assets = {idx: _load_rgba(path) for idx, path in _scan_numbered_assets(self.assets_dir, "brake").items()}
        self.gear_assets = {
            idx: _load_rgba(self.assets_dir / f"gear_{idx}.png")
            for idx in range(1, 9)
            if (self.assets_dir / f"gear_{idx}.png").exists()
        }
        self.rpm_digits = {
            idx: _load_rgba(self.assets_dir / f"rpm_digits_{idx}.png")
            for idx in range(10)
            if (self.assets_dir / f"rpm_digits_{idx}.png").exists()
        }
        base = self.background or self.labels or next((img for img in self.speed_assets.values() if img), None)
        self.base_size = base.size if base is not None else (345, 345)

    def _asset_for_value(self, assets: dict[int, Image.Image | None], value: float, *, value_max: float | None = None) -> Image.Image | None:
        keys = [idx for idx, image in assets.items() if image is not None]
        if not keys:
            return None
        min_idx, max_idx = min(keys), max(keys)
        if value_max is None:
            index = int(round(float(value)))
        else:
            pct = np.clip(float(value), 0, value_max) / float(value_max)
            index = int(round(min_idx + pct * (max_idx - min_idx)))
        index = int(np.clip(index, min_idx, max_idx))
        if index in assets and assets[index] is not None:
            return assets[index]
        closest = min(keys, key=lambda candidate: abs(candidate - index))
        return assets[closest]

    def _paste_centered(self, canvas: Image.Image, sprite: Image.Image, center: tuple[int, int], scale: float = 1.0) -> None:
        image = sprite
        if scale != 1.0:
            image = sprite.resize(
                (max(1, int(round(sprite.width * scale))), max(1, int(round(sprite.height * scale)))),
                Image.Resampling.LANCZOS,
            )
        x = int(round(center[0] - image.width / 2))
        y = int(round(center[1] - image.height / 2))
        canvas.alpha_composite(image, (x, y))

    def _draw_center_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        center_x: int,
        y: int,
        font: ImageFont.ImageFont,
        fill: tuple[int, int, int, int] = (255, 255, 255, 255),
        stroke_width: int = 2,
    ) -> None:
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
        draw.text(
            (center_x - (bbox[2] - bbox[0]) / 2, y),
            text,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0, 190),
        )

    def _draw_centered_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        *,
        center_x: int,
        center_y: int,
        size: int,
        bold: bool = True,
        max_width: int = 150,
        fill: tuple[int, int, int, int] = (255, 255, 255, 255),
        stroke_width: int = 2,
    ) -> None:
        """Draw one centered text value, shrinking if needed to stay in its zone."""
        font_size = int(size)
        while font_size > 8:
            font = _font(font_size, bold=bold)
            bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
            if (bbox[2] - bbox[0]) <= max_width:
                break
            font_size -= 1
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        draw.text(
            (center_x - width / 2 - bbox[0], center_y - height / 2 - bbox[1]),
            text,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0, 185),
        )

    def render_rgba(self, tel_row: dict[str, Any], *, hud_year: int | None = None) -> np.ndarray:
        canvas = Image.new("RGBA", self.base_size, (0, 0, 0, 0))
        # DRS remains available in telemetry, but the clean HUD layout never
        # renders a DRS asset, label, or reserved spacing for any year.
        for layer in (
            self.background,
            self._asset_for_value(self.speed_assets, float(tel_row.get("speed_kmh", 0) or 0)),
            self._asset_for_value(self.throttle_assets, float(tel_row.get("throttle", 0) or 0), value_max=100),
            self._asset_for_value(self.brake_assets, float(tel_row.get("brake", 0) or 0), value_max=100),
            self.labels,
        ):
            if layer is not None:
                canvas.alpha_composite(layer)

        draw = ImageDraw.Draw(canvas)
        center_x = self.base_size[0] // 2
        speed = int(round(float(tel_row.get("speed_kmh", 0) or 0)))
        rpm = int(round(float(tel_row.get("rpm", 0) or 0)))
        gear = int(np.clip(int(tel_row.get("gear", 1) or 1), 1, 8))

        # Dynamic center stack. These values are the only source for center text:
        # the sprite layers have their baked speed/KMH/RPM zones cleared above.
        self._draw_centered_text(
            draw,
            f"{speed}",
            center_x=center_x,
            center_y=HUD_TEXT_LAYOUT["speed_center_y"],
            size=HUD_FONT_SIZES["speed"],
            max_width=148,
            stroke_width=3,
        )
        self._draw_centered_text(
            draw,
            "KMH",
            center_x=center_x,
            center_y=HUD_TEXT_LAYOUT["kmh_center_y"],
            size=HUD_FONT_SIZES["kmh"],
            max_width=70,
            fill=(230, 236, 244, 240),
            stroke_width=1,
        )
        rpm_text = f"{rpm:05d}" if rpm > 0 else "00000"
        self._draw_centered_text(
            draw,
            rpm_text,
            center_x=center_x,
            center_y=HUD_TEXT_LAYOUT["rpm_value_center_y"],
            size=HUD_FONT_SIZES["rpm"],
            max_width=142,
            stroke_width=2,
        )
        self._draw_centered_text(
            draw,
            "RPM",
            center_x=center_x,
            center_y=HUD_TEXT_LAYOUT["rpm_label_center_y"],
            size=HUD_FONT_SIZES["rpm_label"],
            max_width=62,
            fill=(230, 236, 244, 235),
            stroke_width=1,
        )
        self._draw_centered_text(
            draw,
            str(gear),
            center_x=center_x,
            center_y=HUD_TEXT_LAYOUT["gear_center_y"],
            size=HUD_FONT_SIZES["gear"],
            max_width=40,
            stroke_width=2,
        )
        return np.asarray(canvas)


def render_canvas_frame(
    hud: SpriteHUD,
    tel_row: dict[str, Any],
    *,
    canvas_size: tuple[int, int] = CANVAS_DEFAULT,
    hud_width: int = 460,
    position: tuple[int, int] = (80, 1180),
    hud_year: int | None = None,
) -> np.ndarray:
    hud_image = Image.fromarray(hud.render_rgba(tel_row, hud_year=hud_year), mode="RGBA")
    scale = max(1, int(hud_width)) / hud_image.width
    hud_image = hud_image.resize(
        (int(round(hud_image.width * scale)), int(round(hud_image.height * scale))),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGBA", tuple(canvas_size), (0, 0, 0, 0))
    x = int(position[0])
    y = int(position[1])
    x = int(np.clip(x, 0, max(0, canvas.width - hud_image.width)))
    y = int(np.clip(y, 0, max(0, canvas.height - hud_image.height)))
    canvas.alpha_composite(hud_image, (x, y))
    return np.asarray(canvas)


def resolve_hud_position(
    preset: str,
    *,
    canvas_size: tuple[int, int],
    hud_width: int,
    hud_native_size: tuple[int, int] = (345, 345),
    custom_x: int | None = None,
    custom_y: int | None = None,
) -> tuple[int, int]:
    canvas_width, _ = canvas_size
    hud_height = int(round(hud_native_size[1] * (int(hud_width) / hud_native_size[0])))
    del hud_height
    if preset == "Bottom center":
        return (int(round((canvas_width - int(hud_width)) / 2)), 1180)
    if preset == "Bottom right":
        return (int(round(canvas_width - int(hud_width) - 80)), 1180)
    if preset == "Custom":
        return (int(custom_x if custom_x is not None else 80), int(custom_y if custom_y is not None else 1180))
    return (80, 1180)


def build_hud_preview_frame(
    telemetry: pd.DataFrame,
    assets_dir: Path,
    *,
    canvas_size: tuple[int, int] = CANVAS_DEFAULT,
    hud_width: int = 460,
    position_preset: str = "Bottom left",
    custom_x: int | None = None,
    custom_y: int | None = None,
    at_time: float | None = None,
    hud_year: int | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    hud = SpriteHUD(assets_dir)
    duration = telemetry_duration(telemetry)
    t = duration / 2 if at_time is None else float(at_time)
    row = sample_telemetry_at(telemetry, t)
    position = resolve_hud_position(
        position_preset,
        canvas_size=canvas_size,
        hud_width=hud_width,
        hud_native_size=hud.base_size,
        custom_x=custom_x,
        custom_y=custom_y,
    )
    return (
        render_canvas_frame(hud, row, canvas_size=canvas_size, hud_width=hud_width, position=position, hud_year=hud_year),
        row,
    )


def checkerboard_preview(frame_rgba: np.ndarray, *, crop_to_alpha: bool = True, padding: int = 42) -> Image.Image:
    image = Image.fromarray(frame_rgba, mode="RGBA")
    if crop_to_alpha:
        alpha_box = image.getchannel("A").getbbox()
        if alpha_box:
            left = max(0, alpha_box[0] - padding)
            top = max(0, alpha_box[1] - padding)
            right = min(image.width, alpha_box[2] + padding)
            bottom = min(image.height, alpha_box[3] + padding)
            image = image.crop((left, top, right, bottom))
    tile = 28
    board = Image.new("RGBA", image.size, (21, 25, 34, 255))
    draw = ImageDraw.Draw(board)
    for y in range(0, board.height, tile):
        for x in range(0, board.width, tile):
            if (x // tile + y // tile) % 2 == 0:
                draw.rectangle((x, y, x + tile - 1, y + tile - 1), fill=(43, 49, 63, 255))
    board.alpha_composite(image)
    return board


def ffmpeg_available() -> tuple[bool, str]:
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=12)
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    version = result.stdout.splitlines()[0] if result.stdout else result.stderr.splitlines()[0] if result.stderr else ""
    return result.returncode == 0, version


def _write_png_sequence(
    telemetry: pd.DataFrame,
    assets_dir: Path,
    frames_dir: Path,
    *,
    fps: int,
    canvas_size: tuple[int, int],
    hud_width: int,
    position_preset: str,
    custom_x: int | None,
    custom_y: int | None,
    hud_year: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[int, float]:
    frames_dir.mkdir(parents=True, exist_ok=True)
    hud = SpriteHUD(assets_dir)
    duration = telemetry_duration(telemetry)
    frame_count = frame_count_for_duration(duration, fps)
    position = resolve_hud_position(
        position_preset,
        canvas_size=canvas_size,
        hud_width=hud_width,
        hud_native_size=hud.base_size,
        custom_x=custom_x,
        custom_y=custom_y,
    )
    for frame_index in range(frame_count):
        row = sample_telemetry_at(telemetry, frame_index / int(fps))
        frame = render_canvas_frame(hud, row, canvas_size=canvas_size, hud_width=hud_width, position=position, hud_year=hud_year)
        Image.fromarray(frame, mode="RGBA").save(frames_dir / f"frame_{frame_index:06d}.png", compress_level=3)
        if progress_callback and (frame_index % max(1, frame_count // 100) == 0 or frame_index == frame_count - 1):
            progress_callback(frame_index + 1, frame_count)
    return frame_count, duration


def export_hud_png_sequence(
    telemetry: pd.DataFrame,
    assets_dir: Path,
    frames_root: Path,
    safe_label: str,
    *,
    fps: int = 30,
    canvas_size: tuple[int, int] = CANVAS_DEFAULT,
    hud_width: int = 460,
    position_preset: str = "Bottom left",
    custom_x: int | None = None,
    custom_y: int | None = None,
    hud_year: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> HUDExportResult:
    frames_dir = Path(frames_root) / safe_label
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frame_count, duration = _write_png_sequence(
        telemetry,
        assets_dir,
        frames_dir,
        fps=fps,
        canvas_size=canvas_size,
        hud_width=hud_width,
        position_preset=position_preset,
        custom_x=custom_x,
        custom_y=custom_y,
        hud_year=hud_year,
        progress_callback=progress_callback,
    )
    return HUDExportResult(
        output_path=None,
        frames_dir=frames_dir,
        frame_count=frame_count,
        duration_sec=duration,
        fps=fps,
        format_label="PNG Sequence",
        filename=safe_label,
    )


def export_hud_alpha_video(
    telemetry: pd.DataFrame,
    assets_dir: Path,
    exports_dir: Path,
    frames_root: Path,
    safe_label: str,
    *,
    fps: int = 30,
    format_label: str = "WebM VP9 Alpha",
    canvas_size: tuple[int, int] = CANVAS_DEFAULT,
    hud_width: int = 460,
    position_preset: str = "Bottom left",
    custom_x: int | None = None,
    custom_y: int | None = None,
    hud_year: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> HUDExportResult:
    available, version = ffmpeg_available()
    if not available:
        raise RuntimeError(f"ffmpeg was not found. Export PNG Sequence instead. Details: {version}")

    exports_dir = Path(exports_dir)
    exports_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = Path(frames_root) / safe_label
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frame_count, duration = _write_png_sequence(
        telemetry,
        assets_dir,
        frames_dir,
        fps=fps,
        canvas_size=canvas_size,
        hud_width=hud_width,
        position_preset=position_preset,
        custom_x=custom_x,
        custom_y=custom_y,
        hud_year=hud_year,
        progress_callback=progress_callback,
    )

    if format_label == "MOV ProRes 4444":
        output_path = exports_dir / f"{safe_label}.mov"
        command = [
            "ffmpeg",
            "-y",
            "-framerate",
            str(int(fps)),
            "-i",
            str(frames_dir / "frame_%06d.png"),
            "-c:v",
            "prores_ks",
            "-profile:v",
            "4444",
            "-pix_fmt",
            "yuva444p10le",
            str(output_path),
        ]
    else:
        output_path = exports_dir / f"{safe_label}.webm"
        command = [
            "ffmpeg",
            "-y",
            "-framerate",
            str(int(fps)),
            "-i",
            str(frames_dir / "frame_%06d.png"),
            "-c:v",
            "libvpx-vp9",
            "-pix_fmt",
            "yuva420p",
            "-auto-alt-ref",
            "0",
            str(output_path),
        ]

    result = subprocess.run(command, capture_output=True, text=True, timeout=max(120, int(duration * 8)))
    if result.returncode != 0 or not output_path.exists() or output_path.stat().st_size <= 0:
        raise RuntimeError(
            "ffmpeg could not create the alpha video. "
            "Use WebM VP9 Alpha or PNG Sequence if MOV is unavailable.\n\n"
            + result.stderr
        )
    return HUDExportResult(
        output_path=output_path,
        frames_dir=frames_dir,
        frame_count=frame_count,
        duration_sec=duration,
        fps=fps,
        format_label=format_label,
        filename=output_path.name,
        ffmpeg_command=command,
        ffmpeg_stdout=result.stdout,
        ffmpeg_stderr=result.stderr,
    )


def zip_png_sequence(frames_dir: Path) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(Path(frames_dir).glob("frame_*.png")):
            archive.write(path, arcname=path.name)
    return buffer.getvalue()


def format_duration(seconds: float) -> str:
    minutes, remainder = divmod(max(0, int(round(seconds))), 60)
    return f"{minutes}:{remainder:02d}"
