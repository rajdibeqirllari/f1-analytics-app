"""Compatibility entry point: read-only source indexing, never track edits."""
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).with_name("index_singapore_sources.py")),run_name="__main__")
