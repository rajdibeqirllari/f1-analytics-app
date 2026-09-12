from __future__ import annotations

from datetime import datetime
import html
from pathlib import Path
import traceback
from typing import Any

import streamlit as st


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def render_header(active_workspace: str) -> str:
    st.markdown(
        f"""
        <div class="f1-shell">
          <header class="f1-header">
            <div class="f1-brand">
              <div class="f1-monogram" aria-hidden="true"><i></i><i></i><i></i></div>
              <div><div class="f1-brand-mark">RACE <span>HYPE</span></div>
              </div>
            </div>
          </header>
        </div>
        """,
        unsafe_allow_html=True,
    )
    return active_workspace


def render_nav(workspaces: list[str], active_workspace: str) -> str:
    if active_workspace not in workspaces:
        active_workspace = workspaces[0]
    selected = st.segmented_control(
        "Workspace",
        options=workspaces,
        default=None if "workspace_nav_control" in st.session_state else active_workspace,
        key="workspace_nav_control",
        label_visibility="collapsed",
        selection_mode="single",
    )
    return selected or active_workspace


def metric_card(
    label: str,
    value: str,
    caption: str | None = None,
    status: str | None = None,
) -> str:
    tone = status if status in {"good", "info", "warn"} else ""
    dot = f'<span class="rh-status-dot {tone}" role="img" aria-label="{_esc(status)}" title="{_esc(status)}"></span>' if status else ""
    value_class = " is-long" if len(str(value)) > 23 else ""
    markup = (
        '<div class="f1-metric-card">'
        f'<div class="f1-metric-label">{_esc(label)}</div>'
        f'<div class="f1-metric-value{value_class}" title="{_esc(value)}">{_esc(value)}</div>'
    )
    if caption:
        markup += f'<div class="f1-metric-caption">{_esc(caption)}</div>'
    markup += dot + "</div>"
    st.markdown(markup, unsafe_allow_html=True)
    return markup


def status_banner(text: str, tone: str = "info") -> str:
    safe_tone = tone if tone in {"good", "info", "warn"} else "info"
    markup = f'<div class="f1-status-{safe_tone}">{_esc(text)}</div>'
    st.markdown(markup, unsafe_allow_html=True)
    return markup


def section_title(title: str, subtitle: str | None = None) -> str:
    markup = f"""
    <div class="f1-section-title">
      <div>
        <h2>{_esc(title)}</h2>
        {f'<p>{_esc(subtitle)}</p>' if subtitle else ''}
      </div>
    </div>
    """
    st.markdown(markup, unsafe_allow_html=True)
    return markup




def download_card(
    title,
    description,
    filename,
    rows,
    duration,
    data,
    mime,
    *,
    source: str | None = None,
    key: str | None = None,
) -> None:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        st.caption(description)
        cols = st.columns(3)
        cols[0].caption(f"FORMAT · {Path(filename).suffix.lstrip('.').upper() or 'FILE'}")
        cols[1].caption(f"ROWS · {rows:,}" if isinstance(rows, int) else f"ROWS · {rows}")
        cols[2].caption(f"DURATION · {duration}")
        st.download_button(
            f"Download {Path(filename).suffix.lstrip('.').upper() or 'file'}",
            data=data,
            file_name=filename,
            mime=mime,
            key=key or f"download_{filename}",
            use_container_width=True,
        )


def empty_state(title: str, message: str, action_label=None) -> str:
    action = f"<small>{_esc(action_label)}</small>" if action_label else ""
    markup = (
        '<div class="f1-empty"><div>'
        f"<strong>{_esc(title)}</strong><span>{_esc(message)}</span>{action}"
        "</div></div>"
    )
    st.markdown(markup, unsafe_allow_html=True)
    return markup


def technical_error_box(user_message, technical_details=None) -> None:
    st.error(str(user_message))
    details = technical_details
    if details is None:
        details = traceback.format_exc()
    with st.expander("Technical details", expanded=False):
        st.code(str(details), language="text")


def timestamp_caption(filename: str | Path) -> None:
    path = Path(filename)
    when = datetime.fromtimestamp(path.stat().st_mtime) if path.exists() else datetime.now()
    st.caption(f"{path.name} · generated {when:%Y-%m-%d %H:%M:%S}")
