from __future__ import annotations

import html
import json
from pathlib import Path

import streamlit.components.v1 as components


ROOT = Path(__file__).resolve().parents[1]
COMPONENT_DIR = ROOT / "components" / "race_replay_web"


def render_embedded_replay(payload: dict, height: int = 720) -> None:
    """Render the browser-native race replay in an iframe-less HTML component."""
    template = (COMPONENT_DIR / "index.html").read_text(encoding="utf-8")
    css = (COMPONENT_DIR / "replay.css").read_text(encoding="utf-8")
    js = (COMPONENT_DIR / "replay.js").read_text(encoding="utf-8")
    payload_json = html.escape(json.dumps(payload, ensure_ascii=False), quote=False)
    document = (
        template
        .replace("__REPLAY_PAYLOAD__", payload_json)
        .replace("__REPLAY_CSS__", css)
        .replace("__REPLAY_JS__", js)
    )
    components.html(document, height=height, scrolling=True)
