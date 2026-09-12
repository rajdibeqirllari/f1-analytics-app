from __future__ import annotations

import base64
import html
import json
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from ui.constructor_config import CONSTRUCTOR_ASSETS, DEBUG_CAR_ALIGNMENT, SHOWCASE_SETTINGS, constructors_from_standings

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets" / "f1_2026"
COMPONENT_DIR = ROOT / "components" / "constructor_showcase"


@st.cache_data(show_spinner=False, max_entries=22)
def _car_data_uri(path: str, modified_ns: int) -> str:
    """Inline media needs no exposed paths or static-server changes.

    The mtime key invalidates the cache when an artist replaces a PNG.
    """
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode("ascii")


def render_studio_hero(latest: dict[str, Any], overview: dict[str, Any]) -> None:
    event = html.escape(str(latest.get("event_name", "Session archive")))
    year = html.escape(str(latest.get("year", "")))
    constructors = constructors_from_standings(overview.get("constructor_standings", []))
    ranked = bool(constructors)
    if not ranked:
        # A static, explicitly unranked image on provider failure, not invented
        # championship positions or an old manually ordered scroll sequence.
        constructors = [{**CONSTRUCTOR_ASSETS["mercedes"], "id": "mercedes", "index": None, "field_size": 0}]
    cars, labels = [], []
    for item in constructors:
        path = ASSET_DIR / item["image"]
        uri = _car_data_uri(str(path), path.stat().st_mtime_ns)
        name = html.escape(item["name"])
        calibration = f'translate({item["x"]}px,{item["y"]}px) scale({item["scale"]})'
        cars.append(
            f'<div class="rh-scanner-car" data-car="{item["id"]}" aria-hidden="true">'
            f'<div class="rh-car-calibration" style="transform:{calibration}">'
            f'<img src="{uri}" alt="" width="2048" height="500" loading="eager" decoding="async" draggable="false">'
            '</div></div>'
        )
        rank_label = f'P{item["index"]} / {item["field_size"]}' if ranked else "UNRANKED"
        labels.append(
            f'<div class="rh-constructor-label" aria-hidden="true"><span>{name}</span>'
            f'<span>{rank_label}</span></div>'
        )
    css = (COMPONENT_DIR / "showcase.css").read_text(encoding="utf-8")
    width = SHOWCASE_SETTINGS["carWidthPercent"]
    mobile_width = SHOWCASE_SETTINGS["mobileCarWidthPercent"]
    # Native page DOM for real page sticky behavior; only the controller is
    # embedded, following the existing replay's inline components.html pattern.
    st.markdown(f'''<style>{css}</style>
<div class="rh-constructor-story" id="rh-constructor-story" style="--rh-car-width:{width}%;--rh-car-mobile-width:{mobile_width}%">
<div class="rh-constructor-sticky">
<section class="rh-hero">
<div class="rh-hero-copy"><div class="rh-eyebrow">Your seat on the pit wall</div>
<h1>Every lap.<br><em>Every detail.</em></h1>
<p>Read the race. Find the edge. Turn the data into something worth watching.</p>
<div class="rh-hero-meta"><span>RACE WEEKEND /</span> {event}<span> · {year}</span></div></div>
<div class="rh-hero-art rh-scanner" role="group" aria-label="2026 constructor showcase: {html.escape(constructors[0]['name'])}">
<div class="rh-scanner-heading">AERO / CHASSIS / TELEMETRY</div>
<div class="rh-scanner-grid" aria-hidden="true"></div>
<div class="rh-scanner-frame" aria-hidden="true"><i></i><i></i><i></i><i></i></div>
<div class="rh-scanner-axis" aria-hidden="true"></div>
<div class="rh-car-stage">{"".join(cars)}
<div class="rh-alignment-guides" aria-hidden="true"><i class="rh-guide-center"></i><i class="rh-guide-baseline"></i><i class="rh-guide-rear"></i><i class="rh-guide-front"></i></div></div>
<div class="rh-scanner-footer"><div class="rh-constructor-labels">{"".join(labels)}</div>
<div class="rh-scanner-progress" aria-hidden="true"><i></i></div>
<div class="rh-scanner-caption"><span>2026 CONSTRUCTORS' CHAMPIONSHIP</span><span class="rh-scroll-hint">{"SCROLL TO EXPLORE ↓" if ranked else "STANDINGS UNAVAILABLE"}</span></div></div>
<div class="rh-alignment-debug" hidden><output></output><div><button type="button" data-debug-step="-1">Previous</button><button type="button" data-debug-step="1">Next</button></div></div>
</div></section></div></div>''', unsafe_allow_html=True)

    payload = {"constructors": constructors, "settings": SHOWCASE_SETTINGS, "debug": DEBUG_CAR_ALIGNMENT, "enabled": ranked}
    encoded = json.dumps(payload, ensure_ascii=True).replace("<", "\\u003c")
    timeline_js = (COMPONENT_DIR / "timeline.js").read_text(encoding="utf-8")
    controller_js = (COMPONENT_DIR / "showcase.js").read_text(encoding="utf-8")
    components.html(
        f'<script>{timeline_js}\nconst scannerConfig = {encoded};\n{controller_js}</script>',
        height=0, scrolling=False,
    )
