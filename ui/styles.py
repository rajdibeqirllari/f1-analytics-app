from pathlib import Path

import streamlit as st


def inject_styles() -> None:
    """Apply the studio design system without altering exported graphics."""
    css = Path(__file__).with_name("studio.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
