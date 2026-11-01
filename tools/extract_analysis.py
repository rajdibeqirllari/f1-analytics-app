"""One-time mechanical extraction of existing calculations, without importing app.py."""
import ast
from pathlib import Path

root=Path(__file__).resolve().parents[1]
source=(root/'app.py').read_text(encoding='utf-8-sig')
tree=ast.parse(source)
lines=source.splitlines(keepends=True)
skip={'render_driver_media_gallery','render_driver_picker_preview','_build_generic_car_placeholder','get_driver_catalog'}
functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.lineno<2668 and n.name not in skip]
constants=['THEME','HIGHLIGHT','FALLBACK_2026_RACES']
parts=['''"""Existing FastF1 analysis calculations extracted from app.py.

No Streamlit initialization; rendering is serialized by the API job worker.
"""
from pathlib import Path
from datetime import date
import fastf1
import fastf1.plotting
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
from matplotlib.ticker import FuncFormatter
import matplotlib.patheffects as path_effects
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import matplotlib.colors as mcolors
BASE_DIR=Path(__file__).resolve().parents[1]
ASSET_DIR=BASE_DIR/'assets'
COLOR_MODE='FastF1 Official'
CUSTOM_COLOR_A='#00D2BE'
CUSTOM_COLOR_B='#DC0000'
MONO_COLOR_A='#FFFFFF'
MONO_COLOR_B='#8B5CF6'
image_format='16:9 (YouTube)'
plt.style.use('dark_background')
''']
for node in tree.body:
    if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in constants for t in node.targets):
        parts.append(''.join(lines[node.lineno-1:node.end_lineno]))
for node in functions:
    parts.append(''.join(lines[node.lineno-1:node.end_lineno]))
(root/'services'/'analysis_service.py').write_text('\n\n'.join(parts),encoding='utf-8')
print(f'Extracted {len(functions)} existing functions, excluding all UI entry points.')
