"""Relight the Library Loop: amber library, ivory keys, a cyan gloria, three laser families.

Run inside Blender with the scene that already holds the five selected sculptures:

    blender -b library_loop_final.blend --python-exit-code 2 \
        -P scripts/sanctum_lighting.py -- --out library_loop_sanctum.blend

Nothing is deleted and the source .blend is never saved over. The first version's rig (foot-light
strobes, blue washes, ceiling tubes, flat laser planes) is hidden; sculptures, camera, set geometry,
flying-book animation and the music are kept. No Tripo calls.

The show itself (palette, cue stack, effects, master checks) lives in sanctum_show.py / cue.py and
is testable without Blender. This file is the patch: fixtures as a data table, laser geometry and
materials, set dressing, and the build-time checks:
  * every baked channel closes at frame 301
  * no laser ray touches a sculpture or column on any frame
  * no page or flying book sits in front of a sculpture
  * the gloria emitter is hidden from the camera; no fixture sits inside a sculpture
A failed check raises, so nothing half-valid is saved.

Options (after --)
    --out PATH          output .blend (must differ from the source)
    --title bottom|top  title placement (default bottom: small, on the floor, with a soft shade)
    --exposure EV       view exposure (default 0.0)
    --haze DENSITY      volume density (default 0.007)
    --gain X            multiply every light (default 1.0) for quick exposure tests
"""
import argparse
import json
import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from bpy_extras.object_utils import world_to_camera_view

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cue                                                    # noqa: E402
import sanctum_show as show                                   # noqa: E402
from reference_lighting import geometry_signature             # noqa: E402

N = cue.N
PAL = show.PALETTE
SLOT_X = {1: -5.2, 2: -2.6, 3: 0.0, 4: 2.6, 5: 5.2}
COL_X = [-6.5, -3.9, -1.3, 1.3, 3.9, 6.5]
RAY_Y = 2.30                 # laser ray plane: behind every sculpture (deepest 2.05), before the stacks (2.57)
GLORIA_C = (-0.10, RAY_Y, 3.55)
Z_FADE = (4.35, 4.85)        # rays die out just under the ceiling
# gloria: two mirrored fans of rays behind Michael, (angle above horizontal in degrees, length in metres)
GLORIA_FAN = ((2, 4.9), (9, 4.5), (17, 4.0), (26, 3.5), (36, 2.9), (47, 2.3))
GLORIA_R0 = 0.9              # rays start this far from the centre (hidden behind the figure)
GLORIA_FOLD = 28.0           # degrees the fans drop when folded
HELL_FAN = (-28, -14, 0, 14, 28)
SEED = 2611

# ------------------------------------------------------------------------------------ fixtures
# One row per light. `group` names the show channel that drives it (None = constant).
# aim-point data for the keys comes from the measured torso centroids of the imported sculptures.
def fixtures():
    F = []

    def add(**kw):
        F.append(kw)

    for n, x in SLOT_X.items():                                # library: three pools per aisle
        for group, y in (("lib_near", 4.2), ("lib_mid", 7.0), ("lib_far", 9.8)):
            add(id="LIB_%d_%s" % (n, group[4:]), group=group, kind="SPOT", loc=(x, y, 4.36), aim=(x, y, 0.0),
                color="amber", watts=270, spot=128, blend=0.75, radius=0.22, volume=True)
    add(id="LIB_BACK", group="back", kind="AREA", loc=(0, 10.9, 4.35), aim=(0, 12.0, 2.0), color="amber",
        watts=1500, size=(25.0, 1.2), volume=False)
    keys = {3: ((-1.5, -4.2, 4.6), (-0.04, 1.0, 2.95), "key_m", 880, 46),
            2: ((-1.3, -3.6, 4.5), (-2.60, 0.7, 2.05), "key_a", 540, 44),
            4: ((1.3, -3.6, 4.5), (2.50, 0.5, 2.00), "key_a", 540, 46),
            1: ((-3.6, -3.4, 4.4), (-5.25, 0.5, 1.70), "key_d", 720, 46),
            5: ((3.6, -3.4, 4.4), (5.70, 0.9, 1.80), "key_d", 720, 46)}
    for n, (loc, aim, group, watts, spot) in keys.items():      # sculpture keys: high, narrow, statues only
        add(id="KEY_S%d" % n, group=group, kind="SPOT", loc=loc, aim=aim, color="ivory", watts=watts,
            spot=spot, blend=0.55, radius=0.22, volume=False, link="statues")
    rims = [(1, 0.9, 2.3), (2, 0.9, 2.6), (3, -1.1, 3.4), (3, 1.1, 3.4), (4, -0.9, 2.6), (5, -0.9, 2.3)]
    for n, dx, tz in rims:                                      # cool rims from behind and above
        x = SLOT_X[n]
        add(id="RIM_S%d%s" % (n, "L" if dx < 0 else "R"), group="rim", kind="SPOT", loc=(x + dx, 2.36, 4.72),
            aim=(x, 0.95, tz), color="cool", watts=400, spot=42, blend=0.6, radius=0.08, volume=True)
    add(id="FILL", group=None, kind="AREA", loc=(0, -7.5, 3.6), aim=(0, 0.5, 2.2), color="cool", watts=170,
        size=(14.0, 3.5), volume=False, link="statues")
    add(id="COLUMN_SKIM", group=None, kind="AREA", loc=(0, -0.72, 4.86), aim=(0, -0.72, 0.0), color="amber",
        watts=75, size=(14.5, 0.35), volume=False, link="columns")
    for n, x in SLOT_X.items():                                 # glow of the open books under the figures
        add(id="BOOK_S%d" % n, group="book", kind="SPOT", loc=(x, -1.4, 0.12), aim=(x, 0.55, 1.5), color="paper",
            watts=70, spot=70, blend=1.0, radius=0.12, volume=False, link="statues")
    # A gloria: the real light. Hidden behind Michael, pointing at the lens through the haze.
    add(id="GLORIA_BACK", group="glow", kind="SPOT", loc=(0.0, 3.6, 3.05), aim=(0.0, -13.4, 1.9), color="cool",
        watts=5200, spot=64, blend=0.45, radius=0.12, volume=True)
    for sgn in (-1, 1):                                         # big soft sources: black marble reads by its reflections
        add(id="KICK_S%d" % (1 if sgn < 0 else 5), group="key_d", kind="AREA", loc=(sgn * 7.6, -2.6, 3.0),
            aim=(sgn * 5.3, 0.6, 1.7), color="ivory", watts=900, size=(2.2, 3.2), volume=False, link="statues")
    for sgn in (-1, 1):                                         # C embers behind the demons
        add(id="EMBER_%s" % ("L" if sgn < 0 else "R"), group="ember", kind="POINT", loc=(sgn * 5.2, 3.3, 0.55),
            color="ember", watts=520, radius=0.25, volume=True)
    for sgn in (-1, 1):                                         # B rakes: vertical slit projectors
        for group, xc, wall in (("rake_in", 2.6, 3.64), ("rake_out", 5.2, 6.24)):
            add(id="RAKE_%s_%s" % (group[5:], "L" if sgn < 0 else "R"), group=group, kind="SPOT",
                loc=(sgn * (xc - 0.75), 2.36, 2.3), aim=(sgn * wall, 6.0, 2.3), color="laser", watts=19000, spot=88,
                blend=0.05, radius=0.0, volume=False, slit="x", wall=sgn * wall, link="shelves", block="shelves")
    # D contour scan: horizontal slit from above the lens
    add(id="SCAN", group="scan", kind="SPOT", loc=(0.0, -9.0, 4.8), aim=(0.0, 0.9, 4.3), color="laser", watts=42000,
        spot=84, blend=0.05, radius=0.0, volume=False, slit="y", link="statues")
    return F


RAKE_Y = (3.4, 11.0)         # the rake line travels between these depths
SCAN_Z = (4.35, 0.45)        # the contour line travels between these heights (on the sculpture plane)
SCAN_AIM_Y = 0.9


# ------------------------------------------------------------------------------------ helpers
def args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="library_loop_sanctum.blend")
    ap.add_argument("--title", choices=("top", "bottom"), default="bottom")
    ap.add_argument("--exposure", type=float, default=0.0)
    ap.add_argument("--haze", type=float, default=0.007)
    ap.add_argument("--gain", type=float, default=1.0)
    return ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])


def aim_euler(loc, target):
    return (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()


def bake(owner, path, values, scale=1.0, index=-1):
    """key a looped channel on frames 1..N+1 (frame N+1 repeats frame 1), only where it changes"""
    v = [x * scale for x in values] + [values[0] * scale]
    for i, x in enumerate(v):
        a = v[i - 1] if i else None
        b = v[i + 1] if i + 1 < len(v) else None
        if i in (0, len(v) - 1) or x != a or x != b:
            if index >= 0:
                getattr(owner, path)[index] = x
                owner.keyframe_insert(path, index=index, frame=i + 1)
            else:
                setattr(owner, path, x)
                owner.keyframe_insert(path, frame=i + 1)


def node(nt, kind, name=None, **inputs):
    n = nt.nodes.new(kind)
    if name:
        n.name = n.label = name
    for k, v in inputs.items():
        n.inputs[k].default_value = v
    return n


def math_node(nt, op, a=None, b=None, clamp=False):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation, n.use_clamp = op, clamp
    for i, x in enumerate((a, b)):
        if x is None:
            continue
        if isinstance(x, (int, float)):
            n.inputs[i].default_value = x
        else:
            nt.links.new(x, n.inputs[i])
    return n.outputs[0]


def map_range(nt, value, a, b, c, d, smooth=True):
    n = nt.nodes.new("ShaderNodeMapRange")
    n.interpolation_type = "SMOOTHSTEP" if smooth else "LINEAR"
    n.clamp = True
    nt.links.new(value, n.inputs["Value"])
    for k, x in (("From Min", a), ("From Max", b), ("To Min", c), ("To Max", d)):
        n.inputs[k].default_value = x
    return n.outputs[0]


# ------------------------------------------------------------------------------------ laser look
def mat_beam(name, edge, core, glow_gain, core_gain):
    """Additive laser beam on one soft tube. Nothing about it is constant:
       * across: a thin over-exposed core (about a quarter of the tube radius) inside a halo that has
         faded to nothing well before the edge of the tube, so no outline of the geometry is visible
       * along: hottest at the emitter, dying away to the tip (UV.x = 0 root .. 1 tip)
       * per ray: its own gain (UV.y), so a fan is never a row of identical lines
       * in the air: slow 3D noise drifts through the beam like haze moving through real light, with
         small bright specks of dust
       * near the ceiling and the floor the beam dies out in world space
    Returns (material, level_node). `Level` is keyed per frame; HazeX / HazeY are keyed by the show."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    lw = node(nt, "ShaderNodeLayerWeight", Blend=0.5)
    facing = math_node(nt, "SUBTRACT", 1.0, lw.outputs["Facing"], clamp=True)      # 1 on the axis, 0 at the silhouette
    glow = math_node(nt, "POWER", facing, 5.0)
    hot = math_node(nt, "POWER", facing, 28.0)
    uv = nt.nodes.new("ShaderNodeUVMap")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(uv.outputs["UV"], sep.inputs[0])
    t = sep.outputs["X"]
    along = math_node(nt, "POWER", math_node(nt, "SUBTRACT", 1.0, t, clamp=True), 1.4)
    along = math_node(nt, "ADD", along, map_range(nt, t, 0.0, 0.14, 0.8, 0.0))     # extra heat at the emitter
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    pos = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], pos.inputs[0])
    zfade = math_node(nt, "MULTIPLY", map_range(nt, pos.outputs["Z"], Z_FADE[0], Z_FADE[1], 1.0, 0.0),
                      map_range(nt, pos.outputs["Z"], 0.05, 0.40, 0.0, 1.0))
    hx = nt.nodes.new("ShaderNodeValue"); hx.name = hx.label = "HazeX"
    hy = nt.nodes.new("ShaderNodeValue"); hy.name = hy.label = "HazeY"
    off = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(hx.outputs[0], off.inputs["X"]); nt.links.new(hy.outputs[0], off.inputs["Z"])
    add = nt.nodes.new("ShaderNodeVectorMath"); add.operation = "ADD"
    nt.links.new(geo.outputs["Position"], add.inputs[0]); nt.links.new(off.outputs[0], add.inputs[1])
    nz = node(nt, "ShaderNodeTexNoise", Scale=1.5, Detail=3.0, Roughness=0.6)
    nt.links.new(add.outputs[0], nz.inputs["Vector"])
    haze = map_range(nt, nz.outputs[0], 0.32, 0.68, 0.35, 1.40)
    dust = node(nt, "ShaderNodeTexNoise", Scale=26.0, Detail=1.0, Roughness=0.5)
    nt.links.new(add.outputs[0], dust.inputs["Vector"])
    haze = math_node(nt, "ADD", haze, map_range(nt, dust.outputs[0], 0.66, 0.74, 0.0, 0.9))
    level = nt.nodes.new("ShaderNodeValue"); level.name = level.label = "Level"
    body = math_node(nt, "ADD", math_node(nt, "MULTIPLY", glow, glow_gain), math_node(nt, "MULTIPLY", hot, core_gain))
    s = body
    for factor in (along, zfade, haze, sep.outputs["Y"], level.outputs[0]):
        s = math_node(nt, "MULTIPLY", s, factor)
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"
    pick = lambda socks, nm, ty: next(x for x in socks if x.name == nm and x.type == ty)   # Mix has one A/B/Result per data type
    pick(mix.inputs, "A", "RGBA").default_value = (*edge, 1)
    pick(mix.inputs, "B", "RGBA").default_value = (*core, 1)
    nt.links.new(math_node(nt, "POWER", facing, 16.0), pick(mix.inputs, "Factor", "VALUE"))
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(pick(mix.outputs, "Result", "RGBA"), em.inputs["Color"]); nt.links.new(s, em.inputs["Strength"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    sh = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(tr.outputs[0], sh.inputs[0]); nt.links.new(em.outputs[0], sh.inputs[1])
    nt.links.new(sh.outputs[0], out.inputs["Surface"])
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
        try:
            setattr(m, attr, val)
        except Exception:
            pass
    m.cycles.emission_sampling = "NONE"          # the co-located real lights do the lighting
    return m, level


def beam_mesh(name, rays, mat, seg=20):
    """rays: list of (origin, direction, length, r_root, r_tip, gain) in object space. One open, slightly
    widening tube per ray; UV.x runs 0 at the root to 1 at the tip, UV.y carries the ray's own gain."""
    verts, faces, uvs = [], [], []
    stations = 9
    for o, d, length, r0, r1, gain in rays:
        o, d = Vector(o), Vector(d).normalized()
        side = d.cross(Vector((0, 1, 0)))
        if side.length < 1e-6:
            side = d.cross(Vector((1, 0, 0)))
        side.normalize()
        up = d.cross(side).normalized()
        base = len(verts)
        for k in range(stations):
            t = k / (stations - 1)
            c = o + d * (length * t)
            for i in range(seg):
                a = 2 * math.pi * i / seg
                verts.append(tuple(c + (side * math.cos(a) + up * math.sin(a)) * (r0 + (r1 - r0) * t)))
        for k in range(stations - 1):
            for i in range(seg):
                a, b = base + k * seg + i, base + k * seg + (i + 1) % seg
                faces.append((a, b, b + seg, a + seg))
                t0, t1 = k / (stations - 1), (k + 1) / (stations - 1)
                uvs.extend(((t0, gain), (t0, gain), (t1, gain), (t1, gain)))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    layer_uv = me.uv_layers.new(name="UVMap")
    for i, uv in enumerate(uvs):
        layer_uv.data[i].uv = uv
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    me.materials.append(mat)
    return me


def laser_object(name, coll, mesh, loc):
    o = bpy.data.objects.new(name, mesh)
    coll.objects.link(o)
    o.location = loc
    for attr, val in (("visible_diffuse", False), ("visible_volume_scatter", False), ("visible_shadow", False),
                      ("visible_transmission", False)):
        setattr(o, attr, val)
    return o


def slit(light, axis, half, skirt=0.16):
    """turn a spot into a laser-line projector: a thin hot core with a faint skirt, thin along `axis`
    of the lamp's own space. TexCoord 'Normal' is the outgoing direction in lamp space (tested in 5.3)."""
    try:
        light.use_nodes = True
    except Exception:
        pass
    nt = light.node_tree
    em = next(n for n in nt.nodes if n.type == "EMISSION")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Normal"], sep.inputs[0])
    d = math_node(nt, "ABSOLUTE", math_node(nt, "DIVIDE", sep.outputs[axis.upper()], sep.outputs["Z"]))
    core = map_range(nt, d, half, half * 2.4, 1.0, 0.0)
    halo = math_node(nt, "MULTIPLY", map_range(nt, d, half * 2.0, half * 10.0, 1.0, 0.0), skirt)
    nt.links.new(math_node(nt, "ADD", core, halo), em.inputs["Strength"])


# ------------------------------------------------------------------------------------ set dressing
def boxes(name, items, mat):
    """items: (centre, size, rot_z, colour). One mesh with the 'Col' corner attribute the BOOKS material reads."""
    verts, faces, cols = [], [], []
    quad = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))
    for c, s, rz, col in items:
        b = len(verts)
        for dx, dy, dz in ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)):
            x, y = dx * s[0] / 2, dy * s[1] / 2
            verts.append((c[0] + x * math.cos(rz) - y * math.sin(rz), c[1] + x * math.sin(rz) + y * math.cos(rz), c[2] + dz * s[2] / 2))
        for q in quad:
            faces.append(tuple(b + i for i in q))
            cols.extend([(*col, 1.0)] * 4)
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    ca = me.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="CORNER")
    for i, c in enumerate(cols):
        ca.data[i].color = c
    me.materials.append(mat)
    return me


def redress(scene, coll, rng):
    """pages and floor books: nothing in front of the sculptures any more"""
    notes = {}
    old = bpy.data.objects.get("PAGES")
    if old:
        old.hide_render = old.hide_viewport = True
    verts, faces = [], []
    for n, sx in SLOT_X.items():                               # a stream of pages rising behind each figure
        for k in range(30):
            t = (k + rng.random()) / 30.0
            y = 2.25 + 6.6 * t ** 0.85
            reach = 0.85 if y > 2.55 else 0.95
            x = sx + max(-reach, min(reach, 0.8 * math.sin(6.0 * t + n) * (0.35 + 0.65 * t) + rng.uniform(-0.15, 0.15)))
            z = min(4.15, 0.9 + 3.1 * t ** 0.7 + rng.uniform(-0.25, 0.25))
            if y < 4.0 and 1.0 < z < 3.6:                        # keep paper out of the mouths of the rake projectors
                y += 1.8
            m = Matrix.Translation((x, y, z)) @ Matrix.Rotation(rng.uniform(0, 6.28), 4, "Z") @ \
                Matrix.Rotation(rng.uniform(-1.4, 1.4), 4, "X") @ Matrix.Rotation(rng.uniform(-1.4, 1.4), 4, "Y")
            b = len(verts)
            for p in ((-0.105, -0.15, 0.0), (0.105, -0.15, 0.02), (0.105, 0.15, 0.0), (-0.105, 0.15, 0.03)):
                verts.append(tuple(m @ Vector(p)))
            faces.append((b, b + 1, b + 2, b + 3))
    me = bpy.data.meshes.new("PAGES_SANCTUM")
    me.from_pydata(verts, [], faces)
    me.update()
    me.materials.append(bpy.data.materials["PAPER"])
    coll.objects.link(bpy.data.objects.new("PAGES_SANCTUM", me))
    notes["pages"] = len(faces)
    moved = []
    for o in sorted((o for o in scene.objects if o.name.startswith("FLYBOOK_")), key=lambda o: o.name):
        if o.location.y < 4.0:                                 # keep the loop animation, shift the whole path
            sx = min(SLOT_X.values(), key=lambda v: abs(v - o.location.x))
            new = Vector((sx + rng.uniform(-0.6, 0.6), rng.uniform(4.4, 8.5), min(o.location.z, 4.0)))
            o.delta_location = new - o.location
            moved.append(o.name)
    notes["flybooks_moved"] = moved
    old = bpy.data.objects.get("FLOOR_BOOKS")
    if old:
        old.hide_render = old.hide_viewport = True
    palette = ((0.20, 0.03, 0.03), (0.03, 0.10, 0.07), (0.25, 0.16, 0.05), (0.10, 0.07, 0.04), (0.33, 0.27, 0.18), (0.18, 0.10, 0.04))
    items = []
    for n, sx in SLOT_X.items():
        for _ in range(5):
            s = (rng.uniform(0.2, 0.34), rng.uniform(0.28, 0.44), rng.uniform(0.04, 0.09))
            col = tuple(c * rng.uniform(0.7, 1.2) for c in rng.choice(palette))
            items.append(((sx + rng.uniform(-1.05, 1.05), rng.uniform(-2.6, -1.25), s[2] / 2), s, rng.uniform(0, 6.28), col))
    coll.objects.link(bpy.data.objects.new("FLOOR_BOOKS_SANCTUM", boxes("FLOOR_BOOKS_SANCTUM", items, bpy.data.materials["BOOKS"])))
    notes["floor_books"] = len(items)
    return notes


def retitle(scene, where):
    for mat in bpy.data.materials:                             # stable type: no random letter dropouts
        if mat.name.startswith("TITLE_") and mat.use_nodes:
            mat.node_tree.animation_data_clear()
            for n in mat.node_tree.nodes:
                if n.type == "EMISSION":
                    n.inputs["Strength"].default_value = 1.0
                    n.inputs["Color"].default_value = (0.95, 0.92, 0.86, 1)
    t = bpy.data.objects["TITLE"]
    dist = abs(t.location.z)
    half_w = dist * 18.0 / scene.camera.data.lens
    half_h = half_w * scene.render.resolution_y / scene.render.resolution_x
    if where == "top":
        t.scale = tuple(s * 0.8 for s in t.scale)
        t.location.y = 0.905 * half_h
        return dict(placement=where, strength=1.0, flicker=False, shade=False)
    # bottom: small, on the floor in front of the plinths, with a soft shade so it never fights the marble
    t.scale = tuple(s * 0.62 for s in t.scale)
    t.location.y = -0.90 * half_h
    me = bpy.data.meshes.new("SANCTUM_TITLE_SHADE")
    d2 = dist + 0.02
    w, h = d2 * 18.0 / scene.camera.data.lens, d2 * 18.0 / scene.camera.data.lens * scene.render.resolution_y / scene.render.resolution_x
    me.from_pydata([(-w * 0.34, -h, 0), (w * 0.34, -h, 0), (w * 0.34, -h * 0.72, 0), (-w * 0.34, -h * 0.72, 0)], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    for i, c in enumerate(((0, 0), (1, 0), (1, 1), (0, 1))):
        uv.data[i].uv = c
    ob = bpy.data.objects.new("SANCTUM_TITLE_SHADE", me)
    bpy.data.collections["TITLE"].objects.link(ob)
    ob.parent = scene.camera
    ob.location = (0, 0, -d2)
    for attr in ("visible_shadow", "visible_diffuse", "visible_glossy", "visible_transmission", "visible_volume_scatter"):
        setattr(ob, attr, False)
    mat = bpy.data.materials.new("SANCTUM_TITLE_SHADE")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    uvn = nt.nodes.new("ShaderNodeUVMap")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(uvn.outputs["UV"], sep.inputs[0])
    edge = math_node(nt, "MULTIPLY", map_range(nt, sep.outputs["X"], 0.0, 0.3, 0.0, 1.0), map_range(nt, sep.outputs["X"], 0.7, 1.0, 1.0, 0.0))
    fac = math_node(nt, "MULTIPLY", math_node(nt, "MULTIPLY", map_range(nt, sep.outputs["Y"], 0.25, 1.0, 1.0, 0.0), edge), 0.62)
    mix = nt.nodes.new("ShaderNodeMixShader")
    clear = nt.nodes.new("ShaderNodeBsdfTransparent")
    black = nt.nodes.new("ShaderNodeEmission")
    black.inputs["Color"].default_value = (0, 0, 0, 1)
    nt.links.new(fac, mix.inputs[0]); nt.links.new(clear.outputs[0], mix.inputs[1]); nt.links.new(black.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    me.materials.append(mat)
    return dict(placement=where, strength=1.0, flicker=False, shade=True)


# ------------------------------------------------------------------------------------ main
def main():
    o = args()
    source, output = Path(bpy.data.filepath).resolve(), Path(o.out).resolve()
    if not source.is_file() or output == source:
        raise RuntimeError("load the imported scene and choose a separate --out file")
    scene = bpy.data.scenes["HERO"]
    try:
        bpy.context.window.scene = scene
    except Exception:
        pass
    scene.frame_set(1)
    if "RIG_SANCTUM" in bpy.data.collections:
        raise RuntimeError("start from library_loop_final.blend, not from an existing sanctum scene")
    before = geometry_signature()
    cam = scene.camera
    cam_before = (cam.name, tuple(cam.location), tuple(cam.rotation_euler), cam.data.lens)
    rng = random.Random(SEED)
    ch = show.build()
    report = dict(source=str(source.name), output=str(output.name), show=show.master(ch))

    # ---- retire the first version's rig (kept in the file, hidden) --------------------------------
    retired = []
    for ob in scene.objects:
        if ob.type == "LIGHT" or ob.name.startswith(("LASER_", "GRID_")):
            ob.hide_render = ob.hide_viewport = True
            retired.append(ob.name)
            if ob.type == "LIGHT":
                ob.data.animation_data_clear()
                ob.data.energy = 0.0
    bpy.data.collections["LASERS"].hide_render = True
    report["retired"] = retired

    rig = bpy.data.collections.new("RIG_SANCTUM")
    las = bpy.data.collections.new("LASERS_SANCTUM")
    dress = bpy.data.collections.new("DRESSING_SANCTUM")
    for c in (rig, las, dress):
        scene.collection.children.link(c)
    statues = [bpy.data.objects["TRIPO_%d" % i] for i in range(1, 6)]
    columns = [ob for ob in scene.objects if ob.name.startswith("COLUMN_") and ob.type == "MESH"]
    link = {}
    shelves = [bpy.data.objects[n] for n in ("BOOKCASES", "BACK_WALL")]
    for key, members in (("statues", statues), ("columns", columns), ("shelves", shelves)):
        link[key] = bpy.data.collections.new("LINK_" + key.upper())      # receiver sets for light linking
        for ob in members:
            link[key].objects.link(ob)

    # ---- materials -----------------------------------------------------------------------------
    stone = bpy.data.materials["MARBLE"].copy()
    stone.name = "SANCTUM_STONE"                                # quieter architecture: the idea of the gallery version
    for n in stone.node_tree.nodes:
        if n.type == "VALTORGB":
            n.color_ramp.elements[0].color = (0.13, 0.115, 0.10, 1)
            n.color_ramp.elements[1].color = (0.30, 0.27, 0.23, 1)
        elif n.type == "BSDF_PRINCIPLED":
            n.inputs["Roughness"].default_value = 0.55
    for ob in columns:
        for slot in ob.material_slots:
            if slot.material and slot.material.name == "MARBLE":
                slot.material = stone
    for n in bpy.data.materials["OBSIDIAN"].node_tree.nodes:   # thinner gold veins: form before pattern
        if n.type == "VALTORGB":
            n.color_ramp.elements[1].position = 0.013
            n.color_ramp.elements[0].color = (0.42, 0.30, 0.10, 1)
    for name, key, val in (("PAPER", "Base Color", (0.50, 0.45, 0.36, 1)), ("FLOOR", "Roughness", 0.20)):
        for n in bpy.data.materials[name].node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED":
                n.inputs[key].default_value = val
    for n in bpy.data.materials["HAZE"].node_tree.nodes:
        if n.type == "VOLUME_SCATTER":
            n.inputs["Density"].default_value = o.haze
            n.inputs["Anisotropy"].default_value = 0.55
    for n in scene.world.node_tree.nodes:
        if n.type == "BACKGROUND":
            n.inputs["Color"].default_value = (0.30, 0.42, 0.60, 1)
            n.inputs["Strength"].default_value = 0.015

    report["dressing"] = redress(scene, dress, rng)
    report["title"] = retitle(scene, o.title)

    # ---- look ----------------------------------------------------------------------------------
    vs = scene.view_settings
    vs.view_transform, vs.look, vs.exposure = "AgX", "AgX - Medium High Contrast", o.exposure
    comp = scene.compositing_node_group if hasattr(scene, "compositing_node_group") else scene.node_tree
    for n in comp.nodes:
        if n.type == "GLARE":
            if "Strength" in n.inputs:
                n.inputs["Threshold"].default_value = 1.6
                n.inputs["Strength"].default_value = 0.35
                n.inputs["Size"].default_value = 0.55
            else:
                n.threshold, n.mix = 1.6, -0.7

    prefs = bpy.context.preferences.edit
    interp = prefs.keyframe_new_interpolation_type
    prefs.keyframe_new_interpolation_type = "LINEAR"
    lights, lasers = {}, {}
    try:
        # ---- lights from the fixture table ---------------------------------------------------------
        for fx in fixtures():
            d = bpy.data.lights.new(fx["id"], fx["kind"])
            d.color = PAL[fx["color"]]
            watts = fx["watts"] * o.gain
            d.energy = watts
            if fx["kind"] == "SPOT":
                d.spot_size, d.spot_blend, d.shadow_soft_size = math.radians(fx["spot"]), fx["blend"], fx["radius"]
            elif fx["kind"] == "AREA":
                d.shape = "RECTANGLE"
                d.size, d.size_y = fx["size"]
            else:
                d.shadow_soft_size = fx["radius"]
            ob = bpy.data.objects.new(fx["id"], d)
            rig.objects.link(ob)
            ob.location = fx["loc"]
            if "aim" in fx:
                ob.rotation_euler = aim_euler(fx["loc"], fx["aim"])
            ob.visible_volume_scatter = bool(fx.get("volume"))
            if fx.get("link"):
                ob.light_linking.receiver_collection = link[fx["link"]]
            if fx.get("block"):                                 # only these objects cast this light's shadows
                ob.light_linking.blocker_collection = link[fx["block"]]
            if fx.get("slit"):
                slit(d, fx["slit"], 0.014 if fx["slit"] == "x" else 0.0018, 0.16 if fx["slit"] == "x" else 0.07)   # shelf walls are seen at a grazing angle
            lights[fx["id"]] = (ob, fx, watts)
            group = fx["group"]
            if group is None:
                continue
            if group.startswith("rake"):                        # slide the line into the aisle; keep it as bright far away
                pos = ch[group + "_pos"]
                yaw, energy = [], []
                for i in range(N):
                    ty = cue.lerp(RAKE_Y[0], RAKE_Y[1], pos[i])
                    dx, dy = fx["wall"] - fx["loc"][0], ty - fx["loc"][1]
                    yaw.append(math.atan2(-dx, dy))
                    energy.append(ch[group][i] * (math.hypot(dx, dy) / 4.0) ** 1.3)
                ob.rotation_euler = (math.radians(90), 0.0, yaw[0])
                bake(ob, "rotation_euler", yaw, index=2)
                bake(d, "energy", energy, watts)
            elif group == "scan":
                pitch = []
                for i in range(N):
                    tz = cue.lerp(SCAN_Z[0], SCAN_Z[1], ch["scan_pos"][i])
                    pitch.append(math.radians(90) - math.atan2(fx["loc"][2] - tz, SCAN_AIM_Y - fx["loc"][1]))
                ob.rotation_euler = (pitch[0], 0.0, 0.0)
                bake(ob, "rotation_euler", pitch, index=0)
                bake(d, "energy", ch["scan"], watts)
            else:
                bake(d, "energy", ch[group], watts)

        # ---- lasers: emissive rays --------------------------------------------------------------
        m_a, lv_a = mat_beam("BEAM_GLORIA", PAL["laser"], PAL["laser_core"], 0.75, 3.8)
        gloria = []
        for sgn in (-1, 1):
            rays = []
            for a, length in GLORIA_FAN:
                r = math.radians(a)
                d = (sgn * math.cos(r), 0, math.sin(r))
                rays.append(((d[0] * GLORIA_R0, 0, d[2] * GLORIA_R0), d, length, 0.038, 0.062, rng.uniform(0.55, 1.0)))
            g = laser_object("LASER2_GLORIA_%s" % ("L" if sgn < 0 else "R"), las, beam_mesh("LASER2_GLORIA", rays, m_a), GLORIA_C)
            bake(g, "rotation_euler", [math.radians(sgn * GLORIA_FOLD * (1.0 - v)) for v in ch["rays_open"]], index=1)
            for i in range(3):
                bake(g, "scale", [0.45 + 0.55 * v for v in ch["rays_open"]], index=i)
            gloria.append(g)
        m_c, lv_c = mat_beam("BEAM_HELL", PAL["ember"], PAL["ember_core"], 0.9, 4.6)
        hell = []
        for sgn in (-1, 1):
            rays = []
            for a in HELL_FAN:
                r = math.radians(a)
                rays.append(((0, 0, 0), (math.sin(r), 0, math.cos(r)), 3.6 - 0.5 * abs(a) / 28.0, 0.038, 0.066, rng.uniform(0.6, 1.0)))
            h = laser_object("LASER2_HELL_%s" % ("L" if sgn < 0 else "R"), las, beam_mesh("LASER2_HELL", rays, m_c),
                             (sgn * 5.2, RAY_Y, 0.30))
            bake(h, "rotation_euler", [math.radians(sgn * v) for v in ch["hell_sway"]], index=1)
            hell.append(h)
        for lv, key in ((lv_a, "rays"), (lv_c, "hell")):
            bake(lv.outputs[0], "default_value", ch[key])
        for m in (m_a, m_c):
            bake(m.node_tree.nodes["HazeX"].outputs[0], "default_value", ch["haze_x"], 1.5)
            bake(m.node_tree.nodes["HazeY"].outputs[0], "default_value", ch["haze_y"], 1.5)
        lasers = dict(gloria=gloria, hell=hell)
    finally:
        prefs.keyframe_new_interpolation_type = interp

    # ---- build-time checks ---------------------------------------------------------------------
    dg = bpy.context.evaluated_depsgraph_get()
    trees = {ob.name: (BVHTree.FromObject(ob, dg), ob.matrix_world.inverted()) for ob in statues + columns}

    def hit(a, b):
        """name of the sculpture/column that segment a-b touches, or None"""
        for name, (tree, inv) in trees.items():
            la, lb = inv @ Vector(a), inv @ Vector(b)
            d = lb - la
            if d.length > 1e-6 and tree.ray_cast(la, d.normalized(), d.length)[0] is not None:
                return name
        return None

    problems, touched = [], set()
    ray_defs = {}
    for g, sgn in zip(gloria, (-1, 1)):
        ray_defs[g.name] = [(Vector((sgn * math.cos(math.radians(a)) * GLORIA_R0, 0, math.sin(math.radians(a)) * GLORIA_R0)),
                             Vector((sgn * math.cos(math.radians(a)), 0, math.sin(math.radians(a)))), length) for a, length in GLORIA_FAN]
    for h in hell:
        ray_defs[h.name] = [(Vector((0, 0, 0)), Vector((math.sin(math.radians(a)), 0, math.cos(math.radians(a)))), 3.6 - 0.5 * abs(a) / 28.0)
                            for a in HELL_FAN]
    closure = {}

    def sample():
        vals = {}
        for name, (ob, fx, watts) in lights.items():
            vals[name + ".energy"] = ob.data.energy
            vals[name + ".rot"] = tuple(round(v, 6) for v in ob.rotation_euler)
        for ob in gloria + hell:
            vals[ob.name + ".rot"] = tuple(round(v, 6) for v in ob.rotation_euler)
            vals[ob.name + ".scale"] = tuple(round(v, 6) for v in ob.scale)
        for m in (m_a, m_c):
            for nn in ("Level", "HazeX", "HazeY"):
                vals[m.name + "." + nn] = m.node_tree.nodes[nn].outputs[0].default_value
        return vals

    for f in list(range(1, N + 1)) + [N + 1]:
        scene.frame_set(f)
        if f in (1, N + 1):
            closure[f] = sample()
        if f > N:
            continue
        for ob in gloria + hell:
            lit = ch["rays"][f - 1] if ob in gloria else ch["hell"][f - 1]
            if lit <= 0.0:
                continue
            mw = ob.matrix_world
            for origin, direction, length in ray_defs[ob.name]:
                a, b = mw @ origin, mw @ (origin + direction * length)
                if a.z >= Z_FADE[1]:
                    continue
                if b.z > Z_FADE[1]:                              # the shader has faded the ray out by here
                    b = a + (b - a) * ((Z_FADE[1] - a.z) / (b.z - a.z))
                name = hit(a, b)
                if name:
                    touched.add((ob.name, name, f))
    scene.frame_set(1)
    if touched:
        problems.append("laser rays touch geometry: %s" % sorted(touched)[:8])
    worst = 0.0
    for k, v in closure[1].items():
        w = closure[N + 1][k]
        d = max(abs(a - b) for a, b in zip(v, w)) if isinstance(v, tuple) else abs(v - w)
        worst = max(worst, d)
        if d > 1e-4:
            problems.append("channel %s does not close at frame %d (differs by %g)" % (k, N + 1, d))
    report["loop_closure_max_difference"] = worst
    gb = lights["GLORIA_BACK"][0]
    blocker = hit(cam.location, gb.location)
    if blocker is None:
        problems.append("the gloria emitter is visible from the camera")
    report["gloria_hidden_behind"] = blocker
    inside = []
    for name, (ob, fx, watts) in lights.items():
        for sname, (tree, inv) in trees.items():
            near = tree.find_nearest(inv @ ob.location)
            if near[0] is not None and near[3] < 0.10:
                inside.append((name, sname, round(near[3], 3)))
    if inside:
        problems.append("fixtures inside or touching geometry: %s" % inside)
    front = []                                                  # anything loose in front of a sculpture?
    sil = []
    for st in statues:
        me = st.evaluated_get(dg).to_mesh()
        step = max(1, len(me.vertices) // 20000)
        pts = [st.matrix_world @ me.vertices[i].co for i in range(0, len(me.vertices), step)]
        st.evaluated_get(dg).to_mesh_clear()
        grid = set()
        for p in pts:
            v = world_to_camera_view(scene, cam, p)
            grid.add((int(v.x * 96), int(v.y * 48)))
        ys = sorted(p.y for p in pts)
        sil.append((grid, ys[len(ys) // 2]))
    loose = [(ob.name, ob.matrix_world.translation.copy()) for ob in scene.objects if ob.name.startswith("FLYBOOK_")]
    pm = bpy.data.objects["PAGES_SANCTUM"].data
    loose += [("page%d" % p.index, sum((pm.vertices[i].co for i in p.vertices), Vector()) / len(p.vertices)) for p in pm.polygons]
    for name, p in loose:
        v = world_to_camera_view(scene, cam, p)
        for grid, median_y in sil:
            if (int(v.x * 96), int(v.y * 48)) in grid and p.y < median_y:
                front.append(name)
    if front:
        problems.append("loose paper in front of a sculpture: %s" % front[:10])
    report["paper_in_front_of_sculptures"] = len(front)
    if geometry_signature() != before:
        problems.append("sculpture geometry, material assignment or placement changed")
    if (cam.name, tuple(cam.location), tuple(cam.rotation_euler), cam.data.lens) != cam_before:
        problems.append("camera changed")
    if any(not bpy.data.objects[n].hide_render for n in retired):
        problems.append("part of the first version's rig is still renderable")
    if (scene.frame_start, scene.frame_end, scene.render.fps) != (1, 300, 30):
        problems.append("frame range or fps changed")
    report["fixtures"] = [dict(id=n, group=fx["group"], kind=fx["kind"], loc=fx["loc"], watts=round(w, 1), color=fx["color"],
                               volume=bool(fx.get("volume")), link=fx.get("link")) for n, (ob, fx, w) in lights.items()]
    report["options"] = dict(title=o.title, exposure=o.exposure, haze=o.haze, gain=o.gain)
    report["checks_passed"] = not problems
    if problems:
        raise RuntimeError("sanctum build failed its checks:\n  - " + "\n  - ".join(problems))

    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    out_dir = output.parent / "out"
    out_dir.mkdir(exist_ok=True)
    (out_dir / (output.stem + "-validation.json")).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    e = report["show"]["estimate"]
    print("[sanctum] saved %s | %d lights, %d retired | closure %.2g | estimate min/mean %.2f | checks passed"
          % (output.name, len(lights), len(retired), worst, e["min_over_mean"]), flush=True)


if __name__ == "__main__":
    main()
