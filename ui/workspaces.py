from __future__ import annotations

from datetime import date, datetime
import html
import json
import mimetypes
from pathlib import Path
import shutil
import traceback
from typing import Any, Callable

import fastf1
from matplotlib import pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from services.export_service import (
    CANONICAL_TELEMETRY_SCHEMA,
    make_after_effects_tsv,
    make_racerender_csv,
    normalize_telemetry,
)
from services.hud_renderer import (
    CANVAS_DEFAULT,
    HUD_SIZE_PRESETS,
    POSITION_PRESETS,
    build_hud_preview_frame,
    checkerboard_preview,
    export_hud_alpha_video,
    export_hud_png_sequence,
    ffmpeg_available,
    format_duration as format_hud_duration,
    frame_count_for_duration,
    normalize_hud_telemetry,
    telemetry_duration,
    zip_png_sequence,
)
from services.openf1_service import load_openf1_lap
from services.radio_service import load_radio_session
from services.replay_service import build_replay_payload, clear_replay_cache, list_replay_cache
from ui.components import (
    download_card,
    empty_state,
    metric_card,
    section_title,
    status_banner,
    technical_error_box,
    timestamp_caption,
)
from ui.replay_viewer import render_embedded_replay
from ui.race_overview import render_race_overview
from ui.studio_hero import render_studio_hero
from ui.constructor_config import SHOWCASE_SEASON
from services.overview_service import get_season_overview
from ui.session_selector import render_session_selector


CHART_GROUPS = {
    "Lap Analysis": [
        "Fastest lap map",
        "Telemetry Comparison",
        "Car Pace Delta Map",
        "Sector Performance Heatmap",
    ],
    "Race Pace": [
        "Selected driver race pace",
        "Driver lap comparison",
        "Lap consistency",
        "Lap-by-lap pace delta",
        "Lap-by-lap delta + stints",
    ],
    "Strategy": [
        "Stint strategy",
        "Hard stint average pace",
        "Medium stint average pace",
        "Tyre Degradation Analysis",
    ],
    "Race Overview": [
        "Position Tracker",
        "Gap to Leader",
        "Team race pace delta",
        "Speed Trap Analysis",
    ],
}

CHART_DESCRIPTIONS = {
    "Fastest lap map": "Compare two quickest laps around the circuit.",
    "Telemetry Comparison": "Overlay speed, throttle, braking, gear and delta traces.",
    "Car Pace Delta Map": "Map the faster car across circuit segments.",
    "Sector Performance Heatmap": "Compare sector strengths across selected drivers.",
    "Selected driver race pace": "Track cleaned race pace for a focused driver set.",
    "Driver lap comparison": "Compare valid lap distributions and trends.",
    "Lap consistency": "Measure repeatability and variance through a session.",
    "Lap-by-lap pace delta": "See the evolving pace gap between two drivers.",
    "Lap-by-lap delta + stints": "Add tyre-stint context to lap deltas.",
    "Stint strategy": "Visualize compounds and stint lengths across the field.",
    "Hard stint average pace": "Compare representative pace on the hard tyre.",
    "Medium stint average pace": "Compare representative pace on the medium tyre.",
    "Tyre Degradation Analysis": "Model pace loss over selected tyre stints.",
    "Position Tracker": "Follow race position changes lap by lap.",
    "Gap to Leader": "Plot cumulative race gaps to the session leader.",
    "Team race pace delta": "Compare team-level clean-air race pace.",
    "Speed Trap Analysis": "Rank peak speed and speed-trap performance.",
}


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _safe_name(value: Any) -> str:
    return "".join(
        char if char.isalnum() or char in "_-" else "_"
        for char in str(value)
    ).strip("_")


def _option_index(options: list[Any] | tuple[Any, ...], value: Any, fallback: int = 0) -> int:
    try:
        return list(options).index(value)
    except ValueError:
        return fallback


def _go_workspace(name: str, state: dict[str, Any] | None = None) -> None:
    st.session_state["workspace_nav"] = name
    st.session_state["workspace_nav_control"] = name
    for key, value in (state or {}).items():
        st.session_state[key] = value


def _duration(frame: pd.DataFrame) -> float:
    if frame is None or frame.empty or "time_sec" not in frame:
        return 0.0
    return float(pd.to_numeric(frame["time_sec"], errors="coerce").max() or 0.0)


def _format_duration(seconds: float) -> str:
    minutes, seconds = divmod(max(0, int(round(seconds))), 60)
    return f"{minutes}:{seconds:02d}"


def _events_for_year(event_loader: Callable[[int], list[str]], year: int) -> list[str]:
    try:
        return event_loader(int(year))
    except Exception:
        return ["Bahrain Grand Prix", "Italian Grand Prix", "Monaco Grand Prix"]


def _driver_codes(
    driver_loader: Callable[..., pd.DataFrame],
    year: int,
    event_name: str,
    session_name: str,
) -> list[str]:
    try:
        catalog = driver_loader(
            "Race Weekend",
            int(year),
            event_name,
            session_name,
            None,
            None,
        )
        codes = catalog["code"].dropna().astype(str).tolist()
        if codes:
            return codes
    except Exception:
        pass
    return [
        "VER", "NOR", "PIA", "LEC", "HAM", "RUS", "ANT", "ALO", "SAI", "ALB",
        "GAS", "OCO", "HUL", "LAW", "TSU", "STR", "BEA", "BOR", "HAD", "COL",
    ]


def render_overview_section(
    *,
    latest: dict[str, Any],
    output_dir: Path,
    chart_dir: Path,
    radio_dir: Path,
    replay_dir: Path,
    fastf1_cache: Path,
) -> None:
    overview = get_season_overview(SHOWCASE_SEASON)
    render_studio_hero(latest, overview)
    with st.container(key="season_content"):
        render_race_overview(shared_overview=overview)




@st.cache_resource(show_spinner=False)
def _load_timing_session(year: int, event_name: str, session_name: str):
    session = fastf1.get_session(int(year), event_name, session_name)
    session.load(laps=True, telemetry=True, weather=True, messages=True)
    return session


def _team_color(session, driver: str) -> str:
    try:
        return fastf1.plotting.get_driver_color(driver, session)
    except Exception:
        return "#6B7280"


def _lap_time(value: Any) -> str:
    if pd.isna(value):
        return "—"
    try:
        seconds = float(value.total_seconds())
    except (TypeError, ValueError, AttributeError):
        return str(value)
    minutes = int(seconds // 60)
    return f"{minutes}:{seconds - minutes * 60:06.3f}"


def _sector(value: Any) -> str:
    if pd.isna(value):
        return "—"
    try:
        return f"{float(value.total_seconds()):.3f}"
    except (TypeError, ValueError, AttributeError):
        return str(value)


def _timing_rows(session) -> list[dict[str, Any]]:
    rows = []
    fastest_session = session.laps.pick_fastest()
    fastest_time = fastest_session.get("LapTime") if fastest_session is not None else pd.NaT
    for position, number in enumerate(session.drivers, start=1):
        try:
            driver_info = session.get_driver(number)
            code = str(driver_info.get("Abbreviation") or number)
            laps = session.laps.pick_drivers(number)
        except Exception:
            continue
        if laps is None or laps.empty:
            continue
        clean = laps.dropna(subset=["LapTime"])
        best = clean.pick_fastest() if not clean.empty else None
        last = clean.iloc[-1] if not clean.empty else laps.iloc[-1]
        compound = str(last.get("Compound", "—") or "—").upper()
        tyre_short = {
            "SOFT": "S", "MEDIUM": "M", "HARD": "H",
            "INTERMEDIATE": "I", "WET": "W",
        }.get(compound, "—")
        speed_values = [
            pd.to_numeric(last.get(column), errors="coerce")
            for column in ("SpeedST", "SpeedFL", "SpeedI2", "SpeedI1")
        ]
        speed = next((value for value in speed_values if pd.notna(value)), np.nan)
        status = str(driver_info.get("Status") or "RUNNING").upper()
        rows.append(
            {
                "position": int(driver_info.get("Position") or position),
                "driver": code,
                "interval": "LEADER" if position == 1 else "—",
                "tyre": tyre_short,
                "compound": compound,
                "best": _lap_time(best.get("LapTime")) if best is not None else "—",
                "best_is_session": bool(
                    best is not None
                    and pd.notna(fastest_time)
                    and best.get("LapTime") == fastest_time
                ),
                "last": _lap_time(last.get("LapTime")),
                "s1": _sector(last.get("Sector1Time")),
                "s2": _sector(last.get("Sector2Time")),
                "s3": _sector(last.get("Sector3Time")),
                "speed": f"{float(speed):.0f}" if pd.notna(speed) else "—",
                "status": status,
                "color": _team_color(session, code),
            }
        )
    return sorted(rows, key=lambda row: row["position"])


def _timing_table_html(rows: list[dict[str, Any]]) -> str:
    body = []
    tyre_colors = {
        "S": "#ff3b30", "M": "#facc15", "H": "#f5f7fa",
        "I": "#2ccb70", "W": "#38bdf8", "—": "#667085",
    }
    for index, row in enumerate(rows):
        sector_classes = ["f1-sector-purple", "f1-sector-green", "f1-sector-yellow"]
        body.append(
            "<tr>"
            f"<td><b>{row['position']}</b></td>"
            f'<td><span class="f1-driver-pill"><i class="f1-team-dot" style="--team:{_esc(row["color"])}"></i>{_esc(row["driver"])}</span></td>'
            f"<td>{_esc(row['interval'])}</td>"
            f'<td><span class="f1-tyre-badge" style="color:{tyre_colors.get(row["tyre"], "#667085")}">{_esc(row["tyre"])}</span></td>'
            f'<td class="{"f1-best" if row["best_is_session"] else ""}">{_esc(row["best"])}</td>'
            f"<td>{_esc(row['last'])}</td>"
            f'<td class="{sector_classes[index % 3]}">{_esc(row["s1"])}</td>'
            f'<td class="{sector_classes[(index + 1) % 3]}">{_esc(row["s2"])}</td>'
            f'<td class="{sector_classes[(index + 2) % 3]}">{_esc(row["s3"])}</td>'
            f"<td>{_esc(row['speed'])}</td>"
            f"<td>{_esc(row['status'])}</td>"
            "</tr>"
        )
    return (
        '<div class="f1-timing-wrap"><table class="f1-timing-table">'
        "<thead><tr><th>POS</th><th>DRIVER</th><th>INTERVAL</th><th>TYRE</th>"
        "<th>BEST LAP</th><th>LAST LAP</th><th>S1</th><th>S2</th><th>S3</th>"
        "<th>SPEED</th><th>STATUS</th></tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table></div>"
    )


def render_live_timing_section(
    *,
    latest: dict[str, Any],
    event_loader: Callable[[int], list[str]],
    driver_loader: Callable[..., pd.DataFrame],
) -> None:
    section_title("Live Timing", "Session timing, lap performance and race control · Historical data")
    year_hint = int(st.session_state.get("live_timing_year", latest["year"]))
    events = _events_for_year(event_loader, year_hint)
    drivers = ["VER"]
    with st.container(border=True, key="timing_controls"):
        selection = render_session_selector(
            "Live Timing",
            event_options=events,
            driver_options=drivers,
            latest_year=int(latest["year"]),
            latest_event=str(latest["event_name"]),
        )
        load = st.button("Load timing session", key="timing_load")
    if load:
        try:
            with st.spinner("Loading historical timing and telemetry..."):
                st.session_state["timing_session"] = _load_timing_session(
                    selection["year"], selection["event"], selection["session"]
                )
        except Exception:
            technical_error_box(
                "The selected historical timing session could not be loaded.",
                traceback.format_exc(),
            )

    session = st.session_state.get("timing_session")
    if session is None:
        empty_state(
            "Ready to explore a session",
            "Choose a race weekend above and load the session for lap times, sectors, tyres and race control. This is historical data, not a live feed.",
        )
        return

    rows = _timing_rows(session)
    weather = getattr(session, "weather_data", pd.DataFrame())
    latest_weather = weather.iloc[-1] if weather is not None and not weather.empty else {}
    session_name = str(getattr(session, "name", selection["session"]))
    summaries = [
        ("Event", str(session.event.get("EventName", selection["event"]))),
        ("Session", session_name),
        ("Clock", "REPLAY"),
        ("Track status", "HISTORICAL"),
        (
            "Weather",
            f"{latest_weather.get('AirTemp', '—')}°C · {latest_weather.get('Humidity', '—')}%",
        ),
    ]
    st.markdown('<div class="rh-timing-summary">' + ''.join(
        f'<div><span>{_esc(label)}</span><strong>{_esc(value)}</strong></div>'
        for label, value in summaries
    ) + '</div>', unsafe_allow_html=True)

    main, side = st.columns([4, 1.25], gap="large")
    with main:
        section_title("Leaderboard", f"{len(rows)} classified drivers")
        st.markdown(_timing_table_html(rows), unsafe_allow_html=True)
    with side:
        section_title("Track map", "Fastest-lap reference line")
        try:
            lap = session.laps.pick_fastest()
            telemetry = lap.get_telemetry()
            fig, axis = plt.subplots(figsize=(7, 6))
            fig.patch.set_alpha(0)
            axis.set_facecolor("#0E1117")
            axis.plot(telemetry["X"], telemetry["Y"], color="#E8EBF0", linewidth=5, alpha=0.2)
            axis.plot(telemetry["X"], telemetry["Y"], color="#E10600", linewidth=1.7)
            axis.scatter(
                telemetry["X"].iloc[0],
                telemetry["Y"].iloc[0],
                s=45,
                color="#F5F7FA",
                zorder=4,
            )
            axis.set_aspect("equal")
            axis.axis("off")
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
        except Exception:
            empty_state("Track map unavailable", "This session has no usable XY telemetry.")
        st.caption("MINI SECTORS")
        st.markdown(
            '<div class="f1-card"><span class="f1-sector-purple">● ●</span> '
            '<span class="f1-sector-green">● ● ●</span> '
            '<span class="f1-sector-yellow">● ●</span>'
            '<div class="f1-card-muted">Purple best · green personal best · yellow representative</div></div>',
            unsafe_allow_html=True,
        )

    section_title("Race control", "Messages published with the historical session.")
    messages = getattr(session, "race_control_messages", pd.DataFrame())
    if messages is not None and not messages.empty:
        columns = [
            column for column in ("Time", "Category", "Flag", "Message")
            if column in messages.columns
        ]
        st.dataframe(
            messages[columns].tail(12),
            use_container_width=True,
            hide_index=True,
            height=290,
        )
    else:
        empty_state("No race-control messages", "FastF1 did not expose messages for this session.")


def render_analytics_section(
    *,
    latest: dict[str, Any],
    event_loader: Callable[[int], list[str]],
    driver_loader: Callable[..., pd.DataFrame],
    generate_chart: Callable[[str, dict[str, Any], dict[str, Any]], Path],
) -> None:
    section_title("Analytics", "Find the story in the sectors, the strategy and the pace.")
    year_hint = int(st.session_state.get("analytics_year", latest["year"]))
    events = _events_for_year(event_loader, year_hint)
    event_hint = st.session_state.get("analytics_event", latest["event_name"])
    session_hint = st.session_state.get("analytics_session", "R")
    drivers = _driver_codes(driver_loader, year_hint, event_hint, session_hint)
    with st.container(border=True):
        selection = render_session_selector(
            "Analytics",
            event_options=events,
            driver_options=drivers,
            latest_year=int(latest["year"]),
            latest_event=str(latest["event_name"]),
        )
        if selection["color_mode"] == "Custom":
            colors = st.columns(2)
            colors[0].color_picker("Driver / series color A", "#00D2BE", key="custom_color_a")
            colors[1].color_picker("Driver / series color B", "#DC0000", key="custom_color_b")

    selected_category = st.session_state.get("analytics_category", "Lap Analysis")
    section_title("Analysis desk", "Choose a discipline and a chart.")
    selected_category = st.segmented_control(
        "Discipline", list(CHART_GROUPS), default=selected_category,
        key="analytics_discipline_control", label_visibility="collapsed",
    ) or selected_category
    st.session_state["analytics_category"] = selected_category

    charts = CHART_GROUPS[selected_category]
    selected_chart = st.session_state.get("analytics_chart", charts[0])
    if selected_chart not in charts:
        selected_chart = charts[0]
    selected_chart = st.selectbox(
        "Analysis", charts, index=charts.index(selected_chart),
        key=f"analytics_chart_picker_{_safe_name(selected_category)}",
    )
    st.session_state["analytics_chart"] = selected_chart
    st.caption(CHART_DESCRIPTIONS[selected_chart])

    controls_col, result_col = st.columns([3, 7])
    controls: dict[str, Any] = {}
    with controls_col:
        with st.container(border=True):
            st.markdown(f"##### {selected_chart}")
            if selection["mode"] == "Pre-season Testing":
                tc1, tc2 = st.columns(2)
                controls["test_number"] = tc1.number_input("Test #", 1, 3, 1)
                controls["day_number"] = tc2.number_input("Day #", 1, 7, 1)
            pair_charts = {
                "Fastest lap map", "Telemetry Comparison", "Car Pace Delta Map",
                "Driver lap comparison", "Lap-by-lap pace delta", "Lap-by-lap delta + stints",
            }
            multi_charts = {
                "Selected driver race pace", "Lap consistency", "Stint strategy",
                "Hard stint average pace", "Medium stint average pace",
                "Tyre Degradation Analysis", "Position Tracker", "Gap to Leader",
                "Sector Performance Heatmap",
            }
            if selected_chart in pair_charts:
                controls["driver_a"] = st.selectbox(
                    "Driver A",
                    drivers,
                    index=drivers.index(selection["driver_a"]) if selection["driver_a"] in drivers else 0,
                    key="analysis_control_driver_a",
                )
                controls["driver_b"] = st.selectbox(
                    "Driver B",
                    drivers,
                    index=drivers.index(selection["driver_b"]) if selection["driver_b"] in drivers else min(1, len(drivers) - 1),
                    key="analysis_control_driver_b",
                )
            if selected_chart in multi_charts:
                defaults = [driver for driver in ("VER", "NOR", "LEC", "RUS") if driver in drivers]
                controls["drivers"] = st.multiselect(
                    "Drivers",
                    drivers,
                    default=defaults or drivers[: min(4, len(drivers))],
                    key="analysis_control_drivers",
                )
            if selected_chart == "Telemetry Comparison":
                controls["lap_number"] = int(st.number_input("Lap #", 1, 300, 10))
            if selected_chart == "Car Pace Delta Map":
                controls["lap_compare_mode"] = st.selectbox(
                    "Comparison",
                    ["Fastest laps", "Same lap number"],
                )
                if controls["lap_compare_mode"] == "Same lap number":
                    controls["lap_number"] = int(st.number_input("Lap #", 1, 300, 20))
            generate = st.button(
                "Generate chart",
                type="primary",
                key="analytics_generate",
                use_container_width=True,
            )

    with result_col:
        with st.container(border=True, key="analytics_preview_panel"):
            if generate:
                try:
                    with st.spinner(f"Rendering {selected_chart}..."):
                        output = generate_chart(selected_chart, selection, controls)
                    st.session_state["analytics_result"] = str(output)
                    st.session_state["analytics_result_chart"] = selected_chart
                except Exception:
                    technical_error_box(
                        "The chart could not be generated for this selection.",
                        traceback.format_exc(),
                    )
            result = Path(st.session_state["analytics_result"]) if st.session_state.get("analytics_result") else None
            if result and result.exists():
                st.image(str(result), use_container_width=True)
                timestamp_caption(result)
                st.download_button(
                    "Download PNG",
                    data=result.read_bytes(),
                    file_name=result.name,
                    mime="image/png",
                    key="analytics_result_download",
                    use_container_width=True,
                )
            elif not generate:
                empty_state(
                    "Preview ready",
                    "Choose an analysis card, set the required controls and generate a chart.",
                )


def render_telemetry_export_section(
    *,
    latest: dict[str, Any],
    event_loader: Callable[[int], list[str]],
    driver_loader: Callable[..., pd.DataFrame],
    fastf1_builder: Callable[[dict[str, Any]], tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]],
    output_dir: Path,
) -> None:
    section_title("Telemetry Export", "A compact production desk for canonical telemetry files.")
    year_hint = int(st.session_state.get("telemetry_export_year", latest["year"]))
    events = _events_for_year(event_loader, year_hint)
    event_hint = st.session_state.get("telemetry_export_event", latest["event_name"])
    session_hint = st.session_state.get("telemetry_export_session", "Q")
    drivers = _driver_codes(driver_loader, year_hint, event_hint, session_hint)
    with st.container(border=True):
        selection = render_session_selector(
            "Telemetry Export",
            event_options=events,
            driver_options=drivers,
            latest_year=int(latest["year"]),
            latest_event=str(latest["event_name"]),
        )
        if selection["mode"] == "Pre-season Testing":
            testing = st.columns(2)
            selection["test_number"] = int(testing[0].number_input("Test #", 1, 3, 1, key="export_test_number"))
            selection["day_number"] = int(testing[1].number_input("Day #", 1, 7, 1, key="export_day_number"))
        lap_number = None
        if selection["lap"] == "Lap number":
            lap_number = int(st.number_input("Lap #", 1, 300, 1, key="export_lap_number"))
        selection["lap_number"] = lap_number
        status_banner(
            "2026 overtake, boost, recharge and active-aero fields remain null unless a real source exposes them.",
            "info",
        )
        uploaded = None
        with st.expander("Advanced · Upload CSV", expanded=selection["source"] == "Upload CSV"):
            uploaded = st.file_uploader(
                "Upload telemetry CSV",
                type=["csv"],
                key="telemetry_upload",
            )
            st.caption("Uploaded data is normalized to the same canonical schema.")
        generate = st.button(
            "Generate exports",
            type="primary",
            key="telemetry_generate",
            use_container_width=True,
        )

    if generate:
        fastf1_error = None
        try:
            with st.spinner("Loading telemetry and building export formats..."):
                requested_source = selection["source"]
                metadata: dict[str, Any] = {}
                if requested_source == "Upload CSV":
                    if uploaded is None:
                        raise ValueError("Choose a CSV file in Advanced before generating.")
                    raw = pd.read_csv(uploaded)
                    lap_frame = normalize_telemetry(raw, "Upload CSV")
                    full_frame = lap_frame.copy()
                    metadata = {"source": "Upload CSV", "lap": selection["lap"]}
                elif requested_source in {"Auto", "FastF1"}:
                    try:
                        lap_frame, full_frame, metadata = fastf1_builder(selection)
                    except Exception as exc:
                        fastf1_error = traceback.format_exc()
                        if requested_source == "FastF1":
                            raise
                        lap_frame, full_frame, open_meta, lap_meta = load_openf1_lap(
                            selection["year"],
                            selection["event"],
                            selection["session"],
                            selection["driver"],
                            selection["lap"],
                            selection["lap_number"],
                        )
                        metadata = {
                            "source": "OpenF1 fallback",
                            "session": open_meta,
                            "lap": lap_meta,
                        }
                else:
                    lap_frame, full_frame, open_meta, lap_meta = load_openf1_lap(
                        selection["year"],
                        selection["event"],
                        selection["session"],
                        selection["driver"],
                        selection["lap"],
                        selection["lap_number"],
                    )
                    metadata = {"source": "OpenF1", "session": open_meta, "lap": lap_meta}

                lap_frame = lap_frame[CANONICAL_TELEMETRY_SCHEMA].copy()
                full_frame = full_frame[CANONICAL_TELEMETRY_SCHEMA].copy()
                ae_frame = make_after_effects_tsv(lap_frame, int(selection["fps"]))
                rr_frame = make_racerender_csv(lap_frame)
                source = str(metadata.get("source", requested_source))
                stem = _safe_name(
                    f"{selection['year']}_{selection['event']}_{selection['session']}_"
                    f"{selection['driver']}_{selection['lap']}"
                )
                payloads = {
                    "lap": (
                        f"telemetry_{stem}.csv",
                        lap_frame.to_csv(index=False).encode("utf-8"),
                        lap_frame,
                    ),
                    "full": (
                        f"full_telemetry_{stem}.csv",
                        full_frame.to_csv(index=False).encode("utf-8"),
                        full_frame,
                    ),
                    "ae": (
                        f"ae_dataver_{stem}.tsv",
                        ae_frame.to_csv(sep="\t", index=False).encode("utf-8"),
                        ae_frame,
                    ),
                    "rr": (
                        f"racerender_{stem}.csv",
                        rr_frame.to_csv(index=False).encode("utf-8"),
                        rr_frame,
                    ),
                }
                output_dir.mkdir(parents=True, exist_ok=True)
                for filename, data, _ in payloads.values():
                    (output_dir / filename).write_bytes(data)
                st.session_state["telemetry_result"] = {
                    "payloads": payloads,
                    "source": source,
                    "metadata": metadata,
                    "fastf1_error": fastf1_error,
                }
        except Exception:
            technical_error_box(
                "No telemetry export could be produced for that selection.",
                traceback.format_exc(),
            )

    result = st.session_state.get("telemetry_result")
    if not result:
        empty_state(
            "Export desk ready",
            "Select a session and source, then generate the four production formats.",
        )
        return

    payloads = result["payloads"]
    lap_frame = payloads["lap"][2]
    source = result["source"]
    section_title("Selected lap", "Source and payload summary")
    summaries = st.columns(4)
    for column, (label, value, caption) in zip(
        summaries,
        [
            ("Driver", selection["driver"], selection["lap"]),
            ("Source", source, "Auto records the actual fallback"),
            ("Rows", f"{len(lap_frame):,}", "Canonical lap stream"),
            ("Duration", _format_duration(_duration(lap_frame)), f"{selection['fps']} fps export"),
        ],
    ):
        with column:
            metric_card(label, value, caption, "good" if label == "Source" else "info")
    status_banner(
        f"{len(CANONICAL_TELEMETRY_SCHEMA)} canonical columns available. "
        f"Files were written to {output_dir}.",
        "good",
    )

    section_title("Export packages", "Each format is written locally and downloadable here.")
    export_cards = st.columns(4)
    specifications = [
        ("lap", "Lap telemetry CSV", "Canonical selected-lap telemetry", "text/csv"),
        ("full", "Full telemetry CSV", "Full source stream for the request", "text/csv"),
        ("ae", "After Effects TSV", f"Frame-sampled at {selection['fps']} fps", "text/tab-separated-values"),
        ("rr", "RaceRender CSV", "RaceRender-compatible HUD fields", "text/csv"),
    ]
    for column, (key, title, description, mime) in zip(export_cards, specifications):
        filename, data, frame = payloads[key]
        with column:
            download_card(
                title,
                description,
                filename,
                len(frame),
                _format_duration(_duration(lap_frame)),
                data,
                mime,
                source=source,
                key=f"export_download_{key}",
            )

    with st.expander("Preview first 30 rows", expanded=False):
        st.dataframe(lap_frame.head(30), use_container_width=True, hide_index=True)
    with st.expander("Preview columns", expanded=False):
        st.code("\n".join(lap_frame.columns), language="text")
    if result.get("fastf1_error"):
        with st.expander("Technical details · FastF1 fallback", expanded=False):
            st.code(result["fastf1_error"], language="text")


def _hud_output_label(selection: dict[str, Any]) -> str:
    lap_label = (
        "Fastest"
        if selection.get("lap") == "Fastest"
        else f"Lap_{selection.get('lap_number') or 1}"
    )
    return _safe_name(
        "hud_overlay_"
        f"{selection.get('year')}_"
        f"{selection.get('event', 'Testing')}_"
        f"{selection.get('session', 'Test')}_"
        f"{selection.get('driver', 'DRV')}_"
        f"{lap_label}_"
        f"{selection.get('fps', 30)}fps"
    )


def _hud_signature(selection: dict[str, Any]) -> str:
    keys = [
        "mode", "year", "event", "session", "driver", "lap", "lap_number",
        "fps", "source", "output_format", "hud_width", "position_preset",
        "custom_x", "custom_y", "canvas_width", "canvas_height",
    ]
    return json.dumps({key: selection.get(key) for key in keys}, sort_keys=True)


def _load_hud_telemetry(
    selection: dict[str, Any],
    *,
    fastf1_builder: Callable[[dict[str, Any]], tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]],
    uploaded: Any | None,
) -> tuple[pd.DataFrame, dict[str, Any], str | None]:
    requested_source = selection.get("source", "Auto")
    fastf1_error = None
    if requested_source == "Upload CSV":
        if uploaded is None:
            raise ValueError("Choose a CSV file in Advanced before previewing or generating.")
        raw = pd.read_csv(uploaded)
        return normalize_hud_telemetry(raw, "Upload CSV"), {"source": "Upload CSV"}, None

    if requested_source in {"Auto", "FastF1"}:
        try:
            lap_frame, _, metadata = fastf1_builder(selection)
            return normalize_hud_telemetry(lap_frame, "FastF1"), metadata | {"source": "FastF1"}, None
        except Exception:
            fastf1_error = traceback.format_exc()
            if requested_source == "FastF1":
                raise

    if selection.get("mode") != "Race Weekend":
        raise RuntimeError("OpenF1 fallback is only available for race-weekend sessions. Use FastF1 or Upload CSV for testing.")

    lap_frame, _, open_meta, lap_meta = load_openf1_lap(
        int(selection["year"]),
        str(selection["event"]),
        str(selection["session"]),
        str(selection["driver"]),
        str(selection["lap"]),
        selection.get("lap_number"),
    )
    metadata = {"source": "OpenF1", "session": open_meta, "lap": lap_meta}
    return normalize_hud_telemetry(lap_frame, "OpenF1"), metadata, fastf1_error


def _render_hud_preview_result(preview: dict[str, Any]) -> None:
    image = preview.get("image")
    row = preview.get("row", {})
    if image is not None:
        st.image(
            image,
            caption="Checkerboard preview crop. Export remains a full transparent 1080x1920 frame.",
            use_container_width=True,
        )
    values = [
        ("Speed", f"{float(row.get('speed_kmh', 0)):.0f} km/h"),
        ("RPM", f"{float(row.get('rpm', 0)):.0f}"),
        ("Gear", int(row.get("gear", 1) or 1)),
        ("Throttle", f"{float(row.get('throttle', 0)):.0f}%"),
        ("Brake", f"{float(row.get('brake', 0)):.0f}%"),
    ]
    cols = st.columns(len(values))
    for column, (label, value) in zip(cols, values):
        with column:
            metric_card(label, value, "Preview sample", "info")


def _download_hud_result(result: dict[str, Any]) -> None:
    export = result["export"]
    output_path = export.output_path
    if output_path and Path(output_path).exists():
        st.download_button(
            f"Download {Path(output_path).suffix.upper().lstrip('.')}",
            data=Path(output_path).read_bytes(),
            file_name=Path(output_path).name,
            mime="video/webm" if Path(output_path).suffix.lower() == ".webm" else "video/quicktime",
            key=f"hud_download_{Path(output_path).name}",
            use_container_width=True,
        )
    if export.frames_dir and Path(export.frames_dir).exists():
        try:
            archive = zip_png_sequence(export.frames_dir)
            st.download_button(
                "Download PNG sequence ZIP",
                data=archive,
                file_name=f"{Path(export.frames_dir).name}.zip",
                mime="application/zip",
                key=f"hud_zip_{Path(export.frames_dir).name}",
                use_container_width=True,
            )
        except Exception:
            technical_error_box("The HUD frames were created, but the ZIP package could not be prepared.", traceback.format_exc())


def render_hud_export_section(
    *,
    latest: dict[str, Any],
    event_loader: Callable[[int], list[str]],
    driver_loader: Callable[..., pd.DataFrame],
    fastf1_builder: Callable[[dict[str, Any]], tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]],
    assets_dir: Path,
    output_dir: Path,
    frames_dir: Path,
) -> None:
    section_title("HUD Export", "Generate transparent F1-style HUD overlays with real lap telemetry and alpha.")
    ffmpeg_ok, ffmpeg_detail = ffmpeg_available()
    if ffmpeg_ok:
        status_banner("Alpha video export ready · WebM / MOV / PNG sequence", "good")
    else:
        status_banner("ffmpeg not found. PNG Sequence export still works; WebM/MOV alpha video requires ffmpeg.", "warn")

    default_year = 2026
    events = _events_for_year(event_loader, default_year)
    default_event = "Austrian Grand Prix" if "Austrian Grand Prix" in events else str(latest.get("event_name", events[0] if events else "Austrian Grand Prix"))
    drivers = _driver_codes(driver_loader, default_year, default_event, "R")
    if "ALB" not in drivers:
        drivers = [*drivers, "ALB"]

    with st.container(border=True):
        st.markdown("##### Session selector")
        top = st.columns([1.3, .75, 2, .75]) + st.columns([1.2, 1.2, 1, 1.3])
        mode = top[0].selectbox("Mode", ["Race Weekend", "Pre-season Testing"], index=0, key="hud_export_mode")
        year = int(top[1].number_input("Year", min_value=2018, max_value=2035, value=default_year, step=1, key="hud_export_year"))
        events = _events_for_year(event_loader, year)
        if default_event not in events:
            default_event = events[0] if events else default_event
        event = top[2].selectbox("Event", events or [default_event], index=_option_index(events or [default_event], default_event), key="hud_export_event")
        session = top[3].selectbox("Session", ["FP1", "FP2", "FP3", "Q", "R", "SQ", "S"], index=4, key="hud_export_session")
        drivers = _driver_codes(driver_loader, year, event, session)
        if "ALB" not in drivers:
            drivers = [*drivers, "ALB"]
        driver = top[4].selectbox("Driver", drivers, index=_option_index(drivers, "ALB"), key="hud_export_driver")
        lap_mode = top[5].selectbox("Lap", ["Fastest", "Lap number"], index=0, key="hud_export_lap")
        fps = int(top[6].selectbox("Export FPS", [25, 30, 50], index=1, key="hud_export_fps"))
        source = top[7].selectbox("Source", ["Auto", "FastF1", "OpenF1", "Upload CSV"], index=0, key="hud_export_source")

        lap_number = None
        if lap_mode == "Lap number":
            lap_number = int(st.number_input("Lap #", min_value=1, max_value=300, value=1, key="hud_export_lap_number"))
        if mode == "Pre-season Testing":
            testing = st.columns(2)
            test_number = int(testing[0].number_input("Test #", 1, 3, 1, key="hud_export_test_number"))
            day_number = int(testing[1].number_input("Day #", 1, 7, 1, key="hud_export_day_number"))
        else:
            test_number = None
            day_number = None
        uploaded = None
        with st.expander("Advanced · Upload CSV", expanded=source == "Upload CSV"):
            uploaded = st.file_uploader(
                "Upload HUD telemetry CSV",
                type=["csv"],
                key="hud_export_upload",
                help="Columns such as Time, RPM, Speed, nGear, Throttle, Brake, DRS, X, Y, Z are normalized automatically.",
            )
            st.caption("Brake may be boolean or 0-100. DRS may be boolean or FastF1/OpenF1 numeric values.")

    with st.container(border=True):
        st.markdown("##### HUD layout")
        layout = st.columns([1.35, 1, 1.15, .8, .8])
        output_format = layout[0].selectbox("Output format", ["WebM VP9 Alpha", "PNG Sequence", "MOV ProRes 4444"], index=0, key="hud_export_format")
        hud_size = layout[1].selectbox("HUD size", ["Small", "Medium", "Large", "Custom"], index=1, key="hud_export_size")
        hud_width = HUD_SIZE_PRESETS.get(hud_size, 460)
        if hud_size == "Custom":
            hud_width = int(st.number_input("Custom HUD width", min_value=180, max_value=900, value=460, step=10, key="hud_export_custom_width"))
        position_preset = layout[2].selectbox("Position preset", list(POSITION_PRESETS), index=0, key="hud_export_position")
        custom_x = int(layout[3].number_input("X", min_value=0, max_value=3000, value=80, step=5, key="hud_export_x"))
        custom_y = int(layout[4].number_input("Y", min_value=0, max_value=4000, value=1180, step=5, key="hud_export_y"))
        with st.expander("Advanced canvas", expanded=False):
            canvas_cols = st.columns(2)
            canvas_width = int(canvas_cols[0].number_input("Canvas width", min_value=320, max_value=4096, value=CANVAS_DEFAULT[0], step=10, key="hud_canvas_w"))
            canvas_height = int(canvas_cols[1].number_input("Canvas height", min_value=320, max_value=4096, value=CANVAS_DEFAULT[1], step=10, key="hud_canvas_h"))
            st.caption("Default is 1080x1920. Output frames are full-size transparent frames, not cropped HUD-only images.")

    selection = {
        "mode": mode,
        "year": year,
        "event": event,
        "session": session,
        "driver": driver,
        "lap": lap_mode,
        "lap_number": lap_number,
        "fps": fps,
        "source": source,
        "test_number": test_number,
        "day_number": day_number,
        "output_format": output_format,
        "hud_width": hud_width,
        "position_preset": position_preset,
        "custom_x": custom_x,
        "custom_y": custom_y,
        "canvas_width": canvas_width,
        "canvas_height": canvas_height,
    }
    signature = _hud_signature(selection)
    safe_label = _hud_output_label(selection)
    estimated = st.session_state.get("hud_export_estimate")
    estimate_duration = float(estimated.get("duration", 0)) if estimated and estimated.get("signature") == signature else 0.0
    estimate_cols = st.columns(3)
    with estimate_cols[0]:
        metric_card("Estimated duration", format_hud_duration(estimate_duration) if estimate_duration else "Preview first", "Lap telemetry duration", "info")
    with estimate_cols[1]:
        metric_card("Frames", f"{frame_count_for_duration(estimate_duration, fps):,}" if estimate_duration else "—", f"{fps} fps", "info")
    with estimate_cols[2]:
        metric_card("Canvas", f"{canvas_width}x{canvas_height}", f"{hud_width}px HUD", "info")

    preview_card, export_card = st.columns([1.05, .95])
    with preview_card:
        with st.container(border=True):
            st.markdown("##### Preview frame")
            if st.button("Preview frame", key="hud_preview", use_container_width=True):
                try:
                    with st.spinner("Loading telemetry and rendering a transparent HUD frame..."):
                        telemetry, metadata, fastf1_error = _load_hud_telemetry(selection, fastf1_builder=fastf1_builder, uploaded=uploaded)
                        frame, row = build_hud_preview_frame(
                            telemetry,
                            assets_dir,
                            canvas_size=(canvas_width, canvas_height),
                            hud_width=hud_width,
                            position_preset=position_preset,
                            custom_x=custom_x,
                            custom_y=custom_y,
                            hud_year=year,
                        )
                        st.session_state["hud_export_preview"] = {
                            "signature": signature,
                            "image": checkerboard_preview(frame),
                            "row": row,
                            "year": year,
                            "metadata": metadata,
                            "fastf1_error": fastf1_error,
                        }
                        st.session_state["hud_export_estimate"] = {
                            "signature": signature,
                            "duration": telemetry_duration(telemetry),
                            "rows": len(telemetry),
                            "metadata": metadata,
                        }
                        st.rerun()
                except Exception:
                    technical_error_box("No HUD preview could be produced for that selection.", traceback.format_exc())
            preview = st.session_state.get("hud_export_preview")
            if preview and preview.get("signature") == signature:
                _render_hud_preview_result(preview)
                if preview.get("fastf1_error"):
                    with st.expander("Technical details · FastF1 fallback", expanded=False):
                        st.code(preview["fastf1_error"], language="text")
            else:
                empty_state("Preview ready", "Click Preview frame to verify alpha, layout and telemetry values.")

    with export_card:
        with st.container(border=True):
            st.markdown("##### Export")
            status_banner("Generate writes transparent frames first, then encodes alpha video when requested.", "info")
            progress = st.progress(0, text="Waiting for export")

            def _progress(done: int, total: int) -> None:
                progress.progress(min(1.0, done / max(1, total)), text=f"Rendering frames {done:,}/{total:,}")

            generate = st.button("Generate HUD overlay", type="primary", key="hud_generate")
            clear = st.button("Clear previous frames", key="hud_clear_frames", use_container_width=True)
            if clear:
                previous = st.session_state.get("hud_export_result")
                previous_dir = previous.get("export").frames_dir if previous and previous.get("export") else None
                if previous_dir and Path(previous_dir).exists() and frames_dir in Path(previous_dir).parents:
                    shutil.rmtree(previous_dir)
                    st.success("Previous HUD frame sequence cleared.")
                else:
                    st.info("No generated HUD frame sequence is selected to clear.")

            if generate:
                try:
                    if output_format in {"WebM VP9 Alpha", "MOV ProRes 4444"} and not ffmpeg_ok:
                        raise RuntimeError("ffmpeg is required for alpha video. Choose PNG Sequence or install ffmpeg.")
                    with st.spinner("Rendering transparent HUD frames..."):
                        telemetry, metadata, fastf1_error = _load_hud_telemetry(selection, fastf1_builder=fastf1_builder, uploaded=uploaded)
                        if output_format == "PNG Sequence":
                            export = export_hud_png_sequence(
                                telemetry,
                                assets_dir,
                                frames_dir,
                                safe_label,
                                fps=fps,
                                canvas_size=(canvas_width, canvas_height),
                                hud_width=hud_width,
                                position_preset=position_preset,
                                custom_x=custom_x,
                                custom_y=custom_y,
                                hud_year=year,
                                progress_callback=_progress,
                            )
                        else:
                            export = export_hud_alpha_video(
                                telemetry,
                                assets_dir,
                                output_dir,
                                frames_dir,
                                safe_label,
                                fps=fps,
                                format_label=output_format,
                                canvas_size=(canvas_width, canvas_height),
                                hud_width=hud_width,
                                position_preset=position_preset,
                                custom_x=custom_x,
                                custom_y=custom_y,
                                hud_year=year,
                                progress_callback=_progress,
                            )
                        progress.progress(1.0, text="HUD export complete")
                        st.session_state["hud_export_result"] = {
                            "signature": signature,
                            "export": export,
                            "metadata": metadata,
                            "fastf1_error": fastf1_error,
                        }
                        st.session_state["hud_export_estimate"] = {
                            "signature": signature,
                            "duration": export.duration_sec,
                            "rows": len(telemetry),
                            "metadata": metadata,
                        }
                except Exception:
                    progress.empty()
                    technical_error_box("No HUD overlay could be generated for that selection.", traceback.format_exc())

            result = st.session_state.get("hud_export_result")
            if result and result.get("signature") == signature:
                export = result["export"]
                st.success("HUD overlay generated with real alpha transparency.")
                summary = st.columns(2)
                with summary[0]:
                    metric_card("Format", export.format_label, f"{export.fps} fps", "good")
                with summary[1]:
                    metric_card("Duration", format_hud_duration(export.duration_sec), f"{export.frame_count:,} frames", "info")
                _download_hud_result(result)
                with st.expander("Technical details", expanded=False):
                    st.write("Metadata")
                    st.json(result.get("metadata", {}))
                    if export.ffmpeg_command:
                        st.write("ffmpeg command")
                        st.code(" ".join(export.ffmpeg_command), language="text")
                    if export.ffmpeg_stdout:
                        st.write("ffmpeg stdout")
                        st.code(export.ffmpeg_stdout, language="text")
                    if export.ffmpeg_stderr:
                        st.write("ffmpeg stderr")
                        st.code(export.ffmpeg_stderr, language="text")
                    if result.get("fastf1_error"):
                        st.write("FastF1 fallback details")
                        st.code(result["fastf1_error"], language="text")
            else:
                empty_state("Exporter ready", "Click Generate HUD overlay when the preview looks right.")


def render_race_replay_section(
    *,
    latest: dict[str, Any],
    event_loader: Callable[[int], list[str]],
    driver_loader: Callable[..., pd.DataFrame],
    legacy_dir: Path,
) -> None:
    section_title("Race Replay", "Follow the field. Revisit the moves that changed the race.")
    year_hint = int(st.session_state.get("race_replay_year", latest["year"]))
    events = _events_for_year(event_loader, year_hint)
    drivers = ["VER"]
    with st.container(border=True):
        selection = render_session_selector(
            "Race Replay",
            event_options=events,
            driver_options=drivers,
            latest_year=int(latest["year"]),
            latest_event=str(latest["event_name"]),
        )
        load = st.button(
            "Load Replay",
            type="primary",
            key="replay_load",
            use_container_width=True,
        )

    if load:
        progress = st.progress(0, text="Preparing replay")

        def update_progress(value: float, text: str) -> None:
            progress.progress(min(1.0, float(value)), text=text)

        try:
            payload = build_replay_payload(
                int(selection["year"]),
                selection["event"],
                selection["session_type"],
                sample_rate_hz=int(selection["sample_rate"]),
                refresh=bool(selection["refresh"]),
                progress_callback=update_progress,
            )
            st.session_state["replay_payload"] = payload
            status_banner("Replay payload ready. Playback is running inside this page.", "good")
        except Exception:
            technical_error_box(
                "The selected replay could not be prepared.",
                traceback.format_exc(),
            )

    payload = st.session_state.get("replay_payload")
    if not payload:
        empty_state(
            "Replay cockpit standing by",
            "Load a race or qualifying session. Cached payloads open immediately; a first build can take longer.",
        )
    else:
        meta = payload.get("meta", {})
        summary = st.columns(5)
        items = [
            ("Event", meta.get("event", selection["event"])),
            ("Session", meta.get("session", selection["session_type"])),
            ("Frames", f"{len(payload.get('frames', [])):,}"),
            ("Drivers", len(payload.get("drivers", {}))),
            ("Duration", _format_duration(float(meta.get("duration_seconds", 0)))),
        ]
        for column, (label, value) in zip(summary, items):
            with column:
                metric_card(label, value, status="info")
        render_embedded_replay(payload, height=720)

    with st.expander("Advanced", expanded=False):
        columns = st.columns(3)
        with columns[0]:
            if st.button("Clear replay cache", key="clear_replay_cache"):
                removed = clear_replay_cache()
                st.session_state.pop("replay_payload", None)
                st.success(f"Removed {removed} payload file(s).")
        with columns[1]:
            if payload:
                meta = payload.get("meta", {})
                st.download_button(
                    "Download payload JSON",
                    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    file_name=f"replay_{_safe_name(meta.get('event', 'session'))}_{meta.get('session', 'R')}.json",
                    mime="application/json",
                    key="replay_payload_download",
                    use_container_width=True,
                )
        with columns[2]:
            st.caption("Legacy desktop viewer is isolated below.")
        if payload:
            with st.expander("Technical details", expanded=False):
                st.json(payload.get("technical", {}))
        with st.expander("Legacy desktop viewer", expanded=False):
            main_py = legacy_dir / "main.py"
            if main_py.exists():
                st.caption("Troubleshooting only. The normal replay flow never launches this process.")
                st.code(f'.\\.venv\\Scripts\\python.exe "{main_py}" --viewer', language="powershell")
            else:
                st.info("The legacy viewer is not installed.")


def _local_radio_data(output_dir: Path) -> dict[str, Any] | None:
    exports = sorted(output_dir.glob("*.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not exports:
        return None
    path = exports[0]
    frame = pd.read_csv(path)
    if frame.empty:
        return None
    frame["idx"] = range(len(frame))
    json_path = path.with_suffix(".json")
    return {
        "year": "",
        "race": path.stem,
        "session_type": "Local export",
        "csv_path": path,
        "json_path": json_path if json_path.exists() else None,
        "clips": frame.to_dict("records"),
        "local_fallback": True,
    }


def render_radio_section(
    *,
    latest: dict[str, Any],
    event_loader: Callable[[int], list[str]],
    driver_loader: Callable[..., pd.DataFrame],
    cache_dir: Path,
    output_dir: Path,
) -> None:
    section_title("Radio", "Scan public team-radio clips, then play and export from one desk.")
    year_hint = int(st.session_state.get("radio_year", latest["year"]))
    events = _events_for_year(event_loader, year_hint)
    drivers = ["VER"]
    with st.container(border=True):
        selection = render_session_selector(
            "Radio",
            event_options=events,
            driver_options=drivers,
            latest_year=int(latest["year"]),
            latest_event=str(latest["event_name"]),
        )
        load = st.button(
            "Load radio archive",
            type="primary",
            key="radio_load",
            use_container_width=True,
        )

    if load:
        try:
            with st.spinner("Loading public clips and local audio cache..."):
                radio_data = load_radio_session(
                    selection["year"],
                    selection["event"],
                    selection["session"],
                    cache_dir=cache_dir,
                    output_dir=output_dir,
                    force_refresh=bool(selection["refresh"]),
                )
            st.session_state["radio_data"] = radio_data
            status_banner("Public radio archive loaded and local exports refreshed.", "good")
        except Exception:
            fallback = _local_radio_data(output_dir)
            if fallback:
                st.session_state["radio_data"] = fallback
                status_banner("Live archive unavailable; showing the newest local radio export.", "warn")
                with st.expander("Technical details", expanded=False):
                    st.code(traceback.format_exc(), language="text")
            else:
                technical_error_box(
                    "No public or local radio clips were available for that session.",
                    traceback.format_exc(),
                )

    radio_data = st.session_state.get("radio_data")
    if not radio_data:
        empty_state(
            "Radio browser standing by",
            "Load a session to browse clips. Existing local exports remain available as fallback.",
        )
        return
    clips = pd.DataFrame(radio_data.get("clips", []))
    if clips.empty:
        empty_state("No public clips", "The archive contains no clips for this session.")
        return
    if "idx" not in clips:
        clips["idx"] = range(len(clips))
    counts = (
        clips.groupby("driver", dropna=False)
        .size()
        .reset_index(name="clips")
        .sort_values(["clips", "driver"], ascending=[False, True])
    )
    summary = st.columns(3)
    items = [
        ("Public clips", len(clips), str(radio_data.get("session_type", "Session"))),
        ("Drivers with clips", counts["driver"].nunique(), "Filterable archive"),
        ("Most clips", f"{counts.iloc[0]['driver']} · {counts.iloc[0]['clips']}", "Session leader"),
    ]
    for column, (label, value, caption) in zip(summary, items):
        with column:
            metric_card(label, value, caption)

    left, right = st.columns([9, 11])
    with left, st.container(key="radio_browser"):
        st.markdown("##### Clip browser")
        driver_options = ["ALL", *sorted(clips["driver"].dropna().astype(str).unique())]
        selected_driver = st.selectbox(
            "Driver filter",
            driver_options,
            key="radio_driver_filter",
        )
        filtered = clips if selected_driver == "ALL" else clips[clips["driver"] == selected_driver]
        filtered = filtered.reset_index(drop=True)
        labels = []
        for row in filtered.itertuples():
            lap = getattr(row, "lap", "—")
            position = getattr(row, "position", "—")
            labels.append(
                f"{int(row.idx)} · {getattr(row, 'driver', '—')} · "
                f"{getattr(row, 'time', '—')} · L{lap if pd.notna(lap) else '—'} · "
                f"P{position if pd.notna(position) else '—'}"
            )
        selected_label = st.selectbox("Clip", labels, key="radio_clip_selection")
        selected_idx = int(selected_label.split("·", 1)[0].strip())
        display_columns = [
            column for column in ("driver", "time", "lap", "position", "compound")
            if column in filtered
        ]
        st.dataframe(
            filtered[display_columns],
            use_container_width=True,
            hide_index=True,
            height=270,
            row_height=27,
        )
        st.caption(f"Showing {len(filtered)} of {len(clips)} clips.")

    selected = clips[clips["idx"] == selected_idx].iloc[0]
    with right, st.container(key="radio_player"):
        st.markdown('<div class="rh-radio-label"><span>TEAM RADIO / SELECTED CLIP</span><span class="rh-waveform" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></span></div>', unsafe_allow_html=True)
        st.markdown(f"##### {selected.get('driver', '—')} · {selected.get('time', '—')}")
        metadata = st.columns(4)
        for column, (label, value) in zip(
            metadata,
            [
                ("Lap", selected.get("lap", "—")),
                ("Position", selected.get("position", "—")),
                ("Tyre", selected.get("compound", "—")),
                ("Tyre age", selected.get("tyre_age", "—")),
            ],
        ):
            with column:
                metric_card(label, "—" if pd.isna(value) else value, status="info")
        local_value = selected.get("local_path", "")
        local_path = Path(str(local_value)) if pd.notna(local_value) and str(local_value).strip() else None
        source_url = selected.get("recording_url", "")
        if local_path and local_path.exists():
            audio = local_path.read_bytes()
            st.audio(audio, format="audio/mp3")
            st.download_button(
                "Download selected MP3",
                data=audio,
                file_name=local_path.name,
                mime="audio/mpeg",
                key="radio_mp3_download",
                use_container_width=True,
            )
        elif pd.notna(source_url) and str(source_url).strip():
            st.audio(str(source_url))
        else:
            empty_state("Audio unavailable", "This archive row has no local file or public recording URL.")
        st.caption(
            f"{selected.get('driver_name', '')} · {selected.get('team', '')} · "
            f"last lap {selected.get('last_lap', '—')}"
        )

    section_title("Session exports", "Portable metadata for editing and archive work.")
    export_columns = st.columns(2)
    csv_path = Path(radio_data["csv_path"])
    with export_columns[0]:
        if csv_path.exists():
            st.download_button(
                "Download session CSV",
                data=csv_path.read_bytes(),
                file_name=csv_path.name,
                mime="text/csv",
                key="radio_csv_download",
                use_container_width=True,
            )
    json_value = radio_data.get("json_path")
    json_path = Path(json_value) if json_value else None
    with export_columns[1]:
        if json_path and json_path.exists():
            st.download_button(
                "Download session JSON",
                data=json_path.read_bytes(),
                file_name=json_path.name,
                mime="application/json",
                key="radio_json_download",
                use_container_width=True,
            )


def _category_files(locations: dict[str, Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[Path] = set()
    specific_locations = [
        (category, folder)
        for category, folder in locations.items()
        if category != "Recent exports"
    ]
    for category, folder in specific_locations:
        if not folder.exists():
            continue
        for path in folder.rglob("*"):
            if not path.is_file():
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            rows.append(
                {
                    "path": path,
                    "name": path.name,
                    "type": path.suffix.lower().lstrip(".") or "file",
                    "size": path.stat().st_size,
                    "modified": datetime.fromtimestamp(path.stat().st_mtime),
                    "category": category,
                }
            )
    recent_root = locations.get("Recent exports")
    if recent_root and recent_root.exists():
        for path in recent_root.rglob("*"):
            if not path.is_file() or path.resolve() in seen:
                continue
            rows.append(
                {
                    "path": path,
                    "name": path.name,
                    "type": path.suffix.lower().lstrip(".") or "file",
                    "size": path.stat().st_size,
                    "modified": datetime.fromtimestamp(path.stat().st_mtime),
                    "category": "Recent exports",
                }
            )
    return rows


def _render_file_rows(rows: list[dict[str, Any]], key_prefix: str) -> None:
    if not rows:
        empty_state("No matching files", "Adjust the filters or generate a new output.")
        return
    for index, row in enumerate(rows[:20]):
        columns = st.columns([4.2, 1, 1.2, 1.6, 1.4])
        columns[0].markdown(f"**{row['name']}**  \n<small>{row['category']}</small>", unsafe_allow_html=True)
        columns[1].caption(row["type"].upper())
        columns[2].caption(f"{row['size'] / 1024:.1f} KB")
        columns[3].caption(row["modified"].strftime("%Y-%m-%d %H:%M"))
        mime = mimetypes.guess_type(row["name"])[0] or "application/octet-stream"
        columns[4].download_button(
            "Download",
            data=row["path"].read_bytes(),
            file_name=row["name"],
            mime=mime,
            key=f"{key_prefix}_{index}_{_safe_name(row['name'])}_{row['size']}",
            use_container_width=True,
        )


def render_files_section(
    *,
    output_dir: Path,
    telemetry_dir: Path,
    chart_dir: Path,
    radio_dir: Path,
    replay_dir: Path,
    assets_dir: Path,
    hud_export_dir: Path | None = None,
    hud_frames_dir: Path | None = None,
) -> None:
    section_title("Files", "Search, sort and download local studio artifacts.")
    locations = {
        "Recent exports": output_dir,
        "Telemetry": telemetry_dir,
        "Charts": chart_dir,
        "Radio": radio_dir,
        "Replay cache": replay_dir,
        "HUD exports": hud_export_dir or output_dir / "hud_exports",
        "HUD frames": hud_frames_dir or output_dir / "hud_frames",
        "Assets": assets_dir,
    }
    rows = _category_files(locations)
    types = sorted({row["type"] for row in rows})
    toolbar = st.columns([1.6, 1, 1, 1.2])
    search = toolbar[0].text_input("Search", placeholder="filename or folder")
    file_type = toolbar[1].selectbox("File type", ["All", *types])
    category = toolbar[2].selectbox("Category", ["All", *locations])
    sort = toolbar[3].selectbox("Sort by", ["Modified", "Size", "Name"])
    filtered = [
        row for row in rows
        if (not search or search.lower() in row["name"].lower() or search.lower() in str(row["path"]).lower())
        and (file_type == "All" or row["type"] == file_type)
        and (category == "All" or row["category"] == category)
    ]
    if sort == "Modified":
        filtered.sort(key=lambda row: row["modified"], reverse=True)
    elif sort == "Size":
        filtered.sort(key=lambda row: row["size"], reverse=True)
    else:
        filtered.sort(key=lambda row: row["name"].lower())

    summary = st.columns(3)
    with summary[0]:
        metric_card("Matching files", len(filtered), f"{len(rows)} indexed", "info")
    with summary[1]:
        metric_card("Disk footprint", f"{sum(row['size'] for row in filtered) / (1024 ** 2):.1f} MB", "Current filter", "info")
    with summary[2]:
        metric_card("Newest output", filtered[0]["name"] if filtered else "—", "Sorted view", "good" if filtered else "warn")

    tabs = st.tabs(["Recent exports", "Telemetry", "Charts", "Radio", "Replay cache", "HUD exports", "HUD frames", "Assets"])
    tab_names = list(locations)
    for tab, name in zip(tabs, tab_names):
        with tab:
            category_rows = [
                row for row in filtered
                if (name == "Recent exports" and row["category"] != "Assets")
                or row["category"] == name
            ]
            if name == "Recent exports":
                category_rows = category_rows[:20]
            _render_file_rows(category_rows, f"files_{_safe_name(name)}")
