"""All eleven 2026 constructors as individually parameterised chassis with liveries, sponsor decals and number plates.

Run (from C:\\f1hud_app):
  .venv\\Scripts\\python.exe scripts\\cars2026\\make_decals.py
  tools\\blender\\blender-4.5.9-windows-x64\\blender.exe --background --factory-startup --python-exit-code 1 ^
      --python scripts\\cars2026\\build_field.py [-- --only mercedes,red_bull] [--clay]

Per constructor: assets/3d/cars2026/<team>.blend (editable) and frontend/public/cars/2026/<team>.glb (Draco, LOD0/LOD1,
steer_/wheel_ pivots, cam_pod/cam_cockpit mounts). Teammates share the GLB (geometry, paint, sponsor atlas); the
number plates use the material `<team>_number` and the T-cam `<team>_tcam`, which the browser clones per driver.

Geometry: the 2026 template of scripts/qatar/build_cars_blend.py (W17 / RB22 archetypes) blended and adjusted per team
(see TEAMS[...]['geom']); paint: vertex-colour zones; sponsors: wordmark decals shrink-wrapped onto the bodywork with UVs
oriented so the text reads left-to-right from the side it is seen from.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'cars2026'))
from teams import TEAMS  # noqa: E402

spec_ = importlib.util.spec_from_file_location('carbase', str(ROOT / 'scripts/qatar/build_cars_blend.py'))
B = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(B)

OUT_BLEND = ROOT / 'assets/3d/cars2026'
OUT_GLB = ROOT / 'frontend/public/cars/2026'
DECALS = ROOT / 'assets/3d/cars2026/decals'
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
ONLY = None
if '--only' in ARGS:
    ONLY = set(ARGS[ARGS.index('--only') + 1].split(','))
CLAY = '--clay' in ARGS


def lin(hexs):
    h = hexs.lstrip('#')
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)


def blend(a, b, k):
    return [tuple(x + (y - x) * k for x, y in zip(ra, rb)) for ra, rb in zip(a, b)]


W17, RB = B.SPECS['w17'], B.SPECS['rb22']


def make_spec(key, t):
    g = t['geom']
    nose, tip_x = g['nose']
    body = {'high': W17['body'], 'arrow': RB['body'], 'mid': blend(W17['body'], RB['body'], 0.5), 'low': blend(W17['body'], RB['body'], 1.0)}[nose]
    body = [list(r) for r in body]
    body[0][0] = tip_x
    if nose == 'low':
        body[0][2], body[0][3] = 0.135, 0.20
        body[1][2] = 0.14
    pods_w = [(x, list(p)) for x, p in W17['pods']]
    pods_r = [(x, list(p)) for x, p in RB['pods']]

    def pods_blend(k):
        return [(xa + (xb - xa) * k, [(ya + (yb - ya) * k, za + (zb - za) * k) for (ya, za), (yb, zb) in zip(pa, pb)]) for (xa, pa), (xb, pb) in zip(pods_w, pods_r)]
    pod = {'high_flat': pods_blend(0.0), 'bathtub': pods_blend(1.0), 'ramp': pods_blend(0.55)}.get(g['pods'])
    if g['pods'] == 'wedge':      # lower top, stronger rearward taper
        pod = [(x, [(y * (1 - 0.06 * i), z - 0.045 - 0.02 * i if z > 0.4 else z) for (y, z) in p]) for i, (x, p) in enumerate(pods_blend(0.3))]
    if g['pods'] == 'long_slim':  # narrower, carried further back
        pod = [(x - 0.06 * i, [(0.30 + (y - 0.30) * 0.86, z - 0.01) for (y, z) in p]) for i, (x, p) in enumerate(pods_blend(0.15))]
    inlet = dict(W17['inlet'] if g['inlet'] == 'tall' else RB['inlet'])
    inlet['x'] = pod[0][0]
    ab = dict(W17['airbox']) if g['airbox'] in ('round', 'oval') else dict(RB['airbox'])
    if g['airbox'] == 'oval':
        ab.update(top=0.975, w=0.115)
    if g['airbox'] == 'tri':
        ab.update(top=0.965)
    rw = dict(W17['rw'])
    rw['pylon'] = {'swan': 'swan', 'twin': 'twin', 'single': 'twin'}[g['rw']]
    fw = dict(W17['fw'] if nose in ('high', 'mid') else RB['fw'])
    fw['endplate_fin'] = g['fw_endfin']
    p = t['paint']
    return dict(name=t['chassis'], team=t['team'], season=2026, sources=['see scripts/cars2026/teams.py SOURCES'], look=t['notes'],
                body=[tuple(r) for r in body], nose_on_wing=nose in ('arrow', 'low'), pods=pod, inlet=inlet, airbox=ab,
                fin=g['fin'], fin_h=0.10, fw=fw, rw=rw, sus_front='pushrod', sus_rear='pushrod', walls=g['walls'],
                colours=dict(paint=lin(p['base']), paint2=lin(p['second']), accent=lin(p['accent']), helmet=lin(p['second']),
                             finish=t.get('finish', 'gloss')), zones=set(p['zones']), single_pylon=g['rw'] == 'single')


def livery(key, spec, x, y, z, part):
    """Paint zones per team (TEAMS[...]['paint']['zones']); returns a linear RGB colour."""
    c, Z = spec['colours'], spec['zones']
    base, sec, acc = c['paint'], c['paint2'], c['accent']
    if 'split_sides' in Z:
        col = base if y >= 0 else sec
        if part == 'pod' and abs(z - 0.55) < 0.012:
            return acc
        return col
    if part == 'airbox':
        if 'airbox_yellow' in Z and x > -0.75:
            return acc
        if 'airbox_white' in Z:
            return sec
        if 'engine_silver' in Z:
            return sec if z < 0.9 else base
        if 'black_engine' in Z:
            return sec
    if part == 'body':
        if ('nose_tip_yellow' in Z or 'nose_tip_dark' in Z) and x > 2.42:
            return acc if 'nose_tip_yellow' in Z else sec
        if 'nose_top_pink' in Z and x > 1.2 and z > 0.36 + (2.6 - x) * 0.07:
            return acc
        if 'engine_pink_strip' in Z and abs(y) < 0.045 and z > 0.5 and x < -0.2:
            return acc
        if 'engine_silver' in Z and z > 0.56 and -1.6 < x < -0.15:
            return sec
        if 'engine_white_band' in Z and -1.45 < x < -0.55 and z > 0.48:
            return sec
        if 'black_engine' in Z and x < -0.45 and z > 0.42:
            return sec
        if 'blue_engine_sweep' in Z and x < -0.3 and z > 0.62 + 0.18 * (x + 0.3):
            return sec
        if 'engine_rear_dark' in Z and x < -1.25:
            return sec
        if 'teal_lines' in Z and 1.2 < x < 2.6 and abs(y) > 0.06 and abs(z - (0.33 + (2.6 - x) * 0.09)) < 0.018:
            return acc
        if 'lime_stripe' in Z and 1.0 < x < 2.6 and abs(y) > 0.06 and abs(z - (0.31 + (2.6 - x) * 0.09)) < 0.016:
            return acc
    if part == 'pod':
        if 'red_pinstripe' in Z and abs(z - 0.40) < 0.010:
            return lin('#DB0A40')
        if 'teal_lines' in Z and abs(z - 0.60) < 0.015 and x > -0.6:
            return acc
        if 'lime_stripe' in Z and abs(z - 0.58) < 0.015 and x > -0.8:
            return acc
        if 'red_sweep' in Z and 0.33 < z < 0.40 + 0.05 * x:
            return acc
        if 'red_accent_band' in Z and abs(x - 0.15) < 0.05:
            return acc
    if ('lower_dark' in Z or 'blue_lower' in Z or 'black_lower' in Z) and z < 0.27:
        return sec
    return base


B.livery_colour = livery


# ------------------------------------------------------------------ decals
def decal_plane(name, centre, right, up, w, h, uvrect, mat, target, parent, nx=14, ny=4, flip_u=False):
    """A subdivided plane centred at `centre` spanning `right` (text left->right) x `up` (text bottom->top),
    shrink-wrapped onto `target`; UVs map the atlas rectangle so the text reads correctly from outside."""
    right, up = Vector(right).normalized(), Vector(up).normalized()
    normal = right.cross(up).normalized()
    verts, faces, uvs = [], [], []
    u0, v0, u1, v1 = uvrect
    for j in range(ny + 1):
        for i in range(nx + 1):
            a, b = i / nx, j / ny
            p = Vector(centre) + right * ((a - 0.5) * w) + up * ((b - 0.5) * h) + normal * 0.03
            verts.append(tuple(p))
            uvs.append((u0 + (u1 - u0) * (1 - a if flip_u else a), v0 + (v1 - v0) * b))
    for j in range(ny):
        for i in range(nx):
            k = j * (nx + 1) + i
            faces.append((k, k + 1, k + nx + 2, k + nx + 1))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    uv = me.uv_layers.new(name='UVMap')
    uv.data.foreach_set('uv', [c for li in me.loops for c in uvs[li.vertex_index]])
    me.update()
    ob = bpy.data.objects.new(name, me)
    ob.data.materials.append(mat)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = parent
    if target is not None:
        md = ob.modifiers.new('wrap', 'SHRINKWRAP')
        md.target = target
        md.wrap_method = 'NEAREST_SURFACEPOINT'
        md.wrap_mode = 'OUTSIDE_SURFACE'
        md.offset = 0.004
    return ob


def decal_material(key, atlas):
    m = bpy.data.materials.new(f'{key}_decals')
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes['Principled BSDF']
    t = nt.nodes.new('ShaderNodeTexImage')
    t.image = bpy.data.images.load(str(atlas))
    nt.links.new(t.outputs['Color'], b.inputs['Base Color'])
    nt.links.new(t.outputs['Alpha'], b.inputs['Alpha'])
    b.inputs['Roughness'].default_value = 0.35
    return m


def number_material(key):
    """Placeholder number plate (white "00"); the browser draws each driver's own number on a per-car clone."""
    img = bpy.data.images.new(f'{key}_number_placeholder', 128, 64, alpha=True)
    px = np.zeros((64, 128, 4), np.float32)
    px[..., :3] = 1.0
    px[16:48, 20:108, 3] = 1.0
    img.pixels.foreach_set(px.ravel())
    img.pack()
    m = bpy.data.materials.new(f'{key}_number')
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes['Principled BSDF']
    t = nt.nodes.new('ShaderNodeTexImage')
    t.image = img
    nt.links.new(t.outputs['Color'], b.inputs['Base Color'])
    nt.links.new(t.outputs['Alpha'], b.inputs['Alpha'])
    return m


def find(name):
    return bpy.data.objects.get(name)


def add_decals(key, spec, t, root):
    rects = json.loads((DECALS / f'{key}.json').read_text(encoding='utf-8'))
    dm = decal_material(key, DECALS / f'{key}.png')
    nm = number_material(key)
    lod0 = find('LOD0')
    body, podL, podR = find('body_LOD0'), find('sidepod_LOD0_L'), find('sidepod_LOD0_R')
    air = find('airbox_LOD0')
    rwepL, rwepR = find('rw_endplate_LOD0_L'), find('rw_endplate_LOD0_R')
    fwepL, fwepR = find('fw_endplate_LOD0_L'), find('fw_endplate_LOD0_R')
    flap = find('rw_flap_LOD0')
    pod0 = spec['pods'][1]
    pod_y = max(y for y, z in pod0[1])
    rw, fw = spec['rw'], spec['fw']
    X = (1, 0, 0)

    def fit(rect, wmax, hmax):
        a = rect['aspect']
        w = min(wmax, hmax * a)
        return w, w / a
    made = []
    for side, s in (('L', 1), ('R', -1)):
        # side views: viewer on +Y looks towards -Y, so "right" is -X (rear); on -Y it is +X
        right = (-s, 0, 0)
        up = (0, 0, 1)
        for placement, centre, (wmax, hmax), target in (
                ('pod', (pod0[0] - 0.35, s * (pod_y + 0.01), 0.47), (0.80, 0.15), podL if s > 0 else podR),
                ('engine', (-0.72, s * 0.31, 0.57), (0.50, 0.10), body),
                ('nose_side', (1.95, s * 0.12, 0.31), (0.42, 0.065), body),
                ('rw_ep', (rw['x_te'] + 0.28, s * (rw['span'] + 0.02), 0.74), (0.42, 0.12), rwepL if s > 0 else rwepR),
                ('fw_ep', (fw['x_le'] - 0.27, s * (fw['span'] + 0.012), 0.16), (0.36, 0.08), fwepL if s > 0 else fwepR)):
            r = rects.get(placement)
            if not r or target is None:
                continue
            w, h = fit(r, wmax, hmax)
            made.append(decal_plane(f'decal_{placement}_{side}', centre, right, up, w, h, r['uv'], dm, target, lod0))
        # driver number on each side of the engine cover (per-driver texture in the browser)
        # high / long sidepods cover the engine-cover side here: the number goes on the pod's outer surface instead
        high = t['geom']['pods'] in ('high_flat', 'long_slim')
        made.append(decal_plane(f'number_side_{side}', (-1.30, s * (0.40 if high else 0.22), 0.47), right, up, 0.31, 0.18, (0, 0, 1, 1), nm,
                                (podL if s > 0 else podR) if high else body, lod0))   # engine cover, ahead of the rear wheel
    # tops: rear wing flap (read from behind: right = -Y, text up = +X), airbox sides use 'airbox' if present
    r = rects.get('rw_top')
    if r and flap is not None:
        w, h = fit(r, 0.85, 0.11)
        made.append(decal_plane('decal_rw_top', (rw['x_te'] + 0.10, 0, rw['flap_z'] + 0.06), (0, -1, 0), (1, 0, 0), w, h, r['uv'], dm, flap, lod0, ny=2))
    r = rects.get('airbox')
    if r and air is not None:
        w, h = fit(r, 0.34, 0.07)
        for side, s in (('L', 1), ('R', -1)):
            made.append(decal_plane(f'decal_airbox_{side}', (spec['airbox']['x0'] - 0.45, s * 0.12, spec['airbox']['top'] - 0.09), (-s, 0, 0), (0, 0, 1), w, h, r['uv'], dm, air, lod0))
    # number on the nose, read from the front (right = +Y, text up = -X)
    tip = spec['body'][0][0]
    made.append(decal_plane('number_nose', (tip - 0.62, 0, 0.45), (0, 1, 0), (-1, 0, 0), 0.16, 0.10, (0, 0, 1, 1), nm, body, lod0, nx=6, ny=4))
    return made


def build(key):
    t = TEAMS[key]
    spec = make_spec(key, t)
    B.SPECS[key] = spec
    bpy.ops.wm.read_factory_settings(use_empty=True)
    root = B.build_car(key)
    root['constructor'] = key
    root['chassis'] = t['chassis']
    root['drivers'] = json.dumps(t['drivers'])
    # diffuser sidewalls only where the team runs them; single central pylon for 'single'
    if not spec['walls']:
        for o in list(bpy.data.objects):
            if o.name.startswith('diffuser_wall'):
                bpy.data.objects.remove(o, do_unlink=True)
    tc = bpy.data.materials.new(f'{key}_tcam')
    tc.use_nodes = True
    tc.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.01, 0.01, 0.01, 1)
    for o in bpy.data.objects:
        if o.name.startswith('tcam_'):
            o.data.materials[0] = tc
    add_decals(key, spec, t, root)
    OUT_BLEND.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND / f'{key}.blend'), compress=True)
    path = OUT_GLB / f'{key}.glb'
    OUT_GLB.mkdir(parents=True, exist_ok=True)
    kw = dict(filepath=str(path), export_format='GLB', export_yup=True, export_apply=True, export_extras=True,
              export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=6,
              export_draco_position_quantization=14, export_draco_texcoord_quantization=12, export_image_format='WEBP', export_image_quality=88)
    try:
        bpy.ops.export_scene.gltf(export_vertex_color='ACTIVE', **kw)
    except TypeError:
        bpy.ops.export_scene.gltf(**kw)
    tri = B.stats()
    print(f'{key}: {t["chassis"]} GLB {path.stat().st_size / 1e3:.0f} KB tris {tri}')
    if CLAY:
        B.clay_render(key)


for k in TEAMS:
    if ONLY and k not in ONLY:
        continue
    build(k)
