"""Team-inspired presentation colors from the selected session's team metadata.

Never map driver codes to today's teams: historical Hamilton laps, for example,
must retain the team recorded in that historical session.
"""
import re

RENDER_VERSION='qvist-team-colors-v30-surface-locked-exact-trails'
CAR_CREDIT='Car: Qvist_designs / CC BY 4.0 · modified'
CAR_SOURCE='https://sketchfab.com/3d-models/f1-2026-concept-polygon-model-ea3bde709b1e4dc9b0ec8557d106ed42'
CAR_ATTRIBUTION=('F1 2026 concept (polygon model) by Qvist_designs. '+CAR_SOURCE+
                 ' Licensed CC BY 4.0: https://creativecommons.org/licenses/by/4.0/. '
                 'Modified: scale/orientation, mesh welding, reduced detail and team-inspired materials.')
STYLES={
    'ferrari':('#e52235','#ffe16a','#ff4555'),
    'mercedes':('#9da4ac','#2ce6d2','#42ddc8'),
    'mclaren':('#ff8700','#69dbe7','#ffa135'),
    'redbull':('#142954','#ffd441','#5281eb'),
    'astonmartin':('#087f69','#d4f84c','#32c8a6'),
    'alpine':('#2877db','#f394c5','#65a6ff'),
    'williams':('#1466db','#e6f6ff','#4a9fff'),
    'haas':('#e0e4e8','#ed3040','#e0e4e8'),
    'racingbulls':('#344fcb','#e1e7f5','#90b8ff'),
    'sauber':('#44cf20','#101714','#7aff56'),
    'audi':('#999fa6','#ee333b','#ff5a62'),
    'cadillac':('#50545b','#d4b780','#d4b780'),
    'renault':('#f4d421','#171a20','#ffe440'),
    'racingpoint':('#ed8ac4','#393782','#fface0'),
    'alfaromeo':('#9e1831','#eeeeee','#df5069'),
}


def team_key(team):
    name=re.sub(r'[^a-z0-9]','',str(team).lower())
    for key in STYLES:
        if key in name:return key
    if name in ('rb','rbf1team') or 'alphatauri' in name or 'tororosso' in name:return 'racingbulls'
    if 'kick' in name:return 'sauber'
    return name


def rgb(color):
    """sRGB bytes to Blender linear RGB, so rendered paint matches UI swatches."""
    values=[int(color[i:i+2],16)/255 for i in (1,3,5)]
    return tuple(v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values)


def lighten(color,fraction=.48):
    return '#'+''.join(f'{round(int(color[i:i+2],16)*(1-fraction)+255*fraction):02x}' for i in (1,3,5))


def comparison_styles(laps):
    result=[];seen=set()
    for lap in laps:
        team=lap['team'] if isinstance(lap,dict) else lap.team
        fallback=lap.get('color') if isinstance(lap,dict) else lap.color
        if not isinstance(fallback,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',fallback):fallback='#a7b4c2'
        key=team_key(team);body,accent,display=STYLES.get(key,(fallback,'#e5ecf3',fallback))
        if key in seen:accent=lighten(accent,.7);display=lighten(display)
        seen.add(key)
        result.append({'team':key,'body':body,'accent':accent,'display':display})
    return result
