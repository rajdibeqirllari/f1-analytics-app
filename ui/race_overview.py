from __future__ import annotations

from datetime import date
import html
from typing import Any

import pandas as pd
import streamlit as st

from services.overview_service import get_season_overview


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _number(value: Any) -> str:
    try:
        return f"{float(value):g}"
    except (ValueError, TypeError):
        return "—"


def _color(team: str) -> str:
    name = str(team).lower()
    return next((color for key, color in {
        "mclaren": "#f5a052", "ferrari": "#ff655f", "mercedes": "#67d5c2",
        "red bull": "#7d9dff", "red_bull": "#7d9dff", "williams": "#70aeef",
        "aston": "#6cbaa4", "alpine": "#e2a5d6", "haas": "#b7bfc6",
    }.items() if key in name), "#a9b4bf")


def _standings_table(rows: list[dict[str, Any]], *, teams: bool = False, error: str = "") -> None:
    if not rows:
        st.info(error or "Standings have not been published for this season yet.")
        return
    max_points = max(float(row.get("points", 0) or 0) for row in rows) or 1
    body = []
    for row in rows:
        name = row.get("team", "—") if teams else row.get("driver", "—")
        team = row.get("team", "")
        points = float(row.get("points", 0) or 0)
        bar = min(100, max(0, 100 * points / max_points))
        color = _color(team)
        identity = f'<strong>{_esc(name)}</strong>'
        if not teams:
            identity += f'<small>{_esc(team)}</small>'
        body.append(
            f'<tr><td class="rh-pos">{_esc(row.get("position", "—"))}</td>'
            f'<td><div class="rh-driver" style="--team-color:{color}">{identity}</div></td>'
            f'<td class="rh-points"><b>{_number(row.get("points"))}</b>'
            f'<span class="rh-points-track"><i style="width:{bar:.2f}%;background:{color}"></i></span></td>'
            f'<td class="rh-wins">{_number(row.get("wins"))}</td></tr>'
        )
    entity = "Team" if teams else "Driver"
    st.markdown(
        f'<div class="rh-standings-wrap"><table class="rh-standings" aria-label="{entity} championship standings">'
        f'<thead><tr><th scope="col">Pos</th><th scope="col">{entity}</th><th scope="col">Points</th><th scope="col">Wins</th></tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>', unsafe_allow_html=True,
    )


def render_race_overview(shared_overview: dict[str, Any] | None = None) -> None:
    with st.container(key="overview_heading"):
        title, season_column = st.columns([5, 1], vertical_alignment="center")
        with title:
            st.markdown('<div class="rh-page-title"><h2>Season overview</h2><p>Race results & championship standings</p></div>', unsafe_allow_html=True)
        with season_column:
            year = st.selectbox("Season", list(range(date.today().year, 2017, -1)), key="overview_season")

    with st.spinner("Loading race results…"):
        data = shared_overview if shared_overview is not None and shared_overview.get("year") == int(year) else get_season_overview(int(year))
    race = data.get("latest_race")
    errors = data.get("errors", {})
    if race:
        try:
            race_date = date.fromisoformat(str(race.get("date", ""))).strftime("%d %b %Y")
        except ValueError:
            race_date = str(race.get("date", ""))
        podium = []
        for result in race.get("results", [])[:3]:
            position = str(result.get("position", ""))
            podium.append(
                f'<div class="rh-podium-driver"><span class="rh-finish-position">P{_esc(position)}</span>'
                f'<strong>{_esc(result.get("driver", "—"))}</strong>'
                f'<span class="rh-podium-team">{_esc(result.get("team", ""))}</span>'
                f'<span class="rh-finish-time">{_esc(result.get("time") or result.get("status", ""))}</span></div>'
            )
        st.markdown(
            '<section class="rh-race-summary">'
            f'<div class="rh-race-heading"><span class="rh-label">Latest race · Round {_esc(race.get("round", ""))}</span>'
            f'<h2>{_esc(race.get("event_name", ""))}</h2>'
            f'<p>{_esc(race.get("circuit", ""))}<br>{_esc(race_date)}</p></div>'
            f'<div class="rh-podium">{"".join(podium)}</div></section>', unsafe_allow_html=True,
        )
        with st.expander("Race classification"):
            st.caption("Full finishing order · race times, points and status")
            results = pd.DataFrame(race.get("results", []))
            columns = {"position": "Pos", "driver": "Driver", "team": "Team", "time": "Time / gap", "laps": "Laps", "points": "Points", "status": "Status"}
            available = [key for key in columns if key in results]
            st.dataframe(
                results[available].rename(columns=columns), hide_index=True,
                use_container_width=True, row_height=42,
                height=min(620, 42 + 42 * len(results)),
                column_config={
                    "Pos": st.column_config.NumberColumn("Pos", width="small", format="%d"),
                    "Driver": st.column_config.TextColumn("Driver", width="medium"),
                    "Team": st.column_config.TextColumn("Team", width="medium"),
                    "Time / gap": st.column_config.TextColumn("Time / gap", width="medium"),
                    "Laps": st.column_config.NumberColumn("Laps", width="small"),
                    "Points": st.column_config.NumberColumn("Points", width="small"),
                    "Status": st.column_config.TextColumn("Status", width="medium"),
                },
            )
    else:
        st.info(errors.get("latest_race") or "No completed race results have been published for this season yet.")

    st.markdown(f'<div class="rh-championship-heading"><h2>{int(year)} Championship</h2></div>', unsafe_allow_html=True)
    with st.container(key="overview_championship"):
        drivers, teams = st.columns([1.1, 1], gap="large")
    with drivers:
        st.markdown("##### Drivers")
        _standings_table(data.get("driver_standings", []), error=errors.get("driver_standings", ""))
        driver_round = data.get("driver_standings_round")
        if driver_round:
            st.caption(f"After round {driver_round}")
    with teams:
        st.markdown("##### Constructors")
        _standings_table(data.get("constructor_standings", []), teams=True, error=errors.get("constructor_standings", ""))
        constructor_round = data.get("constructor_standings_round")
        if constructor_round:
            st.caption(f"After round {constructor_round}")
    st.caption("Results & standings · Jolpica F1")
