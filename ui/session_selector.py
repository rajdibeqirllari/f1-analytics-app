from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import streamlit as st


SESSION_TYPES = ["Race", "Sprint", "Qualifying", "Sprint Qualifying"]
SESSION_CODES = {"Race": "R", "Sprint": "S", "Qualifying": "Q", "Sprint Qualifying": "SQ"}
RACE_SESSION_CODES = ["FP1", "FP2", "FP3", "Q", "R", "SQ", "S"]
IMAGE_FORMATS = ["16:9 (YouTube)", "1:1 (Instagram)", "9:16 (TikTok)"]
COLOR_MODES = ["FastF1 Official", "Custom", "Monochrome"]
DATA_SOURCES = ["Auto", "FastF1", "OpenF1", "Upload CSV"]


def _option_index(options: Sequence[Any], value: Any, fallback: int = 0) -> int:
    try:
        return list(options).index(value)
    except ValueError:
        return fallback


def _state(key: str, default: Any) -> Any:
    return st.session_state.get(key, default)


def render_session_selector(
    workspace: str,
    *,
    event_options: Sequence[str],
    driver_options: Sequence[str],
    latest_year: int,
    latest_event: str,
    key_prefix: str | None = None,
) -> dict[str, Any]:
    """Render the shared compact selector and return one stable selection dict.

    Workspace-specific controls are intentionally hidden unless that workspace
    needs them, while the underlying state keys remain shared across tabs.
    """
    prefix = key_prefix or workspace.lower().replace(" ", "_")
    event_options = list(event_options) or [latest_event]
    driver_options = list(driver_options) or ["VER", "NOR", "LEC", "RUS"]

    default_mode = _state("selector_mode", "Race Weekend")
    default_year = int(_state("selector_year", latest_year))
    default_event = _state("selector_event", latest_event)
    if default_event not in event_options:
        default_event = latest_event if latest_event in event_options else event_options[0]
    default_session = _state("selector_session", "R")
    if default_session not in RACE_SESSION_CODES:
        default_session = "R"

    fields = {
        "Analytics": ("mode", "year", "event", "session", "driver_a", "driver_b"),
        "Telemetry Export": ("mode", "year", "event", "session", "driver", "lap", "fps", "source"),
        "Live Timing": ("year", "event", "session"),
        "Race Replay": ("year", "event", "replay_session", "sample_rate", "refresh"),
        "Radio": ("year", "event", "session", "refresh"),
    }.get(workspace, ("year", "event", "session"))

    values: dict[str, Any] = {}
    column_count = max(1, len(fields))
    widths = [1.0] * column_count
    if "event" in fields:
        widths[fields.index("event")] = 1.75
    if workspace == "Analytics":
        widths.extend([1.0, 1.0])
    # Keep long selectors readable in the studio and on narrower screens.
    columns = []
    for start in range(0, len(widths), 4):
        columns.extend(st.columns(widths[start:start + 4]))

    for idx, field in enumerate(fields):
        with columns[idx]:
            if field == "mode":
                values["mode"] = st.selectbox(
                    "Mode",
                    ["Race Weekend", "Pre-season Testing"],
                    index=_option_index(["Race Weekend", "Pre-season Testing"], default_mode),
                    key=f"{prefix}_mode",
                )
                st.session_state["selector_mode"] = values["mode"]
            elif field == "year":
                values["year"] = int(
                    st.number_input(
                        "Year",
                        min_value=2018,
                        max_value=2035,
                        value=default_year,
                        step=1,
                        key=f"{prefix}_year",
                    )
                )
                st.session_state["selector_year"] = values["year"]
            elif field == "event":
                values["event"] = st.selectbox(
                    "Event",
                    event_options,
                    index=_option_index(event_options, default_event),
                    key=f"{prefix}_event",
                )
                st.session_state["selector_event"] = values["event"]
            elif field == "session":
                values["session"] = st.selectbox(
                    "Session",
                    RACE_SESSION_CODES,
                    index=_option_index(RACE_SESSION_CODES, default_session, 4),
                    key=f"{prefix}_session",
                )
                st.session_state["selector_session"] = values["session"]
            elif field == "driver":
                default = _state("selector_driver", driver_options[0])
                values["driver"] = st.selectbox(
                    "Driver",
                    driver_options,
                    index=_option_index(driver_options, default),
                    key=f"{prefix}_driver",
                )
                st.session_state["selector_driver"] = values["driver"]
            elif field == "driver_a":
                default = _state("selector_driver_a", driver_options[0])
                values["driver_a"] = st.selectbox(
                    "Driver A",
                    driver_options,
                    index=_option_index(driver_options, default),
                    key=f"{prefix}_driver_a",
                )
                st.session_state["selector_driver_a"] = values["driver_a"]
            elif field == "driver_b":
                fallback = 1 if len(driver_options) > 1 else 0
                default = _state("selector_driver_b", driver_options[fallback])
                values["driver_b"] = st.selectbox(
                    "Driver B",
                    driver_options,
                    index=_option_index(driver_options, default, fallback),
                    key=f"{prefix}_driver_b",
                )
                st.session_state["selector_driver_b"] = values["driver_b"]
            elif field == "lap":
                values["lap"] = st.selectbox(
                    "Lap",
                    ["Fastest", "Lap number"],
                    index=_option_index(["Fastest", "Lap number"], _state("selector_lap", "Fastest")),
                    key=f"{prefix}_lap",
                )
                st.session_state["selector_lap"] = values["lap"]
            elif field == "fps":
                values["fps"] = st.selectbox(
                    "Export FPS",
                    [25, 30, 50, 60],
                    index=_option_index([25, 30, 50, 60], int(_state("export_fps", 30)), 1),
                    key=f"{prefix}_fps",
                )
                st.session_state["export_fps"] = values["fps"]
            elif field == "source":
                values["source"] = st.selectbox(
                    "Source",
                    DATA_SOURCES,
                    index=_option_index(DATA_SOURCES, _state("telemetry_source", "Auto")),
                    key=f"{prefix}_source",
                )
                st.session_state["telemetry_source"] = values["source"]
            elif field == "replay_session":
                values["session_type"] = st.selectbox(
                    "Session type",
                    SESSION_TYPES,
                    index=_option_index(SESSION_TYPES, _state("replay_session_type", "Race")),
                    key=f"{prefix}_session_type",
                )
                st.session_state["replay_session_type"] = values["session_type"]
            elif field == "sample_rate":
                values["sample_rate"] = st.selectbox(
                    "Sample rate",
                    [4, 5, 8, 10],
                    index=_option_index([4, 5, 8, 10], int(_state("replay_rate", 5)), 1),
                    format_func=lambda value: f"{value} Hz",
                    key=f"{prefix}_sample_rate",
                )
                st.session_state["replay_rate"] = values["sample_rate"]
            elif field == "refresh":
                values["refresh"] = st.checkbox(
                    "Refresh cache",
                    value=bool(_state(f"{prefix}_refresh_value", False)),
                    key=f"{prefix}_refresh",
                )
                st.session_state[f"{prefix}_refresh_value"] = values["refresh"]

    if workspace == "Analytics":
        aux = columns[len(fields):]
        with aux[0]:
            values["image_format"] = st.selectbox(
                "Image format",
                IMAGE_FORMATS,
                index=_option_index(IMAGE_FORMATS, _state("image_format", IMAGE_FORMATS[0])),
                key=f"{prefix}_image_format",
            )
            st.session_state["image_format"] = values["image_format"]
        with aux[1]:
            values["color_mode"] = st.selectbox(
                "Color mode",
                COLOR_MODES,
                index=_option_index(COLOR_MODES, _state("color_mode", COLOR_MODES[0])),
                key=f"{prefix}_color_mode",
            )
            st.session_state["color_mode"] = values["color_mode"]

    values.setdefault("mode", default_mode)
    values.setdefault("year", default_year)
    values.setdefault("event", default_event)
    values.setdefault("session", default_session)
    values.setdefault("driver", _state("selector_driver", driver_options[0]))
    values.setdefault("driver_a", _state("selector_driver_a", driver_options[0]))
    values.setdefault(
        "driver_b",
        _state("selector_driver_b", driver_options[1] if len(driver_options) > 1 else driver_options[0]),
    )
    values.setdefault("lap", _state("selector_lap", "Fastest"))
    values.setdefault("fps", int(_state("export_fps", 30)))
    values.setdefault("source", _state("telemetry_source", "Auto"))
    values.setdefault("image_format", _state("image_format", IMAGE_FORMATS[0]))
    values.setdefault("color_mode", _state("color_mode", COLOR_MODES[0]))
    return values
