"""Source-time sampling shared by real-time and accelerated video exports.

Speed changes how far through a lap each output frame advances; it never
changes telemetry values, lap results, output frame rate or the result hold.
"""
from __future__ import annotations

import math


PLAYBACK_SPEEDS = (1, 2, 3, 5, 8, 10, 20)


def validate_playback_speed(value=1) -> float:
    if isinstance(value, bool):
        raise ValueError("Choose a playback speed of 1×, 2×, 3×, 5×, 8×, 10× or 20×.")
    try:
        speed = float(value)
    except (ValueError, TypeError):
        raise ValueError("Choose a playback speed of 1×, 2×, 3×, 5×, 8×, 10× or 20×.") from None
    if not math.isfinite(speed) or speed not in PLAYBACK_SPEEDS:
        raise ValueError("Choose a playback speed of 1×, 2×, 3×, 5×, 8×, 10× or 20×.")
    return speed


def source_elapsed(frame_index: int, start: float, end: float, fps: int, playback_speed=1) -> float:
    """Map a zero-based output frame to source lap seconds, clamped at finish."""
    return min(end, start + frame_index * playback_speed / fps)


def frame_count(start: float, end: float, fps: int, playback_speed=1, *, hold=False) -> int:
    speed = validate_playback_speed(playback_speed)
    return math.ceil((end - start) * fps / speed) + (1 + 2 * fps if hold else 0)
