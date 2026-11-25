"""Mercedes W17 and Red Bull RB22 (2026) as original, parametric Blender models -> .blend + GLB for the browser.

Run (from C:\\f1hud_app):
  tools\\blender\\blender-4.5.9-windows-x64\\blender.exe --background --factory-startup --python-exit-code 1 ^
      --python scripts\\qatar\\build_cars_blend.py [-- --clay]

`--clay` also renders front three-quarter / side / rear clay views of both cars (no team colours) to
outputs/qatar/cars_clay_*.png so the silhouettes can be compared before colours.

Frame: X forward, Y left, Z up, origin on the ground midway between the axles (the browser engine's frame after
glTF's +Y-up conversion: x forward, y up, z to the right). Every shape is built here from numbers; nothing is copied
from a third-party model. Sources for the numbers are in SPECS[...]['sources'] and in assets/3d/cars2026/README.md.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[2]
TEX = ROOT / 'assets/3d/qatar/textures'
OUT_BLEND = ROOT / 'assets/3d/cars2026'
OUT_GLB = ROOT / 'frontend/public/cars/2026'
CLAY = '--clay' in sys.argv

# ----------------------------------------------------------------------------------------------------------- specs
# Dimensions: 2026 technical regulations as reported + Mercedes' published W17 sheet (wheelbase 3400 mm, width
# 1900 mm, length < 5505 mm, height 950-970 mm). Tyres: 2026 18-inch, narrower than 2025 (front ~280 mm, rear ~375 mm
# wide; ~705 / 710 mm diameter) -> reported figures, not measured. Shapes per car: see 'look'.
COMMON = dict(wheelbase=3.40, width=1.90, f_tyre=(0.705, 0.280), r_tyre=(0.710, 0.375), rim_d=0.4572)

SPECS = {
    'w17': dict(
        name='Mercedes W17 (2026)', team='Mercedes', season=2026,
        sources=['mercedesamgf1.com W17 technical specifications (Jan 2026)', 'Wikipedia: Mercedes W17',
                 'The Race, Gary Anderson W17 analysis (Jan 2026): pushrod F/R, high radiator inlet, undercut, 3-element front wing detached from nose',
                 'Hungarian GP photo, 26 Jul 2026 (Russell): livery layout, nose/front wing proportions'],
        look='slender nose ending above the 2nd flap, high narrow sidepod inlet, flat high sidepod top, deep undercut, '
             'rounded airbox, engine-cover fin, single swan-neck rear wing pylon',
        # body sections: x, half-width, z bottom, z top, squareness
        body=[(2.66, .045, .225, .285, 2.2), (2.40, .085, .205, .345, 2.4), (2.05, .125, .190, .420, 2.6), (1.70, .160, .165, .495, 2.8),
              (1.25, .205, .120, .545, 3.0), (0.80, .265, .095, .585, 3.2), (0.30, .330, .085, .615, 3.4), (-0.10, .370, .080, .650, 3.4),
              (-0.45, .360, .080, .700, 3.2), (-0.90, .300, .085, .660, 3.0), (-1.30, .220, .100, .560, 2.8), (-1.70, .140, .130, .470, 2.6),
              (-2.05, .095, .170, .400, 2.4), (-2.38, .070, .195, .340, 2.2)],
        nose_on_wing=False,
        # sidepod sections: x, list of (y, z) control points (outer half, left side), closed via the body
        pods=[(0.62, [(.30, .63), (.46, .64), (.535, .600), (.545, .470), (.49, .330), (.38, .220), (.30, .200)]),
              (0.40, [(.30, .66), (.50, .665), (.585, .615), (.590, .470), (.52, .300), (.38, .175), (.30, .165)]),
              (0.00, [(.30, .66), (.50, .655), (.575, .600), (.575, .460), (.49, .280), (.36, .160), (.30, .150)]),
              (-0.45, [(.28, .64), (.46, .625), (.525, .565), (.520, .430), (.44, .270), (.33, .160), (.28, .150)]),
              (-0.95, [(.25, .62), (.40, .610), (.455, .560), (.450, .430), (.38, .270), (.29, .170), (.25, .160)]),   # high flat top carried back
              (-1.45, [(.18, .54), (.27, .525), (.300, .480), (.290, .370), (.24, .250), (.19, .180), (.18, .170)])],
        inlet=dict(x=0.62, y0=.36, y1=.535, z0=.44, z1=.625),
        airbox=dict(x0=-0.10, x1=-1.45, top=.965, w=.105, round=True),
        fin=True, fin_h=.11,
        fw=dict(main_z=.075, flaps=[(.135, .17, 11), (.195, .14, 22)], span=.90, x_le=2.92, chord=.30, endplate_fin=True),
        rw=dict(z_main=.80, chord=.27, flap_z=.885, flap_chord=.19, span=.50, x_te=-2.62, pylon='swan'),
        sus_front='pushrod', sus_rear='pushrod',
        colours=dict(paint=(0.012, 0.013, 0.015), paint2=(0.42, 0.44, 0.46), accent=(0.0, 0.52, 0.47),
                     helmet=(0.06, 0.06, 0.07), finish='satin'),
    ),
    'rb22': dict(
        name='Red Bull RB22 (2026)', team='Red Bull Racing', season=2026,
        sources=['Giorgio Piola Design, RB22 analysis (3 May 2026): bathtub gully on sidepods, deep undercut, downwash ramp, "Macarena" rear wing',
                 'RacingNews365 / Autosport RB22 launch analysis (Jan 2026): narrow arrow-shaped nose tip on two small pillars, short straight sidepods',
                 'Red Bull launch (15 Jan 2026, Detroit): gloss finish, brighter blue',
                 'Japan update side comparison photo (Apr 2026): livery layout, sidepod length'],
        look='thick nose with arrow-shaped tip on two pillars to the mainplane, short straight sidepods with a top gully and '
             'steep downwash ramp, taller pointed airbox, no engine-cover fin, twin rear wing pillars',
        body=[(2.74, .035, .150, .215, 2.0), (2.50, .095, .150, .305, 2.6), (2.10, .140, .160, .410, 2.8), (1.70, .175, .150, .495, 3.0),
              (1.25, .215, .115, .555, 3.2), (0.80, .275, .095, .590, 3.3), (0.30, .335, .085, .620, 3.4), (-0.10, .370, .080, .655, 3.4),
              (-0.45, .350, .080, .715, 3.2), (-0.90, .280, .085, .640, 3.0), (-1.30, .200, .100, .540, 2.8), (-1.70, .130, .130, .455, 2.6),
              (-2.05, .090, .170, .390, 2.4), (-2.38, .065, .195, .335, 2.2)],
        nose_on_wing=True,
        pods=[(0.52, [(.30, .565), (.47, .570), (.585, .540), (.600, .425), (.52, .285), (.39, .185), (.30, .175)]),   # wide low letterbox inlet
              (0.30, [(.30, .60), (.48, .585), (.600, .585), (.605, .445), (.53, .290), (.39, .170), (.30, .160)]),   # gully: outer lip higher than mid
              (-0.15, [(.30, .58), (.47, .555), (.590, .565), (.590, .430), (.51, .270), (.37, .160), (.30, .150)]),
              (-0.40, [(.27, .47), (.40, .440), (.490, .440), (.480, .340), (.41, .230), (.31, .160), (.27, .150)]),   # steep downwash ramp
              (-0.70, [(.22, .30), (.30, .275), (.350, .255), (.340, .220), (.30, .185), (.24, .160), (.22, .155)]),
              (-1.00, [(.16, .21), (.20, .200), (.220, .190), (.215, .175), (.20, .165), (.17, .157), (.16, .155)])],
        inlet=dict(x=0.52, y0=.36, y1=.575, z0=.43, z1=.595),
        airbox=dict(x0=-0.08, x1=-1.40, top=.985, w=.12, round=False),
        fin=False, fin_h=0,
        fw=dict(main_z=.085, flaps=[(.145, .16, 13), (.205, .12, 26)], span=.90, x_le=2.88, chord=.28, endplate_fin=False),
        rw=dict(z_main=.79, chord=.26, flap_z=.875, flap_chord=.20, span=.50, x_te=-2.60, pylon='twin'),
        sus_front='pushrod', sus_rear='pushrod',
        colours=dict(paint=(0.016, 0.030, 0.115), paint2=(0.016, 0.030, 0.115), accent=(0.95, 0.70, 0.02),
                     helmet=(0.85, 0.85, 0.86), finish='gloss'),
    ),
}

# ----------------------------------------------------------------------------------------------------------- helpers
MATS = {}


def mat(name, col, rough=0.5, metal=0.0, emit=None, emit_strength=0.0, vcol=False, alpha=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*col, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    if emit:
        b.inputs['Emission Color'].default_value = (*emit, 1)
        b.inputs['Emission Strength'].default_value = emit_strength
    if vcol:
        ca = m.node_tree.nodes.new('ShaderNodeVertexColor')
        m.node_tree.links.new(ca.outputs['Color'], b.inputs['Base Color'])
    if alpha < 1:
        b.inputs['Alpha'].default_value = alpha
    return m


def tex_mat(name, albedo, normal, orm=None, rough=0.4):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes['Principled BSDF']
    t = nt.nodes.new('ShaderNodeTexImage')
    t.image = bpy.data.images.load(str(TEX / albedo))
    nt.links.new(t.outputs['Color'], b.inputs['Base Color'])
    n = nt.nodes.new('ShaderNodeTexImage')
    n.image = bpy.data.images.load(str(TEX / normal))
    n.image.colorspace_settings.name = 'Non-Color'
    nm = nt.nodes.new('ShaderNodeNormalMap')
    nm.inputs['Strength'].default_value = 0.6
    nt.links.new(n.outputs['Color'], nm.inputs['Color'])
    nt.links.new(nm.outputs['Normal'], b.inputs['Normal'])
    b.inputs['Roughness'].default_value = rough
    return m


def make_mats(spec, key):
    c = spec['colours']
    p = f'{key}_'
    MATS.clear()
    MATS['paint'] = mat(p + 'paint', (1, 1, 1), rough=0.32 if c['finish'] == 'gloss' else 0.45, metal=0.35 if c['finish'] == 'gloss' else 0.15, vcol=True)
    MATS['carbon'] = tex_mat(p + 'carbon', 'carbon_albedo.jpg', 'carbon_normal.png', rough=0.38)
    MATS['carbon_matte'] = mat(p + 'carbon_matte', (0.025, 0.026, 0.028), rough=0.7)
    MATS['tyre'] = mat(p + 'tyre', (0.035, 0.035, 0.037), rough=0.86)
    MATS['tyre_band'] = mat(p + 'tyre_band', (0.6, 0.6, 0.6), rough=0.7)
    MATS['rim'] = mat(p + 'rim', (0.03, 0.03, 0.033), rough=0.35, metal=0.7)
    MATS['metal'] = mat(p + 'titanium', (0.45, 0.46, 0.48), rough=0.3, metal=1.0)
    MATS['mirror'] = mat(p + 'mirror_glass', (0.9, 0.92, 0.95), rough=0.02, metal=1.0)
    MATS['helmet'] = mat(p + 'helmet', c['helmet'], rough=0.25, metal=0.2)
    MATS['visor'] = mat(p + 'visor', (0.01, 0.01, 0.012), rough=0.05, metal=0.6)
    MATS['red_light'] = mat(p + 'rain_light', (0.4, 0.0, 0.0), emit=(1.0, 0.05, 0.03), emit_strength=8)
    MATS['display'] = mat(p + 'display', (0.0, 0.0, 0.0), emit=(0.3, 0.8, 1.0), emit_strength=2)
    MATS['dark'] = mat(p + 'dark_inlet', (0.004, 0.004, 0.005), rough=0.9)
    MATS['brake'] = mat(p + 'brake_disc', (0.12, 0.1, 0.09), rough=0.6, metal=0.3)
    MATS['pad'] = mat(p + 'cockpit_pad', (0.02, 0.02, 0.022), rough=0.9)


def obj_from(name, verts, faces, m, parent=None, smooth=True, cols=None, subsurf=0):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(map(float, v)) for v in verts], [], faces)
    me.validate()
    if cols is not None:
        ca = me.color_attributes.new('Col', 'BYTE_COLOR', 'POINT')
        flat = []
        for c in cols:
            flat.extend((*c, 1.0))
        ca.data.foreach_set('color', flat)
    me.update()
    if smooth:
        me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    ob.data.materials.append(m)
    bpy.context.scene.collection.objects.link(ob)
    if parent:
        ob.parent = parent
    if subsurf:
        md = ob.modifiers.new('sub', 'SUBSURF')
        md.levels = md.render_levels = subsurf
    fix_normals(ob)
    return ob


def fix_normals(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ob.data)
    bm.free()


def loft(rings, cap=True):
    """Rings: list of equal-length closed point lists -> verts, quad faces (+ n-gon caps)."""
    k = len(rings[0])
    verts = [p for r in rings for p in r]
    faces = []
    for a in range(len(rings) - 1):
        for j in range(k):
            i0, i1 = a * k + j, a * k + (j + 1) % k
            faces.append((i0, i1, i1 + k, i0 + k))
    if cap:
        faces.append(tuple(range(k))[::-1])
        faces.append(tuple(range((len(rings) - 1) * k, len(rings) * k)))
    return verts, faces


def superellipse(x, w, zb, zt, n, k):
    zc, h = (zb + zt) / 2, (zt - zb) / 2
    out = []
    for i in range(k):
        t = 2 * math.pi * i / k
        c, s = math.cos(t), math.sin(t)
        y = w * math.copysign(abs(c) ** (2 / n), c)
        z = zc + h * math.copysign(abs(s) ** (2 / (n if s > 0 else n * 0.8)), s)
        out.append((x, y, z))
    return out


def catmull_closed(pts, per=6):
    pts = [np.array(p, float) for p in pts]
    n = len(pts)
    out = []
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        for k in range(per):
            u = k / per
            u2, u3 = u * u, u * u * u
            out.append(0.5 * (2 * p1 + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u2 + (-p0 + 3 * p1 - 3 * p2 + p3) * u3))
    return out


def interp_sections(secs, xs):
    """Linear interpolation of section parameter tuples (first item = x, descending) at xs."""
    arr = np.array(secs, float)
    out = []
    for x in xs:
        row = [np.interp(-x, -arr[:, 0], arr[:, j]) for j in range(1, arr.shape[1])]
        out.append((x, *row))
    return out


def tube(path, r, k=10, ry=None, closed=False):
    """Tube along a polyline; elliptic when ry is given (r horizontal-ish, ry vertical-ish)."""
    path = [np.array(p, float) for p in path]
    rings = []
    for i, p in enumerate(path):
        a, b = path[max(0, i - 1)], path[min(len(path) - 1, i + 1)]
        if closed:
            a, b = path[i - 1], path[(i + 1) % len(path)]
        t = b - a
        t /= max(1e-9, np.linalg.norm(t))
        up = np.array([0, 0, 1.0]) if abs(t[2]) < 0.9 else np.array([1.0, 0, 0])
        u = np.cross(t, up)
        u /= np.linalg.norm(u)
        v = np.cross(u, t)
        rings.append([p + u * r * math.cos(2 * math.pi * j / k) + v * (ry or r) * math.sin(2 * math.pi * j / k) for j in range(k)])
    if closed:
        verts = [q for rr in rings for q in rr]
        faces = []
        n = len(rings)
        for a in range(n):
            for j in range(k):
                i0, i1 = a * k + j, a * k + (j + 1) % k
                b0, b1 = ((a + 1) % n) * k + j, ((a + 1) % n) * k + (j + 1) % k
                faces.append((i0, i1, b1, b0))
        return verts, faces
    return loft(rings, cap=True)


def arm(a, b, w=0.022, h=0.009):
    """Aerofoil-section suspension member (flattened tube)."""
    return tube([a, b], w, k=8, ry=h)


def airfoil(c, t, camber, n=14):
    """Closed airfoil outline in the chord frame: (x back from LE (negative), z), inverted camber (lift down)."""
    pts_u, pts_l = [], []
    for i in range(n + 1):
        s = (1 - math.cos(math.pi * i / n)) / 2
        yt = 5 * t * (0.2969 * math.sqrt(s) - 0.126 * s - 0.3516 * s * s + 0.2843 * s ** 3 - 0.1036 * s ** 4)
        yc = -4 * camber * s * (1 - s)
        pts_u.append((-s * c, (yc + yt) * c))
        pts_l.append((-s * c, (yc - yt) * c))
    return pts_u + pts_l[::-1][1:-1]


def wing(stations, t=0.10, camber=0.06, n=12):
    """Spanwise loft of airfoils. stations: (y, x_le, z_le, chord, angle_deg TE-up)."""
    rings = []
    for y, xle, zle, c, ang in stations:
        a = math.radians(ang)
        ring = []
        for px, pz in airfoil(c, t, camber, n):
            rx = px * math.cos(a) + pz * math.sin(a) * 0
            rz = pz - px * math.sin(a) * -1
            rz = pz + (-px) * math.tan(a) * 0 + (-px) * math.sin(a)
            ring.append((xle + px * math.cos(a), y, zle + rz))
        rings.append(ring)
    return loft(rings, cap=True)


def plate(outline_xz, y, thick):
    """Thin plate (endplate) from an (x, z) outline at lateral y."""
    k = len(outline_xz)
    verts = [(x, y - thick / 2, z) for x, z in outline_xz] + [(x, y + thick / 2, z) for x, z in outline_xz]
    faces = [tuple(range(k))[::-1], tuple(range(k, 2 * k))]
    for i in range(k):
        j = (i + 1) % k
        faces.append((i, j, j + k, i + k))
    return verts, faces


def mirror(verts, faces):
    v2 = [(x, -y, z) for x, y, z in verts]
    f2 = [tuple(reversed(f)) for f in faces]
    return v2, f2


def both(name, verts, faces, m, parent, **kw):
    a = obj_from(name + '_L', verts, faces, m, parent, **kw)
    v2, f2 = mirror(verts, faces)
    b = obj_from(name + '_R', v2, f2, m, parent, **kw)
    return a, b


def revolve(profile, segs=40):
    """Lathe around the Y axis (wheel axle = car's lateral axis). profile: (radius, y) open polyline."""
    verts, faces = [], []
    k = len(profile)
    for s in range(segs):
        a = 2 * math.pi * s / segs
        for r, y in profile:
            verts.append((r * math.cos(a), y, r * math.sin(a)))
    for s in range(segs):
        for j in range(k - 1):
            i0 = s * k + j
            i1 = ((s + 1) % segs) * k + j
            faces.append((i0, i1, i1 + 1, i0 + 1))
    return verts, faces


def empty(name, loc, parent=None):
    e = bpy.data.objects.new(name, None)
    e.location = loc
    e.empty_display_size = 0.15
    bpy.context.scene.collection.objects.link(e)
    if parent:
        e.parent = parent
    return e


# ----------------------------------------------------------------------------------------------------------- livery
def livery_colour(key, spec, x, y, z, part):
    """Vertex colour = livery layout (no logos, no text): plain colour fields only."""
    c = spec['colours']
    if key == 'w17':
        # black car, silver upper engine cover / airbox flanks, Petronas-teal lines on nose sides and sidepod shoulder
        if part == 'body' and z > 0.56 and -1.6 < x < -0.15:
            return c['paint2']
        if part == 'body' and 1.2 < x < 2.6 and abs(y) > 0.06 and abs(z - (0.33 + (2.6 - x) * 0.09)) < 0.018:
            return c['accent']
        if part == 'pod' and abs(z - 0.60) < 0.015 and x > -0.6:
            return c['accent']
        if part == 'airbox':
            return c['paint2'] if z < 0.9 else c['paint']
        return c['paint']
    # RB22: gloss metallic navy, yellow airbox front/top and nose tip
    if part == 'airbox' and x > -0.75:
        return c['accent']
    if part == 'body' and x > 2.45:
        return c['accent']
    if part == 'body' and 0.0 > x > -0.5 and z > 0.66:
        return c['accent']
    return c['paint']


def coloured(key, spec, verts, part):
    return [livery_colour(key, spec, *v, part) for v in verts]


# ----------------------------------------------------------------------------------------------------------- parts
def build_body(key, spec, root, lod):
    k = 48 if lod == 0 else 16
    xs = np.r_[np.linspace(spec['body'][0][0], spec['body'][-1][0], 42 if lod == 0 else 14)]
    secs = interp_sections(spec['body'], xs)
    rings = [superellipse(x, w, zb, zt, n, k) for x, w, zb, zt, n in secs]
    # cockpit opening: lower the top centre between 0.55 and -0.12 (filled later by the rim, driver, pads)
    for r, (x, w, zb, zt, n) in zip(rings, secs):
        if -0.12 < x < 0.58:
            f = min(1, (0.58 - x) / 0.08, (x + 0.12) / 0.05)
            for i, (px, py, pz) in enumerate(r):
                if pz > zt - 0.08 and abs(py) < 0.24:
                    r[i] = (px, py, pz - 0.10 * f * (1 - (abs(py) / 0.24) ** 2))
    v, f = loft(rings)
    return obj_from(f'body_LOD{lod}', v, f, MATS['paint'], root, cols=coloured(key, spec, v, 'body'), subsurf=1 if lod == 0 else 0)


def build_pods(key, spec, root, lod):
    per = 6 if lod == 0 else 2
    rings = []
    secs = spec['pods']
    for x, pts in secs:
        closed = pts + [(pts[-1][0] - 0.02, pts[-1][1]), (pts[0][0] - 0.02, pts[0][1])]
        ring = catmull_closed([(y, z) for y, z in closed], per)
        rings.append([(x, float(p[0]), float(p[1])) for p in ring])
    # tail: close to a point on the floor/body side
    xt = secs[-1][0] - 0.25
    rings.append([(xt, 0.14 + (p[1] - 0.14) * 0.15, 0.17 + (p[2] - 0.17) * 0.12) for p in rings[-1]])
    v, f = loft(rings)
    out = both(f'sidepod_LOD{lod}', v, f, MATS['paint'], root, cols=coloured(key, spec, v, 'pod'), subsurf=1 if lod == 0 else 0)
    # inlet mouth (dark, slightly recessed), pod-face outline
    i = spec['inlet']
    mouth = [(i['x'] + 0.012, i['y0'], i['z0']), (i['x'] + 0.012, i['y1'], i['z0'] + 0.02), (i['x'] + 0.012, i['y1'] - 0.01, i['z1'] - 0.01), (i['x'] + 0.012, i['y0'], i['z1'])]
    back = [(p[0] - 0.12, p[1], p[2]) for p in mouth]
    v, f = loft([mouth, back])
    both(f'inlet_LOD{lod}', v, f, MATS['dark'], root, smooth=False)
    return out


def build_airbox(key, spec, root, lod):
    a = spec['airbox']
    k = 24 if lod == 0 else 10
    xs = np.linspace(a['x0'], a['x1'], 16 if lod == 0 else 6)
    rings = []
    for x in xs:
        u = (a['x0'] - x) / (a['x0'] - a['x1'])
        top = 0.66 + (a['top'] - 0.66) * min(1, u / 0.22) - max(0, u - 0.22) / 0.78 * (a['top'] - 0.60)
        w = a['w'] * (0.75 + 0.6 * min(1, u / 0.3)) * (1 - 0.55 * max(0, u - 0.5))
        rings.append(superellipse(x, w, 0.58, top, 2.2 if a['round'] else 1.6, k))
    v, f = loft(rings)
    obj_from(f'airbox_LOD{lod}', v, f, MATS['paint'], root, cols=coloured(key, spec, v, 'airbox'), subsurf=1 if lod == 0 else 0)
    # intake mouth
    x0 = a['x0'] - 0.03
    m = [(x0, -a['w'] * 0.55, a['top'] - 0.15), (x0, a['w'] * 0.55, a['top'] - 0.15), (x0, a['w'] * 0.45, a['top'] - 0.03), (x0, -a['w'] * 0.45, a['top'] - 0.03)]
    if not a['round']:
        m = [(x0, -a['w'] * 0.6, a['top'] - 0.17), (x0, a['w'] * 0.6, a['top'] - 0.17), (x0, 0.0, a['top'] - 0.02), (x0, 0.0, a['top'] - 0.02)]
        m = m[:3]
    v, f = loft([m, [(p[0] - 0.1, p[1] * 0.8, p[2]) for p in m]])
    obj_from(f'airbox_mouth_LOD{lod}', v, f, MATS['dark'], root, smooth=False)
    # roll hoop / T-cam housing on top
    v, f = loft([superellipse(x, 0.035, a['top'] - 0.005, a['top'] + 0.045, 2.0, 8) for x in (a['x0'] - 0.20, a['x0'] - 0.42)])
    obj_from(f'tcam_LOD{lod}', v, f, MATS['carbon_matte'], root)
    if spec['fin']:
        v, f = plate([(-1.05, 0.62), (-1.95, 0.42), (-1.95, 0.42 + spec['fin_h']), (-1.15, 0.70)], 0.0, 0.01)
        obj_from(f'fin_LOD{lod}', v, f, MATS['paint'], root, smooth=False, cols=[spec['colours']['paint']] * len(v))


def build_floor(key, spec, root, lod):
    # plan outline (left half), x forward
    plan = [(1.25, 0.10), (1.05, 0.40), (0.70, 0.62), (0.20, 0.70), (-0.60, 0.70), (-1.25, 0.66), (-1.62, 0.56), (-1.62, 0.20)]
    top = [(x, y, 0.065) for x, y in plan]
    bot = [(x, y, 0.035) for x, y in plan]
    pts = plan + [(x, -y) for x, y in reversed(plan)]
    v = [(x, y, 0.065) for x, y in pts] + [(x, y, 0.035) for x, y in pts]
    n = len(pts)
    f = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))]
    for i in range(n):
        j = (i + 1) % n
        f.append((i, i + n, j + n, j))
    obj_from(f'floor_LOD{lod}', v, f, MATS['carbon'], root, smooth=False)
    # floor edge wing (kick-up) and fences under the front of the floor
    edge = [(x, y + 0.005, 0.065) for x, y in plan[2:6]]
    v, f = tube([(x, y, 0.09) for x, y, _ in edge], 0.03, k=6, ry=0.008)
    both(f'floor_edge_LOD{lod}', v, f, MATS['carbon'], root)
    for yy in (0.18, 0.28, 0.38):
        v, f = plate([(1.0, 0.035), (0.35, 0.035), (0.35, 0.0), (1.0, -0.005)], yy, 0.006)
        both(f'floor_fence{int(yy * 100)}_LOD{lod}', v, f, MATS['carbon'], root, smooth=False)
    # diffuser: ramp from the floor to the crash structure
    rings = []
    for x in np.linspace(-1.62, -2.40, 8):
        u = (-1.62 - x) / 0.78
        zt = 0.065 + 0.24 * u ** 1.3
        w = 0.50 - 0.06 * u
        rings.append([(x, -w, 0.035 + 0.22 * u ** 1.3), (x, w, 0.035 + 0.22 * u ** 1.3), (x, w, zt + 0.015), (x, -w, zt + 0.015)])
    v, f = loft(rings)
    obj_from(f'diffuser_LOD{lod}', v, f, MATS['carbon'], root, smooth=False)
    if key == 'w17':   # sidewalls (RB22 runs without them: Piola, May 2026)
        v, f = plate([(-1.62, 0.04), (-2.40, 0.28), (-2.40, 0.33), (-1.62, 0.09)], 0.505, 0.008)
        both(f'diffuser_wall_LOD{lod}', v, f, MATS['carbon'], root, smooth=False)
    # bargeboards (back in 2026)
    for yy, h in ((0.50, 0.30), (0.56, 0.24)):
        v, f = plate([(0.95, 0.07), (0.62, 0.07), (0.62, 0.07 + h), (0.90, 0.07 + h * 0.8)], yy, 0.008)
        both(f'bargeboard{int(yy * 100)}_LOD{lod}', v, f, MATS['carbon'], root, smooth=False)


def build_front_wing(key, spec, root, lod):
    fw = spec['fw']
    span = fw['span']
    sts = []
    n = 13 if lod == 0 else 5
    for y in np.linspace(-span, span, n):
        u = abs(y) / span
        central = abs(y) < 0.25
        z = fw['main_z'] + (0.0 if central else 0.01 * u)
        c = fw['chord'] * (1.0 - 0.25 * u) if not central else fw['chord'] * 0.9
        sts.append((y, fw['x_le'] - 0.06 * u * u, z, c, 4 + 4 * u))
    v, f = wing(sts, t=0.09, camber=0.05)
    obj_from(f'fw_main_LOD{lod}', v, f, MATS['carbon'], root)
    for k, (z, c, ang) in enumerate(fw['flaps']):
        sts = []
        for y in np.linspace(-span, span, n):
            u = abs(y) / span
            if abs(y) < 0.24:
                yz = z - 0.03     # neutral centre section stays low
            else:
                yz = z + 0.03 * u
            sts.append((y, fw['x_le'] - fw['chord'] * (0.55 + 0.18 * k) - 0.05 * u * u, yz, c, ang + 6 * u))
        v, f = wing(sts, t=0.08, camber=0.06)
        cols = None
        m = MATS['carbon']
        if k == len(fw['flaps']) - 1:
            m = MATS['paint']
            cols = [spec['colours']['accent'] if key == 'w17' else spec['colours']['paint']] * len(v)
        obj_from(f'fw_flap{k + 1}_LOD{lod}', v, f, m, root, cols=cols)
    # endplates (+ outer foot fin for the W17)
    out = [(fw['x_le'] + 0.02, 0.05), (fw['x_le'] - 0.52, 0.05), (fw['x_le'] - 0.55, 0.30), (fw['x_le'] - 0.35, 0.33), (fw['x_le'] - 0.05, 0.12)]
    v, f = plate(out, span + 0.005, 0.012)
    both(f'fw_endplate_LOD{lod}', v, f, MATS['paint'], root, smooth=False, cols=[spec['colours']['paint']] * len(v))
    if fw['endplate_fin']:
        v, f = plate([(fw['x_le'] - 0.05, 0.05), (fw['x_le'] - 0.40, 0.05), (fw['x_le'] - 0.40, 0.11), (fw['x_le'] - 0.12, 0.09)], span + 0.04, 0.008)
        both(f'fw_footfin_LOD{lod}', v, f, MATS['carbon'], root, smooth=False)
    # nose pillars: W17 pylons onto the 2nd flap; RB22 two small pillars onto the mainplane under the arrow tip
    tip = spec['body'][0]
    if spec['nose_on_wing']:
        for yy in (-0.05, 0.05):
            v, f = plate([(tip[0] - 0.02, tip[2] + 0.01), (tip[0] - 0.22, tip[2] + 0.02), (tip[0] - 0.22, fw['main_z'] + 0.02), (tip[0] - 0.04, fw['main_z'] + 0.02)], yy, 0.01)
            obj_from(f'nose_pillar{int(yy * 100)}_LOD{lod}', v, f, MATS['carbon'], root, smooth=False)
    else:
        z2 = fw['flaps'][0][0]
        for yy in (-0.07, 0.07):
            v, f = plate([(tip[0] - 0.30, tip[2] + 0.02), (tip[0] - 0.52, tip[2] + 0.04), (tip[0] - 0.62, z2 + 0.03), (tip[0] - 0.36, z2 + 0.02)], yy, 0.012)
            obj_from(f'nose_pylon{int(yy * 100)}_LOD{lod}', v, f, MATS['carbon'], root, smooth=False)


def build_rear_wing(key, spec, root, lod):
    rw = spec['rw']
    n = 9 if lod == 0 else 3
    span = rw['span']
    sts = [(y, rw['x_te'] + rw['chord'] + 0.06, rw['z_main'] - 0.015 * (1 - abs(y) / span), rw['chord'], 8) for y in np.linspace(-span, span, n)]
    v, f = wing(sts, t=0.11, camber=0.07)
    obj_from(f'rw_main_LOD{lod}', v, f, MATS['carbon'], root)
    flap_ang = 32 if key == 'w17' else 26
    sts = [(y, rw['x_te'] + rw['flap_chord'] + 0.01, rw['flap_z'], rw['flap_chord'], flap_ang) for y in np.linspace(-span, span, n)]
    v, f = wing(sts, t=0.09, camber=0.06)
    obj_from(f'rw_flap_LOD{lod}', v, f, MATS['paint'], root, cols=[spec['colours']['paint']] * len(v))
    x0, x1 = rw['x_te'] - 0.02, rw['x_te'] + 0.58
    ep = [(x1, 0.50), (x0 + 0.08, 0.50), (x0, 0.62), (x0, 0.93), (x0 + 0.10, 0.975), (x1 - 0.12, 0.975), (x1, 0.90)]
    v, f = plate(ep, span + 0.008, 0.014)
    both(f'rw_endplate_LOD{lod}', v, f, MATS['paint'], root, smooth=False, cols=[spec['colours']['paint']] * len(v))
    # rain lights on the endplate trailing edge (2026) and on the crash structure
    v, f = plate([(x0 + 0.005, 0.70), (x0 - 0.005, 0.70), (x0 - 0.005, 0.90), (x0 + 0.005, 0.90)], span + 0.016, 0.006)
    both(f'rw_light_LOD{lod}', v, f, MATS['red_light'], root, smooth=False)
    v, f = loft([superellipse(x, 0.04, 0.24, 0.30, 2.5, 10) for x in (-2.36, -2.41)])
    obj_from(f'rain_light_LOD{lod}', v, f, MATS['red_light'], root)
    # support: W17 single swan neck over the mainplane; RB22 twin pillars under it
    if rw['pylon'] == 'swan':
        v, f = tube([(-2.15, 0.0, 0.36), (-2.25, 0.0, 0.62), (-2.32, 0.0, rw['z_main'] + 0.06), (-2.40, 0.0, rw['z_main'] + 0.035)], 0.035, k=8, ry=0.012)
        obj_from(f'rw_swanneck_LOD{lod}', v, f, MATS['carbon'], root)
    else:
        for yy in (-0.07, 0.07):
            v, f = plate([(-2.12, 0.36), (-2.30, 0.36), (-2.42, rw['z_main'] - 0.01), (-2.28, rw['z_main'] - 0.01)], yy, 0.012)
            obj_from(f'rw_pillar{int(yy * 100)}_LOD{lod}', v, f, MATS['carbon'], root, smooth=False)


def build_cockpit(key, spec, root, lod):
    # halo: central pillar + hoop (titanium, painted in body colour)
    hoop = [(0.56, 0.0, 0.795), (0.50, 0.17, 0.79), (0.30, 0.29, 0.775), (0.05, 0.325, 0.735), (-0.10, 0.335, 0.66)]
    path = [(p[0], -p[1], p[2]) for p in reversed(hoop)] + hoop[1:]
    v, f = tube(path, 0.026 if lod == 0 else 0.03, k=12 if lod == 0 else 6)
    obj_from(f'halo_LOD{lod}', v, f, MATS['paint'], root, cols=[spec['colours']['paint']] * len(v))
    v, f = tube([(0.86, 0.0, 0.56), (0.74, 0.0, 0.70), (0.58, 0.0, 0.79)], 0.03, k=10, ry=0.022)
    obj_from(f'halo_pillar_LOD{lod}', v, f, MATS['paint'], root, cols=[spec['colours']['paint']] * len(v))
    if lod:
        return
    # cockpit rim (padded) + headrest
    rim = [(0.56 - 0.70 * (1 - math.cos(a)) / 2, 0.27 * math.sin(a), 0.585) for a in np.linspace(0, 2 * math.pi, 28, endpoint=False)]
    v, f = tube(rim, 0.03, k=8, closed=True)
    obj_from('cockpit_rim', v, f, MATS['pad'], root)
    for s in (1, -1):
        v, f = loft([superellipse(x, 0.07, 0.56, 0.69, 2.4, 10) for x in (-0.02, -0.16)])
        v = [(x, y + s * 0.19, z) for x, y, z in v]
        obj_from(f'headrest_{"L" if s > 0 else "R"}', v, f, MATS['pad'], root)
    # steering wheel with grips and display
    v, f = loft([superellipse(x, 0.14, 0.50, 0.62, 3.5, 16) for x in (0.40, 0.37)])
    obj_from('steering_wheel', v, f, MATS['carbon_matte'], root)
    v, f = loft([[(0.405, -0.05, 0.53), (0.405, 0.05, 0.53), (0.405, 0.05, 0.58), (0.405, -0.05, 0.58)], [(0.401, -0.05, 0.53), (0.401, 0.05, 0.53), (0.401, 0.05, 0.58), (0.401, -0.05, 0.58)]])
    obj_from('steering_display', v, f, MATS['display'], root, smooth=False)
    for s in (1, -1):
        v, f = tube([(0.39, s * 0.14, 0.49), (0.39, s * 0.16, 0.56), (0.39, s * 0.14, 0.62)], 0.022, k=8)
        obj_from(f'steering_grip_{s}', v, f, MATS['pad'], root)
    # mirrors on stalks from the chassis side
    for s in (1, -1):
        v, f = tube([(0.62, s * 0.30, 0.58), (0.60, s * 0.40, 0.64), (0.58, s * 0.46, 0.66)], 0.012, k=6)
        obj_from(f'mirror_stalk_{"L" if s > 0 else "R"}', v, f, MATS['carbon'], root)
        v, f = loft([superellipse(x, 0.075, 0.635, 0.695, 3.0, 12) for x in (0.60, 0.52)])
        v = [(x, y + s * 0.49, z) for x, y, z in v]
        obj_from(f'mirror_{"L" if s > 0 else "R"}', v, f, MATS['paint'], root, cols=[spec['colours']['paint']] * len(v))
        v, f = loft([superellipse(x, 0.066, 0.640, 0.690, 3.0, 12) for x in (0.517, 0.515)])
        v = [(x, y + s * 0.49, z) for x, y, z in v]
        obj_from(f'mirror_glass_{"L" if s > 0 else "R"}', v, f, MATS['mirror'], root)


def build_driver(spec, root):
    v, f = loft([superellipse(x, 0.115 * math.sqrt(max(0.02, 1 - ((x - 0.02) / 0.15) ** 2)), 0.62, 0.62 + 0.27 * math.sqrt(max(0.02, 1 - ((x - 0.02) / 0.15) ** 2)), 2.0, 20)
                 for x in np.linspace(0.16, -0.12, 12)])
    h = obj_from('driver_helmet', v, f, MATS['helmet'], root)
    v, f = loft([superellipse(x, 0.105, 0.725, 0.785, 2.2, 14) for x in (0.165, 0.150)])
    obj_from('driver_visor', v, f, MATS['visor'], h)
    return h


def build_suspension(spec, root, lod, wheel_pos):
    k = 8 if lod == 0 else 4
    out = []
    (xf, yf, rf), (xr, yr, rr) = wheel_pos
    for s in (1, -1):
        # front: upper / lower wishbones (two legs each), pushrod, track rod, upright drum
        up_o, lo_o = (xf, s * (yf - 0.10), 0.44), (xf + 0.01, s * (yf - 0.11), 0.17)
        legs = [((xf + 0.22, s * 0.17, 0.43), up_o), ((xf - 0.22, s * 0.17, 0.42), up_o),
                ((xf + 0.20, s * 0.15, 0.20), lo_o), ((xf - 0.25, s * 0.15, 0.19), lo_o),
                ((xf - 0.08, s * 0.16, 0.52), (xf - 0.02, s * (yf - 0.15), 0.19)),      # pushrod
                ((xf + 0.10, s * 0.16, 0.30), (xf + 0.10, s * (yf - 0.10), 0.30))]      # track rod
        for i, (a, b) in enumerate(legs):
            v, f = arm(a, b, 0.024 if i < 4 else 0.016, 0.009 if i < 4 else 0.016)
            out.append(obj_from(f'sus_front_{i}_{"L" if s > 0 else "R"}_LOD{lod}', v, f, MATS['carbon'], root))
        # rear: same layout, wider legs
        up_o, lo_o = (xr, s * (yr - 0.12), 0.46), (xr, s * (yr - 0.13), 0.17)
        legs = [((xr + 0.25, s * 0.13, 0.42), up_o), ((xr - 0.15, s * 0.10, 0.44), up_o),
                ((xr + 0.30, s * 0.15, 0.19), lo_o), ((xr - 0.12, s * 0.10, 0.20), lo_o),
                ((xr + 0.06, s * 0.13, 0.50), (xr + 0.02, s * (yr - 0.16), 0.19)),
                ((xr - 0.10, s * 0.11, 0.30), (xr - 0.10, s * (yr - 0.12), 0.32))]
        for i, (a, b) in enumerate(legs):
            v, f = arm(a, b, 0.026 if i < 4 else 0.016, 0.010 if i < 4 else 0.016)
            out.append(obj_from(f'sus_rear_{i}_{"L" if s > 0 else "R"}_LOD{lod}', v, f, MATS['carbon'], root))
    return out


def build_wheel(name, d, w, front, parent):
    """Tyre (lathe profile with rounded shoulders), 18-inch rim with cover, brake drum. Pivot at the hub."""
    r = d / 2
    rr = COMMON['rim_d'] / 2
    hw = w / 2
    prof = [(rr + 0.01, -hw + 0.02), (rr + 0.03, -hw), (r - 0.05, -hw - 0.004), (r - 0.012, -hw + 0.015), (r, -hw + 0.05),
            (r, hw - 0.05), (r - 0.012, hw - 0.015), (r - 0.05, hw + 0.004), (rr + 0.03, hw), (rr + 0.01, hw - 0.02)]
    v, f = revolve(prof, 48)
    t = obj_from(name + '_tyre', v, f, MATS['tyre'], parent)
    for s in (1, -1):    # compound band on each sidewall (colour set by the browser from the timing data)
        band = [(r - 0.075, s * (hw + 0.002)), (r - 0.06, s * (hw + 0.003))]
        v, f = revolve(band, 48)
        obj_from(name + f'_band{"L" if s > 0 else "R"}', v, f, MATS['tyre_band'], parent)
    rim = [(0.0, -hw + 0.06), (rr - 0.02, -hw + 0.05), (rr, -hw + 0.03), (rr, hw - 0.03), (rr - 0.02, hw - 0.05), (0.0, hw - 0.06)]
    v, f = revolve(rim, 32)
    obj_from(name + '_rim', v, f, MATS['rim'], parent)
    v, f = revolve([(0.0, -0.08), (0.14, -0.08), (0.14, 0.08), (0.0, 0.08)], 20)
    obj_from(name + '_drum', v, f, MATS['carbon'], parent)
    return t


def build_car(key):
    spec = SPECS[key]
    make_mats(spec, key)
    root = empty(f'{key}_root', (0, 0, 0))
    root['season'] = spec['season']
    root['team'] = spec['team']
    root['model'] = spec['name']
    root['sources'] = '; '.join(spec['sources'])
    wb, W = COMMON['wheelbase'], COMMON['width']
    fd, fw_ = COMMON['f_tyre']
    rd, rw_ = COMMON['r_tyre']
    yf = W / 2 - fw_ / 2
    yr = W / 2 - rw_ / 2
    xf, xr = wb / 2, -wb / 2
    for lod in (0, 1):
        grp = empty(f'LOD{lod}', (0, 0, 0), root)
        build_body(key, spec, grp, lod)
        build_pods(key, spec, grp, lod)
        build_airbox(key, spec, grp, lod)
        build_floor(key, spec, grp, lod)
        build_front_wing(key, spec, grp, lod)
        build_rear_wing(key, spec, grp, lod)
        build_cockpit(key, spec, grp, lod)
        build_suspension(spec, grp, lod, ((xf, yf, fd / 2), (xr, yr, rd / 2)))
    build_driver(spec, root)
    for nm, x, y, d, w, front in (('FL', xf, yf, fd, fw_, True), ('FR', xf, -yf, fd, fw_, True), ('RL', xr, yr, rd, rw_, False), ('RR', xr, -yr, rd, rw_, False)):
        steer = empty(f'steer_{nm}', (x, y, d / 2), root)
        wheel = empty(f'wheel_{nm}', (0, 0, 0), steer)
        build_wheel(f'wheel_{nm}', d, w, front, wheel)
    # camera mounts: TV pod on the T-cam above the airbox, driver's eye inside the halo
    a = spec['airbox']
    empty('cam_pod', (a['x0'] - 0.42, 0.0, a['top'] + 0.19), root)   # T-cam lens height ~1.16-1.18 m
    empty('cam_cockpit', (0.10, 0.0, 0.80), root)   # eye inside the helmet visor, just under the halo hoop
    empty('mount_label', (0.0, 0.0, 1.35), root)
    return root


def export(key):
    path = OUT_GLB / f'{key}.glb'
    OUT_GLB.mkdir(parents=True, exist_ok=True)
    kw = dict(filepath=str(path), export_format='GLB', export_yup=True, export_apply=True, export_extras=True,
              export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=6,
              export_draco_position_quantization=14, export_image_format='WEBP', export_image_quality=85)
    try:
        bpy.ops.export_scene.gltf(export_vertex_color='ACTIVE', **kw)
    except TypeError:
        bpy.ops.export_scene.gltf(**kw)
    return path


def stats():
    tri = {0: 0, 1: 0, 'shared': 0}
    deps = bpy.context.evaluated_depsgraph_get()
    for o in bpy.context.scene.objects:
        if o.type != 'MESH':
            continue
        me = o.evaluated_get(deps).to_mesh()
        n = sum(len(p.vertices) - 2 for p in me.polygons)
        o.evaluated_get(deps).to_mesh_clear()
        lod = 0 if o.name.endswith('LOD0') or (o.parent and o.parent.name.startswith('LOD0')) else 1 if o.name.endswith('LOD1') or (o.parent and o.parent.name.startswith('LOD1')) else 'shared'
        tri[lod] += n
    return tri


def clay_render(key):
    """Clay views of one car (no team colours): front three-quarter (perspective), side and rear (orthographic)."""
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'
    sc.display.shading.light = 'STUDIO'
    sc.display.shading.color_type = 'SINGLE'
    sc.display.shading.single_color = (0.62, 0.62, 0.62)
    sc.display.shading.show_cavity = True
    sc.display.shading.show_shadows = True
    sc.render.film_transparent = False
    sc.render.resolution_x, sc.render.resolution_y = 1000, 520
    for o in bpy.data.objects:
        if o.name.startswith('LOD1'):
            for c in o.children_recursive:
                c.hide_render = True
    cam = bpy.data.objects.new('clay_cam', bpy.data.cameras.new('clay_cam'))
    sc.collection.objects.link(cam)
    sc.camera = cam
    views = dict(front34=('PERSP', (6.2, -4.6, 2.0), (0.2, 0, 0.45), 6.0), side=('ORTHO', (0, -14, 0.5), (0, 0, 0.5), 6.0), rear=('ORTHO', (-14, 0, 0.55), (0, 0, 0.55), 2.7))
    for name, (kind, loc, tgt, scale) in views.items():
        cam.data.type = kind
        cam.data.lens = 40
        cam.data.ortho_scale = scale
        cam.location = loc
        d = Vector(tgt) - Vector(loc)
        cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = str(ROOT / f'outputs/qatar/cars_clay_{key}_{name}.png')
        bpy.ops.render.render(write_still=True)


def main():
    OUT_BLEND.mkdir(parents=True, exist_ok=True)
    report = {}
    roots = {}
    for key in SPECS:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        root = build_car(key)
        report[key] = stats()
        bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND / f'{key}.blend'), compress=True)
        p = export(key)
        print(f'{key}: GLB {p.stat().st_size / 1e3:.0f} KB, triangles {report[key]}')
    if CLAY:
        for key in SPECS:
            bpy.ops.wm.read_factory_settings(use_empty=True)
            build_car(key)
            clay_render(key)

if __name__ == "__main__":
    main()
