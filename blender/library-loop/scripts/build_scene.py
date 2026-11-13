"""
Something Ventured · Library Loop  —  scene builder
====================================================
Builds the whole 10-second loop procedurally: the library colonnade, five sculpture
slots (proxy angels / demons standing on giant open books), the strobe rig, the laser
rig, camera, title, compositor and the music track.

Run headless:
    blender -b -P build_scene.py -- --out ../library_loop.blend
    blender -b -P build_scene.py -- --out ../library_loop.blend --engine EEVEE      (faster, look not verified)
    blender -b -P build_scene.py -- --out ../library_loop.blend --quality previz    (low samples, half size)
    extra: --haze 0.01 (0 = no volumetric haze)
or open this file in Blender's Text Editor and press "Run Script"
(it then builds into the currently open file — use an empty one).

Scenes created
    HERO  the final look: uplight strobes + blue ceiling grid + lasers   (bottom row of the reference)
    TOP   same camera, neutral top light scanning right-to-left, no lasers (top row of the reference)

Tested on Blender 4.2 LTS, 4.5 LTS and 5.3.
"""
import bpy, bmesh, math, os, random, sys, colorsys
from math import radians, sin, cos, pi, exp
from mathutils import Vector, Euler, Matrix
import numpy as np

# ----------------------------------------------------------------------------------------------
# CONFIG  (everything you are likely to tweak lives here)
# ----------------------------------------------------------------------------------------------
FPS = 30
N = 300                  # frames in the loop (10.0 s). Frame N+1 must look like frame 1.
BPM = 130.0              # measured from the reference soundtrack
BEAT0 = 0.42             # seconds: time of beat k=1 (beat k=0 is the hit at t=0, clipped by the edit)
RES = (1920, 744)        # one panel, 2.58:1 like the reference. 16:9 -> (1920, 1080)

BAY = 2.6                # metres between columns
CEIL_Z = 4.95
BACK_Y = 12.0
CAM_LOC = (0.0, -13.4, 2.3)
CAM_LENS = 35.0

HAZE_DENSITY = 0.010     # volumetric haze. 0 disables it
TITLE_LINES = ("SOMETHING VENTURED", "THE PSYCHEDELIC LIBRARY")
SEED = 1215

# sculpture slots, left to right.  asset = file stem expected by import_tripo.py
SLOTS = [
    dict(n=1, asset="hero_1_demon_rising",    kind="demon",   height=2.9, side="hell"),
    dict(n=2, asset="hero_2_angel_trumpet",   kind="trumpet", height=3.3, side="heaven"),
    dict(n=3, asset="hero_3_michael_dragon",  kind="michael", height=4.3, side="heaven"),
    dict(n=4, asset="hero_4_angel_spear",     kind="spear",   height=3.3, side="heaven"),
    dict(n=5, asset="hero_5_lucifer_falling", kind="lucifer", height=2.9, side="hell"),
]

# colours (linear RGB)
COL_KEY = (0.90, 0.95, 1.00)       # strobe white, slightly cold
COL_GRID = (0.05, 0.32, 1.00)      # ceiling grid blue (reference)
COL_HEAVEN = (0.35, 0.85, 1.00)    # cyan-white lasers
COL_FAN = (0.04, 0.20, 1.00)       # deep blue fans
COL_HELL = (1.00, 0.03, 0.01)      # red lasers

# ----------------------------------------------------------------------------------------------
# arguments / paths
# ----------------------------------------------------------------------------------------------
def _args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = dict(out=None, engine="CYCLES", quality="final", root=None, haze=None)
    i = 0
    while i < len(a):
        k = a[i].lstrip("-")
        if k in out and i + 1 < len(a):
            out[k] = a[i + 1]; i += 2
        else:
            i += 1
    return out

ARGS = _args()

def _root():
    if ARGS["root"]:
        return os.path.abspath(ARGS["root"])
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if os.path.isdir(here):
            return os.path.dirname(here)
    except NameError:
        pass
    for t in bpy.data.texts:
        if t.filepath and t.name.startswith("build_scene"):
            return os.path.dirname(os.path.dirname(bpy.path.abspath(t.filepath)))
    return os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.getcwd()

if ARGS["haze"] is not None:
    HAZE_DENSITY = float(ARGS["haze"])
ROOT = _root()
AUDIO = os.path.join(ROOT, "reference", "audio_loop.wav")
FONT = os.path.join(ROOT, "assets", "fonts", "Jost-Light.ttf")
rng = random.Random(SEED)
nrng = np.random.default_rng(SEED)

# ----------------------------------------------------------------------------------------------
# timing helpers
# ----------------------------------------------------------------------------------------------
BEAT = 60.0 / BPM

def beat_time(k):
    """seconds of beat k (float). k=0 is the clipped hit at t=0, k=1 is at BEAT0."""
    return k * BEAT0 if k < 1 else BEAT0 + (k - 1) * BEAT

def bf(k):
    """frame number (1-based) of beat k"""
    return 1 + int(round(beat_time(k) * FPS))

N_BEATS = int((N / FPS - BEAT0) / BEAT) + 1          # 21 -> beats 0..21


class Chan:
    """one animated value, stored per frame, wraps around the loop"""
    def __init__(self, base=0.0):
        self.v = np.full(N, float(base))

    def hit(self, frame, peak=1.0, dur=9, tau=5.0):
        for i in range(int(dur)):
            j = (frame - 1 + i) % N
            self.v[j] = max(self.v[j], peak * exp(-i / tau))
        return self

    def hold(self, f0, f1, val, mode="max"):
        for f in range(int(f0), int(f1)):
            j = (f - 1) % N
            self.v[j] = max(self.v[j], val) if mode == "max" else val
        return self

    def mul(self, f0, f1, val):
        for f in range(int(f0), int(f1)):
            self.v[(f - 1) % N] *= val
        return self

    def bake(self, idblock, path, scale=1.0, index=-1):
        v = self.v * scale
        for i in range(N):
            a, b = v[i - 1], v[(i + 1) % N]
            if i in (0, N - 1) or v[i] != a or v[i] != b:
                _key(idblock, path, i + 1, float(v[i]), index)


def _key(idblock, path, frame, value, index=-1):
    """keyframe a property given as 'prop' or 'prop[i]' path on an id / struct"""
    if index >= 0:
        getattr(idblock, path)[index] = value
        idblock.keyframe_insert(path, index=index, frame=frame)
    else:
        setattr(idblock, path, value)
        idblock.keyframe_insert(path, frame=frame)


# ----------------------------------------------------------------------------------------------
# data helpers
# ----------------------------------------------------------------------------------------------
def purge():
    for sc in list(bpy.data.scenes)[1:]:
        bpy.data.scenes.remove(sc)
    sc = bpy.data.scenes[0]
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    for blocks in (bpy.data.meshes, bpy.data.curves, bpy.data.lights, bpy.data.cameras,
                   bpy.data.materials, bpy.data.actions, bpy.data.node_groups, bpy.data.worlds,
                   bpy.data.sounds):
        for b in list(blocks):
            try:
                blocks.remove(b)
            except Exception:
                pass
    if sc.sequence_editor:
        sc.sequence_editor_clear()
    return sc


def coll(name, parent):
    c = bpy.data.collections.new(name)
    parent.children.link(c)
    return c


def obj(name, data, c, loc=(0, 0, 0), rot=(0, 0, 0)):
    o = bpy.data.objects.new(name, data)
    c.objects.link(o)
    o.location = loc
    o.rotation_euler = rot
    return o


def bm_obj(bm, name, c, mat=None, smooth=False, loc=(0, 0, 0)):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    if mat:
        me.materials.append(mat)
    return obj(name, me, c, loc)


def no_gi(o, shadow=False):
    """emissive helper geometry: visible to camera and reflections, but not a (noisy) light source"""
    for attr, val in (("visible_diffuse", False), ("visible_volume_scatter", False),
                      ("visible_shadow", shadow)):
        try:
            setattr(o, attr, val)
        except Exception:
            pass

# ---- bmesh primitives ---------------------------------------------------------------------
def slab(bm, c, size, rot=(0, 0, 0)):
    g = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.transform(bm, matrix=Matrix.LocRotScale(Vector(c), Euler(rot), Vector(size)), verts=g["verts"])
    return g["verts"]


def limb(bm, p0, p1, r0, r1=None, seg=10):
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    if d.length < 1e-6:
        return []
    r1 = r0 if r1 is None else r1
    g = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg,
                              radius1=max(r0, 1e-4), radius2=max(r1, 1e-4), depth=d.length)
    m = Matrix.Translation((p0 + p1) / 2) @ Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=m, verts=g["verts"])
    return g["verts"]


def ball(bm, c, r, sc=(1, 1, 1), u=14, v=10):
    g = bmesh.ops.create_uvsphere(bm, u_segments=u, v_segments=v, radius=r)
    bmesh.ops.transform(bm, matrix=Matrix.Translation(Vector(c)) @ Matrix.Diagonal((*sc, 1.0)), verts=g["verts"])
    return g["verts"]


def poly(bm, pts):
    vs = [bm.verts.new(Vector(p)) for p in pts]
    try:
        bm.faces.new(vs)
    except ValueError:
        pass
    return vs


def xform_since(bm, start, m):
    bm.verts.ensure_lookup_table()
    bmesh.ops.transform(bm, matrix=m, verts=bm.verts[start:])


def boxes_mesh(name, centers, sizes, colors, rotz=None):
    """many boxes in one mesh, with a per-corner colour attribute 'Col'"""
    centers = np.asarray(centers, float); sizes = np.asarray(sizes, float); colors = np.asarray(colors, float)
    n = len(centers)
    unit = np.array([[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
                     [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]], float) * 0.5
    local = unit[None, :, :] * sizes[:, None, :]
    if rotz is not None:
        c, s = np.cos(rotz)[:, None], np.sin(rotz)[:, None]
        x = local[:, :, 0] * c - local[:, :, 1] * s
        y = local[:, :, 0] * s + local[:, :, 1] * c
        local = np.stack([x, y, local[:, :, 2]], axis=2)
    verts = (centers[:, None, :] + local).reshape(-1, 3)
    quad = np.array([[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]])
    faces = (quad[None, :, :] + (np.arange(n) * 8)[:, None, None]).reshape(-1, 4)
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts.tolist(), [], faces.tolist())
    me.update()
    ca = me.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="CORNER")
    rgba = np.concatenate([colors, np.ones((n, 1))], axis=1)
    ca.data.foreach_set("color", np.repeat(rgba, 24, axis=0).ravel())
    return me

# ----------------------------------------------------------------------------------------------
# materials
# ----------------------------------------------------------------------------------------------
def _nodes(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    return m, nt, out


def mat_principled(name, color, rough=0.5, metal=0.0, veins=None, bump=0.0):
    m, nt, out = _nodes(name)
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    nt.links.new(b.outputs[0], out.inputs["Surface"])
    if veins is not None or bump:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 2.2
        nz.inputs["Detail"].default_value = 9.0
        nz.inputs["Roughness"].default_value = 0.62
        nz.inputs["Distortion"].default_value = 2.4
        nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
        if veins is not None:                       # thin veins: |noise - 0.5| close to zero
            sub = nt.nodes.new("ShaderNodeMath"); sub.operation = "SUBTRACT"; sub.inputs[1].default_value = 0.5
            ab = nt.nodes.new("ShaderNodeMath"); ab.operation = "ABSOLUTE"
            ramp = nt.nodes.new("ShaderNodeValToRGB")
            ramp.color_ramp.elements[0].position = 0.0
            ramp.color_ramp.elements[0].color = (*veins, 1)
            ramp.color_ramp.elements[1].position = 0.035
            ramp.color_ramp.elements[1].color = (*color, 1)
            nt.links.new(nz.outputs[0], sub.inputs[0])
            nt.links.new(sub.outputs[0], ab.inputs[0])
            nt.links.new(ab.outputs[0], ramp.inputs[0])
            nt.links.new(ramp.outputs[0], b.inputs["Base Color"])
        if bump:
            bp = nt.nodes.new("ShaderNodeBump")
            bp.inputs["Strength"].default_value = bump
            nt.links.new(nz.outputs[0], bp.inputs["Height"])
            nt.links.new(bp.outputs[0], b.inputs["Normal"])
    return m


def mat_vertex_color(name, rough=0.55):
    m, nt, out = _nodes(name)
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    a = nt.nodes.new("ShaderNodeVertexColor")
    a.layer_name = "Col"
    b.inputs["Roughness"].default_value = rough
    nt.links.new(a.outputs["Color"], b.inputs["Base Color"])
    nt.links.new(b.outputs[0], out.inputs["Surface"])
    return m


def mat_emit(name, color, strength=1.0):
    """additive light material (Transparent + Emission): at strength 0 the geometry disappears, so an
    unlit laser never shows up as a black stick. Returns (material, emission node); Strength and Color
    are keyframed later."""
    m, nt, out = _nodes(name)
    e = nt.nodes.new("ShaderNodeEmission")
    e.name = "Emission"
    e.inputs["Color"].default_value = (*color, 1)
    e.inputs["Strength"].default_value = strength
    t = nt.nodes.new("ShaderNodeBsdfTransparent")
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(t.outputs[0], add.inputs[0])
    nt.links.new(e.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
        try:
            setattr(m, attr, val)
        except Exception:
            pass
    try:
        m.cycles.emission_sampling = "NONE"      # glow comes from bloom; real spill lights do the lighting
    except Exception:
        pass
    return m, e


def mat_volume(name, density):
    m, nt, out = _nodes(name)
    v = nt.nodes.new("ShaderNodeVolumeScatter")
    v.inputs["Density"].default_value = density
    v.inputs["Anisotropy"].default_value = 0.35
    nt.links.new(v.outputs[0], out.inputs["Volume"])
    try:
        m.cycles.homogeneous_volume = True
    except Exception:
        pass
    return m

# ----------------------------------------------------------------------------------------------
# set
# ----------------------------------------------------------------------------------------------
BOOK_PALETTE = np.array([
    (0.20, 0.03, 0.03), (0.28, 0.05, 0.04), (0.03, 0.10, 0.07), (0.02, 0.05, 0.14), (0.25, 0.16, 0.05),
    (0.10, 0.07, 0.04), (0.33, 0.27, 0.18), (0.05, 0.05, 0.06), (0.18, 0.10, 0.04), (0.40, 0.35, 0.28),
])
WOOD = (0.035, 0.02, 0.012)


def shelf_run(length, height, row_h=0.37, depth=0.22):
    """books of one bookcase face in local coords: u along the shelf, v = depth (0 at the front), w up"""
    cs, ss, cols = [], [], []
    rows = int(height / row_h)
    for r in range(rows):
        u = 0.04
        while u < length - 0.06:
            if rng.random() < 0.05:            # a gap
                u += rng.uniform(0.08, 0.3); continue
            th = rng.uniform(0.028, 0.075)
            hh = row_h * rng.uniform(0.62, 0.92)
            dd = depth * rng.uniform(0.75, 1.0)
            cs.append((u + th / 2, dd / 2, r * row_h + 0.03 + hh / 2))
            ss.append((th * 0.93, dd, hh))
            c = BOOK_PALETTE[rng.randrange(len(BOOK_PALETTE))] * rng.uniform(0.6, 1.3)
            cols.append(c)
            u += th
    return np.array(cs), np.array(ss), np.array(cols), rows


def build_set(c_set, mats):
    # floor: black, glossy, slightly uneven so reflections break up
    bm = bmesh.new()
    slab(bm, (0, 0, -0.05), (60, 60, 0.1))
    bm_obj(bm, "FLOOR", c_set, mats["floor"])
    bm = bmesh.new()
    slab(bm, (0, 0, CEIL_Z + 0.05), (60, 60, 0.1))
    bm_obj(bm, "CEILING", c_set, mats["dark"])
    bm = bmesh.new()
    slab(bm, (0, BACK_Y + 0.5, CEIL_Z / 2), (60, 0.2, CEIL_Z))
    bm_obj(bm, "BACK_WALL", c_set, mats["dark"])

    # columns
    col_x = [(i - 2.5) * BAY for i in range(6)]
    for i, x in enumerate(col_x):
        build_column(c_set, f"COLUMN_{i + 1}", x, mats)

    # bookcases: the back wall + library stacks receding behind every column (aisles)
    C, S, K = [], [], []
    def add(cs, ss, cols):
        C.append(cs); S.append(ss); K.append(cols)
    # back wall, books face -Y
    L = 30.0
    cs, ss, cols, rows = shelf_run(L, CEIL_Z - 0.2)
    add(np.stack([cs[:, 0] - L / 2, BACK_Y - cs[:, 1], cs[:, 2]], 1), ss, cols)
    for r in range(rows + 1):
        add(np.array([[0, BACK_Y - 0.13, r * 0.37 + 0.012]]), np.array([[L, 0.28, 0.024]]), np.array([WOOD]))
    # stacks
    y0, y1, h, half = 2.6, BACK_Y - 0.4, 4.25, 0.26
    for x in col_x:
        for sgn in (-1, 1):
            cs, ss, cols, rows = shelf_run(y1 - y0, h)
            add(np.stack([x + sgn * (half - cs[:, 1]), y0 + cs[:, 0], cs[:, 2]], 1),
                np.stack([ss[:, 1], ss[:, 0], ss[:, 2]], 1), cols)
        frame_c = [[x, (y0 + y1) / 2, h / 2], [x, y0 - 0.03, h / 2], [x, (y0 + y1) / 2, h + 0.06]]
        frame_s = [[0.06, y1 - y0, h], [2 * half + 0.06, 0.06, h + 0.1], [2 * half + 0.1, y1 - y0 + 0.1, 0.12]]
        for r in range(rows + 1):
            frame_c.append([x, (y0 + y1) / 2, r * 0.37 + 0.012]); frame_s.append([2 * half, y1 - y0, 0.024])
        add(np.array(frame_c), np.array(frame_s), np.tile(WOOD, (len(frame_c), 1)))
    me = boxes_mesh("BOOKCASES", np.concatenate(C), np.concatenate(S), np.concatenate(K))
    me.materials.append(mats["books"])
    obj("BOOKCASES", me, c_set)

    # books lying on the floor
    n = 90
    cx = nrng.uniform(-8.5, 8.5, n); cy = nrng.uniform(-3.5, 2.2, n)
    sz = np.stack([nrng.uniform(0.2, 0.34, n), nrng.uniform(0.28, 0.44, n), nrng.uniform(0.04, 0.09, n)], 1)
    cols = BOOK_PALETTE[nrng.integers(0, len(BOOK_PALETTE), n)] * nrng.uniform(0.6, 1.3, (n, 1))
    me = boxes_mesh("FLOOR_BOOKS", np.stack([cx, cy, sz[:, 2] / 2], 1), sz, cols, rotz=nrng.uniform(0, 6.28, n))
    me.materials.append(mats["books"])
    obj("FLOOR_BOOKS", me, c_set)

    # haze
    if HAZE_DENSITY > 0:
        bm = bmesh.new()
        slab(bm, (0, -1.5, CEIL_Z / 2), (34, 30, CEIL_Z - 0.02))
        hz = bm_obj(bm, "HAZE", c_set, mats["haze"])
        hz.display_type = "WIRE"
    return col_x


def build_column(c_set, name, x, mats, h=CEIL_Z, r=0.27):
    bm = bmesh.new()
    seg, flutes = 96, 24
    z0, z1 = 0.42, h - 0.5
    rings = 7
    ring_verts = []
    for j in range(rings):
        t = j / (rings - 1)
        rz = r * (1.0 - 0.13 * t * t)
        vs = []
        for i in range(seg):
            a = 2 * pi * i / seg
            rr = rz * (1.0 - 0.075 * abs(sin(flutes * a / 2)) ** 0.6)
            vs.append(bm.verts.new((rr * cos(a), rr * sin(a), z0 + (z1 - z0) * t)))
        ring_verts.append(vs)
    for j in range(rings - 1):
        for i in range(seg):
            a, b = ring_verts[j], ring_verts[j + 1]
            bm.faces.new((a[i], a[(i + 1) % seg], b[(i + 1) % seg], b[i]))
    # base
    slab(bm, (0, 0, 0.09), (r * 2.9, r * 2.9, 0.18))
    limb(bm, (0, 0, 0.18), (0, 0, 0.30), r * 1.32, r * 1.32, seg=32)
    limb(bm, (0, 0, 0.30), (0, 0, 0.42), r * 1.22, r * 1.02, seg=32)
    # ionic capital
    limb(bm, (0, 0, z1), (0, 0, z1 + 0.14), r * 0.9, r * 1.12, seg=32)
    for sx in (-1, 1):
        limb(bm, (sx * (r * 1.08), -r * 1.05, z1 + 0.2), (sx * (r * 1.08), r * 1.05, z1 + 0.2), 0.17, 0.17, seg=20)
    slab(bm, (0, 0, z1 + 0.25), (r * 2.4, r * 2.1, 0.2))
    slab(bm, (0, 0, z1 + 0.42), (r * 3.2, r * 2.7, 0.14))
    o = bm_obj(bm, name, c_set, mats["marble"], loc=(x, 0, 0))
    # a cable / vine wrapped around the shaft (homage to the reference columns)
    cu = bpy.data.curves.new(name + "_CABLE", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 0.014
    sp = cu.splines.new("POLY")
    turns, pts = rng.uniform(2.5, 4.5), 120
    sp.points.add(pts - 1)
    ph = rng.uniform(0, 6.28)
    for i in range(pts):
        t = i / (pts - 1)
        a = ph + turns * 2 * pi * t
        rr = r * 1.06 + 0.05 * sin(t * 37.0)
        sp.points[i].co = (rr * cos(a), rr * sin(a), 0.2 + t * (h - 1.0), 1)
    cab = obj(name + "_CABLE", cu, c_set, loc=(x, 0, 0))
    cu.materials.append(mats["dark"])
    return o

# ----------------------------------------------------------------------------------------------
# proxy sculptures (replaced by the Tripo models later)
# ----------------------------------------------------------------------------------------------
def feather_wing(bm, root, side, lift=0.4, length=1.6, n=10, sweep=0.3):
    root = Vector(root)
    first_tip = None
    for i in range(n):
        t = i / (n - 1)
        ang = lift + radians(78) - radians(150) * t
        L = length * (0.5 + 0.5 * sin(pi * (0.12 + 0.8 * (1 - t))))
        tip = root + Vector((side * cos(ang) * L, sweep * L * (0.4 + 0.6 * t), sin(ang) * L))
        d = (tip - root).normalized()
        perp = d.cross(Vector((0, 1, 0))).normalized() * (0.11 + 0.04 * (1 - t))
        base = root + d * 0.15
        poly(bm, [base - perp * 0.4, base + perp * 0.4, tip + perp, tip - perp])
        if first_tip is None:
            first_tip = tip
    limb(bm, root, root + (first_tip - root) * 0.75, 0.06, 0.025, seg=6)


def bat_wing(bm, root, side, lift=0.3, size=1.4):
    root = Vector(root)
    def P(x, y, z):                      # a point of the wing, raised by `lift`, mirrored by `side`
        ca, sa = cos(lift), sin(lift)
        return root + Vector((side * (x * ca - z * sa), y, x * sa + z * ca))
    elbow = P(0.45 * size, 0.12, 0.42 * size)
    wrist = P(0.78 * size, 0.2, 0.78 * size)
    tips = [P(1.25 * size, 0.25, 0.95 * size), P(1.35 * size, 0.3, 0.35 * size),
            P(1.05 * size, 0.3, -0.25 * size), P(0.55 * size, 0.25, -0.5 * size)]
    limb(bm, root, elbow, 0.05, 0.04, seg=6)
    limb(bm, elbow, wrist, 0.04, 0.03, seg=6)
    for tp in tips:
        limb(bm, wrist, tp, 0.022, 0.008, seg=5)
    chain = tips + [root + Vector((0, 0.1, -0.35 * size))]
    for a, b in zip(chain[:-1], chain[1:]):
        mid = wrist + ((a + b) / 2 - wrist) * 0.7
        poly(bm, [wrist, a, mid, b])
    poly(bm, [root, elbow, wrist, chain[-1]])


def robe_body(bm, base_z=0.0):
    s = len(bm.verts)
    g = limb(bm, (0, 0, base_z), (0, 0, base_z + 1.02), 0.36, 0.17, seg=18)
    limb(bm, (0, 0, base_z + 0.95), (0, 0, base_z + 1.47), 0.17, 0.2, seg=12)
    ball(bm, (0, 0, base_z + 1.46), 0.2, (1.3, 0.72, 0.6))
    limb(bm, (0, 0, base_z + 1.5), (0, 0, base_z + 1.62), 0.055, 0.05, seg=8)
    ball(bm, (0, 0.0, base_z + 1.7), 0.115, (0.92, 1.0, 1.12))
    return s


def arm(bm, sh, el, ha):
    limb(bm, sh, el, 0.06, 0.05, seg=8)
    limb(bm, el, ha, 0.05, 0.04, seg=8)
    ball(bm, ha, 0.055)


def open_book(bm, c, w=1.7, d=1.2, t=0.3, rz=0.0, tilt=(0, 0, 0)):
    s = len(bm.verts)
    for sx in (-1, 1):
        slab(bm, (sx * w / 4, 0, t * 0.55), (w / 2 * 0.985, d, t), rot=(0, -sx * radians(8), 0))
    slab(bm, (0, 0, 0.03), (w * 1.05, d * 1.05, 0.05))
    limb(bm, (0, -d / 2, t * 0.3), (0, d / 2, t * 0.3), 0.07, 0.07, seg=8)
    xform_since(bm, s, Matrix.Translation(Vector(c)) @ Euler((tilt[0], tilt[1], rz)).to_matrix().to_4x4())


def pedestal(bm, big=1.0):
    """two giant tomes and an open book on top. returns the height of the standing surface"""
    slab(bm, (0.05, 0.0, 0.14), (1.75 * big, 1.25 * big, 0.28), rot=(0, 0, radians(7)))
    slab(bm, (-0.04, 0.03, 0.40), (1.6 * big, 1.15 * big, 0.24), rot=(0, 0, radians(-9)))
    open_book(bm, (0, 0, 0.52), w=1.8 * big, d=1.2 * big, t=0.26)
    return 0.80


def build_figure(kind):
    bm = bmesh.new()
    top = pedestal(bm, 1.15 if kind == "michael" else 1.0)
    s = len(bm.verts)
    if kind == "michael":
        # archangel, sword raised overhead with both hands, wings fully spread, the dragon under his feet
        limb(bm, (-0.75, 0.05, 0.14), (0.25, -0.12, 0.2), 0.11, 0.17, seg=10)
        limb(bm, (0.25, -0.12, 0.2), (0.72, -0.3, 0.3), 0.17, 0.12, seg=10)
        ball(bm, (0.86, -0.36, 0.36), 0.15, (1.3, 0.9, 0.8))
        limb(bm, (0.84, -0.3, 0.45), (0.98, -0.18, 0.72), 0.03, 0.004, seg=5)
        limb(bm, (0.9, -0.42, 0.45), (1.08, -0.5, 0.68), 0.03, 0.004, seg=5)
        robe_body(bm, 0.28)
        z = 0.28
        arm(bm, (0.25, 0, z + 1.46), (0.23, -0.06, z + 1.8), (0.05, -0.08, z + 2.04))
        arm(bm, (-0.25, 0, z + 1.46), (-0.23, -0.06, z + 1.8), (-0.05, -0.08, z + 2.04))
        slab(bm, (0, -0.08, z + 2.62), (0.075, 0.02, 1.1))
        slab(bm, (0, -0.08, z + 2.08), (0.36, 0.04, 0.05))
        for sd in (-1, 1):
            feather_wing(bm, (sd * 0.12, 0.16, z + 1.38), sd, lift=radians(24), length=1.95, n=12, sweep=0.22)
        sc = 1.12
    elif kind == "trumpet":
        robe_body(bm)
        arm(bm, (0.25, 0, 1.46), (0.42, -0.12, 1.5), (0.36, -0.2, 1.68))
        arm(bm, (-0.25, 0, 1.46), (-0.4, 0.05, 1.15), (-0.5, -0.05, 0.9))
        limb(bm, (0.08, -0.12, 1.68), (1.0, -0.42, 2.28), 0.014, 0.022, seg=8)
        limb(bm, (1.0, -0.42, 2.28), (1.12, -0.46, 2.36), 0.022, 0.13, seg=12)
        for sd in (-1, 1):
            feather_wing(bm, (sd * 0.12, 0.16, 1.38), sd, lift=radians(8 if sd > 0 else 30), length=1.55, sweep=0.5)
        sc = 1.12
    elif kind == "spear":
        robe_body(bm)
        limb(bm, (-0.62, -0.1, 2.35), (0.95, -0.3, 0.45), 0.018, 0.018, seg=6)
        limb(bm, (0.95, -0.3, 0.45), (1.1, -0.32, 0.27), 0.045, 0.002, seg=6)
        arm(bm, (0.25, 0, 1.46), (0.45, -0.18, 1.3), (0.42, -0.22, 1.08))
        arm(bm, (-0.25, 0, 1.46), (-0.38, -0.1, 1.75), (-0.3, -0.14, 1.97))
        ball(bm, (-0.42, -0.3, 1.2), 0.33, (1, 0.16, 1))
        for sd in (-1, 1):
            feather_wing(bm, (sd * 0.12, 0.16, 1.38), sd, lift=radians(34), length=1.6, sweep=0.35)
        sc = 1.12
    elif kind == "demon":
        # crawling out of the open book: hunched torso, clawed arm reaching toward the centre, bat wings, horns
        limb(bm, (0, 0.05, -0.05), (0.12, -0.15, 0.62), 0.2, 0.25, seg=10)
        ball(bm, (0.14, -0.17, 0.66), 0.24, (1.25, 0.8, 0.75))
        ball(bm, (0.24, -0.32, 0.9), 0.13, (0.95, 1.05, 1.1))
        for sd in (-1, 1):
            limb(bm, (0.24 + sd * 0.08, -0.3, 0.98), (0.24 + sd * 0.22, -0.26, 1.16), 0.035, 0.022, seg=6)
            limb(bm, (0.24 + sd * 0.22, -0.26, 1.16), (0.24 + sd * 0.2, -0.36, 1.36), 0.022, 0.003, seg=6)
        arm(bm, (0.38, -0.15, 0.7), (0.62, -0.32, 1.0), (0.88, -0.4, 1.42))
        for a in (-0.5, 0.0, 0.5):
            limb(bm, (0.88, -0.4, 1.42), (0.96 + 0.07 * a, -0.44, 1.6 - 0.05 * abs(a)), 0.014, 0.002, seg=4)
        arm(bm, (-0.1, -0.15, 0.68), (-0.42, -0.35, 0.42), (-0.62, -0.5, 0.12))
        bat_wing(bm, (0.26, 0.12, 0.62), 1, lift=radians(28), size=1.3)
        bat_wing(bm, (-0.02, 0.12, 0.62), -1, lift=radians(10), size=1.3)
        tail = [(-0.1, 0.25, 0.05), (-0.45, 0.4, 0.2), (-0.75, 0.3, 0.55), (-0.8, 0.1, 0.9)]
        for a, b, r in zip(tail[:-1], tail[1:], (0.06, 0.04, 0.025)):
            limb(bm, a, b, r, r * 0.6, seg=6)
        sc = 1.2
    else:   # lucifer: the fallen angel, thrown backwards, one feathered wing, one bat wing, shielding his face
        s2 = len(bm.verts)
        limb(bm, (0, 0, 0), (0, 0, 0.95), 0.17, 0.17, seg=10)
        limb(bm, (0, 0, 0.95), (0, 0, 1.47), 0.17, 0.2, seg=12)
        ball(bm, (0, 0, 1.46), 0.2, (1.3, 0.72, 0.6))
        ball(bm, (0, 0.0, 1.7), 0.115, (0.92, 1.0, 1.12))
        for sd in (-1, 1):
            limb(bm, (sd * 0.05, -0.04, 1.8), (sd * 0.16, -0.02, 1.98), 0.028, 0.003, seg=5)
        arm(bm, (-0.25, 0, 1.46), (-0.42, -0.2, 1.58), (-0.16, -0.26, 1.72))
        arm(bm, (0.25, 0, 1.46), (0.52, 0.05, 1.2), (0.75, -0.05, 1.02))
        feather_wing(bm, (0.12, 0.16, 1.38), 1, lift=radians(-22), length=1.5, sweep=0.5)
        bat_wing(bm, (-0.12, 0.16, 1.3), -1, lift=radians(32), size=1.35)
        xform_since(bm, s2, Matrix.Rotation(radians(20), 4, "Y"))
        slab(bm, (0.2, -0.45, 0.02), (0.07, 0.02, 0.8), rot=(radians(86), 0, radians(40)))
        sc = 1.15
    xform_since(bm, s, Matrix.Translation((0, 0, top)) @ Matrix.Scale(sc, 4))
    return bm


def build_slots(c_slots, c_proxy, mats):
    slots = []
    for sd in SLOTS:
        x = (sd["n"] - 3) * BAY
        e = bpy.data.objects.new(f"SLOT_{sd['n']}", None)
        c_slots.objects.link(e)
        e.empty_display_type = "ARROWS"
        e.empty_display_size = 0.6
        e.location = (x, 0.5, 0)
        e["asset"] = sd["asset"]
        e["target_height"] = sd["height"]
        e["side"] = sd["side"]
        bm = build_figure(sd["kind"])
        mat = mats["obsidian"] if sd["side"] == "hell" else mats["marble"]
        p = bm_obj(bm, f"PROXY_{sd['n']}_{sd['kind']}", c_proxy, mat)
        p.parent = e
        slots.append(e)
    return slots


def build_flying(c_books, mats):
    """a frozen whirl of open books and loose pages above the sculptures"""
    books = []
    for i in range(16):
        bm = bmesh.new()
        open_book(bm, (0, 0, 0), w=rng.uniform(0.4, 0.62), d=rng.uniform(0.3, 0.42), t=0.07)
        o = bm_obj(bm, f"FLYBOOK_{i:02d}", c_books, mats["paper"])
        a = rng.uniform(0, 6.28)
        rad = rng.uniform(1.0, 7.5)
        o.location = (rad * cos(a), rng.uniform(-1.6, 4.5), rng.uniform(2.6, 4.5))
        o.rotation_euler = (rng.uniform(-1.2, 1.2), rng.uniform(-1.2, 1.2), rng.uniform(0, 6.28))
        books.append(o)
    bm = bmesh.new()
    for i in range(140):
        w, h = 0.21, 0.3
        s = len(bm.verts)
        poly(bm, [(-w / 2, -h / 2, 0), (w / 2, -h / 2, 0.02), (w / 2, h / 2, 0), (-w / 2, h / 2, 0.03)])
        # pages spiral up out of the five open books
        slot = rng.randrange(5)
        t = rng.random()
        a = t * 9.0 + slot
        rad = 0.3 + 1.3 * t
        loc = Vector(((slot - 2) * BAY + rad * cos(a), 0.4 + rad * sin(a) * 0.8, 1.2 + 3.4 * t))
        xform_since(bm, s, Matrix.Translation(loc) @ Euler((rng.uniform(-1.5, 1.5), rng.uniform(-1.5, 1.5), rng.uniform(0, 6.28))).to_matrix().to_4x4())
    bm_obj(bm, "PAGES", c_books, mats["paper"])
    return books

# ----------------------------------------------------------------------------------------------
# lasers
# ----------------------------------------------------------------------------------------------
def beams_obj(name, c, segments, mat, r=0.012, loc=(0, 0, 0)):
    bm = bmesh.new()
    for p0, p1 in segments:
        limb(bm, p0, p1, r, r, seg=5)
    o = bm_obj(bm, name, c, mat, loc=loc)
    no_gi(o)
    return o


def build_grid(c_set):
    """ceiling grid of light tubes, split in 6 flicker groups (the reference's blue ceiling)"""
    xs = [(-7 + i) * BAY / 2 for i in range(15)]
    ys = [-1.0 + j * 1.0 for j in range(int(BACK_Y) + 1)]
    z = CEIL_Z - 0.13
    groups = [[] for _ in range(6)]
    for j, y in enumerate(ys):
        for i in range(len(xs) - 1):
            if rng.random() < 0.26:
                continue
            a, b = xs[i], xs[i + 1]
            if rng.random() < 0.25:                      # glitchy half tubes
                b = a + (b - a) * rng.uniform(0.3, 0.7)
            groups[rng.randrange(6)].append(((a, y, z), (b, y, z)))
    for i, x in enumerate(xs):
        for j in range(len(ys) - 1):
            if rng.random() < 0.3:
                continue
            groups[rng.randrange(6)].append(((x, ys[j], z), (x, ys[j + 1], z)))
    for _ in range(12):                                  # a few fallen, diagonal tubes
        x, y = rng.uniform(-8, 8), rng.uniform(0, BACK_Y - 2)
        groups[rng.randrange(6)].append(((x, y, z), (x + rng.uniform(-1.6, 1.6), y + rng.uniform(0.3, 1.2), z - rng.uniform(0.1, 0.7))))
    out = []
    for g, segs in enumerate(groups):
        m, e = mat_emit(f"GRID_{g}", COL_GRID, 3.4)
        beams_obj(f"GRID_{g}", c_set, segs, m, r=0.02)
        out.append(e)
    return out


def build_lasers(c_las, col_x):
    L = {}
    # L2 heaven curtain: vertical beams behind the sculptures, two interleaved groups
    xs = np.arange(-6.84, 6.85, 0.36)                     # 39 beams
    for g in (0, 1):
        m, e = mat_emit(f"CURTAIN_{'AB'[g]}", COL_HEAVEN, 0.0)
        segs = [((x, 1.7, 0.0), (x, 1.7, CEIL_Z - 0.15)) for x in xs[g::2]]
        beams_obj(f"LASER_CURTAIN_{'AB'[g]}", c_las, segs, m, r=0.010)
        L[f"curtain{g}"] = e
    # L3 fans: a head above every column, in a plane BEHIND the sculptures, scissoring blue beams
    #          across the aisles. Lasers stay behind the figures so they frame them instead of hiding them.
    L["fans"] = []
    for g in (0, 1):
        m, e = mat_emit(f"FAN_{'AB'[g]}", COL_FAN, 0.0)
        L[f"fan{g}"] = e
        for i, x in enumerate(col_x):
            if i % 2 != g:
                continue
            segs = []
            for a in (-44, -22, 0, 22, 44):
                d = Vector((sin(radians(a)), 0, -cos(radians(a))))
                segs.append(((0, 0, 0), tuple(d * 8.5)))
            o = beams_obj(f"LASER_FAN_{i + 1}", c_las, segs, m, r=0.012, loc=(x, 2.1, CEIL_Z - 0.3))
            L["fans"].append(o)
    # L4 hell: red beams bursting upward from behind the two outer (demon) books
    L["hells"] = []
    m, e = mat_emit("HELL", COL_HELL, 0.0)
    L["hell"] = e
    for x in (-2 * BAY, 2 * BAY):
        segs = []
        n, spread = 9, 56
        for k in range(n):
            a = radians(-spread + 2 * spread * k / (n - 1))
            d = Vector((sin(a), 0, cos(a)))
            segs.append(((0, 0, 0), tuple(d * 7.0)))
        o = beams_obj(f"LASER_HELL_{len(L['hells']) + 1}", c_las, segs, m, r=0.012, loc=(x, 1.35, 0.25))
        L["hells"].append(o)
    # L5 halo: a rotating sunburst mandala behind the archangel's head
    m, e = mat_emit("HALO", COL_HEAVEN, 0.0)
    L["halo"] = e
    segs = []
    for k in range(24):
        a = 2 * pi * k / 24
        r0, r1 = 0.75, (3.3 if k % 2 == 0 else 2.1)
        d = Vector((cos(a), 0, sin(a)))
        segs.append((tuple(d * r0), tuple(d * r1)))
    for rad in (0.68, 1.05):
        for k in range(48):
            a0, a1 = 2 * pi * k / 48, 2 * pi * (k + 1) / 48
            segs.append(((rad * cos(a0), 0, rad * sin(a0)), (rad * cos(a1), 0, rad * sin(a1))))
    L["halo_obj"] = beams_obj("LASER_HALO", c_las, segs, m, r=0.012, loc=(0, 1.15, 3.2))
    # L6 scanner: a horizontal sheet of light descending through the haze
    m, e = mat_emit("SCANNER", COL_HEAVEN, 0.0)
    L["scan"] = e
    bm = bmesh.new()
    slab(bm, (0, 0.6, 0), (17, 1.8, 0.004))      # a thin slice through the sculpture plane
    o = bm_obj(bm, "LASER_SCANNER", c_las, m, loc=(0, 0, 4.6))
    no_gi(o)
    L["scan_obj"] = o
    return L

# ----------------------------------------------------------------------------------------------
# lights
# ----------------------------------------------------------------------------------------------
def light(name, kind, c, loc, energy=0.0, color=(1, 1, 1), target=None, **kw):
    d = bpy.data.lights.new(name, kind)
    d.energy = energy
    d.color = color
    for k, v in kw.items():
        try:
            setattr(d, k, v)
        except Exception:
            pass
    o = obj(name, d, c, loc)
    if target is not None:
        o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o


def build_hero_rig(c_rig):
    R = {"keys": []}
    for sd in SLOTS:
        x = (sd["n"] - 3) * BAY
        # footlights: the reference lights its statues from the floor in front (hot skirts, dark heads)
        k = light(f"KEY_{sd['n']}", "SPOT", c_rig, (x, -2.6, 0.12), target=(x, 0.6, 2.3),
                  color=COL_KEY, spot_size=radians(58), spot_blend=1.0, shadow_soft_size=0.06)
        R["keys"].append(k)
    R["red"] = [light(f"SPILL_HELL_{i + 1}", "POINT", c_rig, (x, 1.3, 0.7), color=COL_HELL, shadow_soft_size=0.3)
                for i, x in enumerate((-2 * BAY, 2 * BAY))]   # placed behind the demons: red rim light
    R["cyan"] = light("SPILL_HEAVEN", "AREA", c_rig, (0, 1.2, CEIL_Z - 0.3), target=(0, 0.6, 0),
                      color=COL_HEAVEN, size=9.0, shape="RECTANGLE", size_y=2.0)
    R["halo"] = light("SPILL_HALO", "POINT", c_rig, (0, 1.6, 3.3), color=COL_HEAVEN, shadow_soft_size=0.5)
    # the blue the ceiling grid "casts": one wash over the aisles, one on the back wall, so that unlit
    # sculptures read as black silhouettes against blue shelves (as in the reference)
    R["wash"] = [light("WASH_BLUE_AISLES", "AREA", c_rig, (0, 6.5, CEIL_Z - 0.2), target=(0, 6.5, 0),
                       color=COL_GRID, size=22.0, shape="RECTANGLE", size_y=10.0),
                 light("WASH_BLUE_BACK", "AREA", c_rig, (0, 7.5, 2.6), target=(0, BACK_Y, 2.4),
                       color=COL_GRID, size=24.0, shape="RECTANGLE", size_y=3.5)]
    return R


def build_top_rig(c_rig):
    T = {}
    tgt = bpy.data.objects.new("SCAN_TARGET", None)
    c_rig.objects.link(tgt)
    tgt.location = (0, 0.4, 2.6)
    sp = light("SCAN_SPOT", "SPOT", c_rig, (0, -9.0, CEIL_Z - 0.35), color=(1, 1, 1), spot_size=radians(22),
               spot_blend=0.5, shadow_soft_size=0.1)
    con = sp.constraints.new("TRACK_TO")
    con.target = tgt
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    T["spot"], T["target"] = sp, tgt
    T["fill"] = light("TOP_FILL", "AREA", c_rig, (0, 6.5, CEIL_Z - 0.2), target=(0, 6.5, 0),
                      color=(0.55, 0.65, 0.85), size=22.0, shape="RECTANGLE", size_y=10.0)
    return T

# ----------------------------------------------------------------------------------------------
# title
# ----------------------------------------------------------------------------------------------
def build_title(c_title, cam):
    font = None
    if os.path.exists(FONT):
        try:
            font = bpy.data.fonts.load(FONT)
        except Exception:
            font = None
    cu = bpy.data.curves.new("TITLE_SRC", "FONT")
    cu.body = "\n".join(TITLE_LINES)
    cu.align_x = "CENTER"
    cu.size = 1.0
    cu.space_character = 1.45
    cu.space_line = 1.25
    if font:
        cu.font = font
    tmp = obj("TITLE_SRC", cu, c_title)
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    bpy.data.objects.remove(tmp, do_unlink=True)
    bpy.data.curves.remove(cu)
    # every letter is one mesh island -> random flicker group
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    seen = set()
    for f in bm.faces:
        if f.index in seen:
            continue
        g = rng.randrange(6)
        stack = [f]
        seen.add(f.index)
        while stack:
            q = stack.pop()
            q.material_index = g
            for e in q.edges:
                for o in e.link_faces:
                    if o.index not in seen:
                        seen.add(o.index); stack.append(o)
    xs = [v.co.x for v in bm.verts]
    width = max(xs) - min(xs)
    bm.to_mesh(me)
    bm.free()
    nodes = []
    for g in range(6):
        m, e = mat_emit(f"TITLE_{g}", (1, 1, 1), 1.6)
        me.materials.append(m)
        nodes.append(e)
    o = obj("TITLE", me, c_title)
    no_gi(o)
    o.parent = cam
    dist = 2.0
    half_w = dist * (36.0 / 2) / CAM_LENS
    half_h = half_w * RES[1] / RES[0]
    s = (2 * half_w * 0.27) / width
    o.scale = (s, s, s)
    o.location = (0, -half_h * 0.66, -dist)
    return nodes

# ----------------------------------------------------------------------------------------------
# cue sheet
# ----------------------------------------------------------------------------------------------
def animate_hero(R, L, grid, title, books):
    keys = {s["n"]: Chan() for s in SLOTS}
    kcol = {s["n"]: np.tile(np.array(COL_KEY), (N, 1)) for s in SLOTS}
    C, I, O, ALL = [3], [2, 4], [1, 5], [1, 2, 3, 4, 5]
    curtain = [Chan(), Chan()]
    fan = [Chan(), Chan()]
    hell, halo, scan = Chan(), Chan(), Chan()
    wash = Chan(1.0)
    gridc = [Chan(1.0) for _ in grid]

    def strobe(slots, k, peak=1.0, dur=9, tau=5.0, color=None):
        f = bf(k)
        for s in slots:
            keys[s].hit(f, peak, dur, tau)
            if color is not None:
                for i in range(dur):
                    kcol[s][(f - 1 + i) % N] = color

    def ripple(k, laser=False, gain=1.0):
        """the reference's cycle: centre -> inner pair (+0.5 beat) -> outer pair (+1.5 beat)"""
        strobe(C, k, 1.0 * gain); strobe(I, k + 0.5, 0.9 * gain); strobe(C, k + 0.5, 0.42 * gain)
        strobe(O, k + 1.5, 0.85 * gain)
        if laser:
            halo.hit(bf(k), 1.0, 13, 7.0)
            curtain[0].hit(bf(k), 0.8, 10, 6.0); curtain[1].hit(bf(k + 0.5), 0.6, 10, 6.0)
            fan[0].hit(bf(k + 0.5), 1.0, 12, 6.0); fan[1].hit(bf(k + 1.0), 0.7, 10, 6.0)
            hell.hit(bf(k + 1.5), 1.0, 11, 5.0)

    # BAR 1 (beats 0-3)  HOMAGE: the reference, exactly — white ripple, blue grid, nothing else
    ripple(0); ripple(2)
    # BAR 2 (beats 4-7)  THE BOOKS OPEN: same ripple, the lasers wake up one family at a time
    ripple(4, laser=True); ripple(6, laser=True)
    curtain[0].hold(bf(4), bf(8), 0.12); curtain[1].hold(bf(5), bf(8), 0.12)
    # BAR 3 (beats 8-11)  STANDOFF: heaven on the beat, hell on the off-beat; roll into the drop
    fan[0].hold(bf(8), bf(11.7), 0.45); fan[1].hold(bf(8), bf(11.7), 0.45)
    halo.hold(bf(8), bf(11.7), 0.35)
    for k in (8, 9, 10):
        strobe(C + I, k, 0.85, 6, 3.5); curtain[k % 2].hit(bf(k), 1.0, 7, 4.0)
        strobe(O, k + 0.5, 0.85, 6, 3.5, color=(1.0, 0.16, 0.10)); hell.hit(bf(k + 0.5), 1.0, 7, 4.0)
    for j in range(3):
        strobe(ALL, 11 + j * 0.25, 1.0, 3, 2.0); curtain[j % 2].hit(bf(11 + j * 0.25), 1.0, 3, 2.0)
        hell.hit(bf(11 + j * 0.25), 1.0, 3, 2.0)
    # BAR 4 (beats 12-15)  WAR IN HEAVEN: full hits on every kick, red/blue split on the off-beats
    for b, k in enumerate((12, 13, 14, 15)):
        strobe(ALL, k, 1.25, 8, 4.5)
        halo.hit(bf(k), 1.4, 13, 8.0)
        curtain[0].hit(bf(k), 1.0, 6, 3.5); curtain[1].hit(bf(k + 0.5), 1.0, 6, 3.5)
        fan[b % 2].hit(bf(k), 1.3, 12, 6.0); fan[(b + 1) % 2].hit(bf(k + 0.5), 1.3, 12, 6.0)
        hell.hit(bf(k + 0.5), 1.3, 9, 5.0)
        left, right = ((1.0, 0.08, 0.05), (0.10, 0.35, 1.0)) if b % 2 == 0 else ((0.10, 0.35, 1.0), (1.0, 0.08, 0.05))
        strobe([1, 2], k + 0.5, 0.9, 5, 3.0, color=left); strobe([4, 5], k + 0.5, 0.9, 5, 3.0, color=right)
    halo.hold(bf(12), bf(16), 0.5); fan[0].hold(bf(12), bf(16), 0.35); fan[1].hold(bf(12), bf(16), 0.35)
    # BAR 5 (beats 16-19)  JUDGEMENT: hell answers first, heaven lands the last word; the scanner descends
    for k in (16, 18):
        strobe(O, k, 0.9, 8, 4.5, color=(1.0, 0.12, 0.06)); hell.hit(bf(k), 1.2, 10, 5.0)
        strobe(I, k + 0.5, 1.0, 8, 4.5); fan[0].hit(bf(k + 0.5), 1.0, 10, 5.0); fan[1].hit(bf(k + 0.5), 1.0, 10, 5.0)
        strobe(C, k + 1, 1.3, 11, 6.0); halo.hit(bf(k + 1), 1.5, 13, 8.0)
        curtain[0].hit(bf(k + 1), 1.0, 8, 4.0); curtain[1].hit(bf(k + 1.5), 1.0, 8, 4.0)
    scan.hold(bf(16), bf(20), 1.0)
    halo.hold(bf(16), bf(20), 0.4)
    for j in range(8):                                    # curtain shimmer in 16ths before the last hit
        curtain[j % 2].hit(bf(19 + j * 0.125), 0.9, 2, 2.0)
    # BAR 6 (beats 20-21 + tail)  RESOLVE: one enormous hit, the ripple runs outward and dies into black
    strobe(ALL, 20, 1.5, 12, 6.0); halo.hit(bf(20), 1.8, 16, 9.0); hell.hit(bf(20), 1.0, 8, 4.0)
    curtain[0].hit(bf(20), 1.2, 12, 6.0); curtain[1].hit(bf(20), 1.2, 12, 6.0)
    fan[0].hit(bf(20), 1.4, 12, 6.0); fan[1].hit(bf(20), 1.4, 12, 6.0)
    strobe(I, 20.5, 0.8, 8); strobe(O, 21, 0.7, 7, 4.0)

    # pre-drop blackout: 3 frames of nothing right before beat 12
    blk0, blk1 = bf(12) - 3, bf(12)
    for ch in list(keys.values()) + curtain + fan + [hell, halo, wash] + gridc:
        ch.hold(blk0, blk1, 0.0, mode="set")

    # ceiling grid: random tube groups drop out on 8th notes, flash on the drop, dim at the loop point
    r2 = random.Random(SEED + 1)
    k = 0.0
    while k < N_BEATS + 1:
        for g in gridc:
            if r2.random() < 0.22:
                g.mul(bf(k), bf(k + 0.5), r2.choice((0.0, 0.15, 0.4)))
        k += 0.5
    for kk in (12, 13, 14, 15, 20):
        for g in gridc:
            g.hit(bf(kk), 1.6, 6, 3.0)
    for g in gridc:
        g.hold(blk0, blk1, 0.0, mode="set")
        g.mul(N - 5, N + 1, 0.5)
    wash.mul(N - 5, N + 1, 0.6)
    for kk in (12, 13, 14, 15, 20):
        wash.hit(bf(kk), 1.5, 6, 3.0)

    # ---- bake ---------------------------------------------------------------------------------
    KEY_W = 420.0
    for s in SLOTS:
        lt = R["keys"][s["n"] - 1].data
        keys[s["n"]].bake(lt, "energy", KEY_W * (1.25 if s["n"] == 3 else 1.0))
        col = kcol[s["n"]]
        for i in range(N):
            if i in (0, N - 1) or (col[i] != col[i - 1]).any() or (col[i] != col[(i + 1) % N]).any():
                lt.color = col[i]
                lt.keyframe_insert("color", frame=i + 1)
    def bake_node(ch, node, scale):
        ch.bake(node.inputs["Strength"], "default_value", scale)
    for g in (0, 1):
        bake_node(curtain[g], L[f"curtain{g}"], 6.0)
        bake_node(fan[g], L[f"fan{g}"], 9.0)
    bake_node(hell, L["hell"], 12.0)
    bake_node(halo, L["halo"], 9.0)
    bake_node(scan, L["scan"], 1.6)
    for ch, node in zip(gridc, grid):
        bake_node(ch, node, 3.4)
    hell.bake(R["red"][0].data, "energy", 260.0); hell.bake(R["red"][1].data, "energy", 260.0)
    cy = Chan(); cy.v = np.maximum(curtain[0].v, curtain[1].v)
    cy.bake(R["cyan"].data, "energy", 900.0)
    halo.bake(R["halo"].data, "energy", 320.0)
    wash.bake(R["wash"][0].data, "energy", 2200.0)
    wash.bake(R["wash"][1].data, "energy", 1400.0)

    # halo: rotation (lands on a multiple of 15 deg so the loop is seamless) and psychedelic hue steps
    speed = np.zeros(N)
    for f in range(1, N + 1):
        speed[f - 1] = 0.0 if f < bf(4) else 0.5 if f < bf(12) else 2.6 if f < bf(16) else 1.2 if f < bf(20) else 0.6
    total = speed.sum()
    speed *= (round(total / 15.0) * 15.0) / total
    ang = np.concatenate([[0.0], np.cumsum(speed)])
    ho = L["halo_obj"]
    for f in range(1, N + 2):
        ho.rotation_euler = (0, radians(ang[f - 1]), 0)
        ho.keyframe_insert("rotation_euler", index=1, frame=f)
    hues = {12: 0.52, 13: 0.84, 14: 0.12, 15: 0.66, 16: 0.76, 17: 0.52, 18: 0.92, 19: 0.52, 20: 0.52}
    def halo_rgb(f):
        cur = None
        for kk in sorted(hues):
            if f >= bf(kk):
                cur = hues[kk]
        if cur is None or f >= bf(20) + 6:
            return COL_HEAVEN
        return colorsys.hsv_to_rgb(cur, 0.92, 1.0)
    prev = None
    for f in range(1, N + 1):
        c = halo_rgb(f)
        nxt = halo_rgb(f + 1) if f < N else None
        if c != prev or c != nxt:
            for tgt, path in ((L["halo"].inputs["Color"], "default_value"),):
                tgt.default_value = (*c, 1)
                tgt.keyframe_insert(path, frame=f)
            R["halo"].data.color = c
            R["halo"].data.keyframe_insert("color", frame=f)
        prev = c
    # halo pulse (scale) on the drop
    sc = Chan(1.0)
    for kk in (12, 13, 14, 15, 17, 19, 20):
        sc.hit(bf(kk), 1.22, 8, 4.0)
    for f in range(1, N + 1):
        v = max(1.0, sc.v[f - 1])
        ho.scale = (v, v, v)
        ho.keyframe_insert("scale", frame=f)

    # fans sweep (whole number of cycles per loop), hell beams sway, scanner descends
    for i, o in enumerate(L["fans"]):
        for f in range(1, N + 2):
            ph = 2 * pi * (f - 1) / N
            o.rotation_euler = (radians(5) * sin(6 * ph + i), radians(17) * sin(5 * ph + i * 1.05), 0)
            o.keyframe_insert("rotation_euler", frame=f)
    for i, o in enumerate(L["hells"]):
        for f in range(1, N + 2):
            ph = 2 * pi * (f - 1) / N
            o.rotation_euler = (0, radians(11) * sin(11 * ph + i * 2.1), 0)
            o.keyframe_insert("rotation_euler", frame=f)
    so = L["scan_obj"]
    f0, f1 = bf(16), bf(20)
    for f in range(f0 - 1, f1 + 2):
        t = min(1.0, max(0.0, (f - f0) / (f1 - f0)))
        so.location = (0, 0, 4.7 - 4.3 * (t * t * (3 - 2 * t)))
        so.keyframe_insert("location", index=2, frame=f)

    # title: letters blink out in random groups (the reference's "BLENDER VISUAL PRESENTATION" glitch)
    r3 = random.Random(SEED + 2)
    for node in title:
        ch = Chan(1.0)
        f = 1
        while f <= N:
            d = r3.randint(2, 7)
            if r3.random() < 0.26:
                ch.hold(f, min(f + d, N + 1), 0.0, mode="set")
            f += d
        ch.bake(node.inputs["Strength"], "default_value", 1.6)

    # flying books drift, one or two whole cycles per loop
    for i, o in enumerate(books):
        base_loc, base_rot = o.location.copy(), o.rotation_euler.copy()
        n1, ph0 = 1 + i % 2, i * 0.9
        for f in range(1, N + 2, 5):
            ph = 2 * pi * (f - 1) / N
            o.location = base_loc + Vector((0, 0, 0.09 * sin(n1 * ph + ph0)))
            o.rotation_euler = (base_rot.x + 0.22 * sin(n1 * ph + ph0), base_rot.y + 0.18 * cos(n1 * ph + ph0), base_rot.z + 0.3 * sin(ph + ph0))
            o.keyframe_insert("location", frame=f)
            o.keyframe_insert("rotation_euler", frame=f)


def animate_top(T):
    """TOP scene: one white spot scans right to left every two beats (measured: sweep 0.73 s, cycle 1.07 s)"""
    en = Chan()
    tx = np.zeros(N)
    k = 0
    while k <= N_BEATS + 1:
        f0, f1 = bf(k), bf(k + 1.5)
        for f in range(f0, f1):
            t = (f - f0) / max(1, (f1 - f0 - 1))
            j = (f - 1) % N
            if f <= N:
                tx[j] = 8.2 - 16.4 * t
                en.v[j] = sin(pi * min(1.0, max(0.0, t))) ** 0.35
        k += 2
    en.bake(T["spot"].data, "energy", 5200.0)
    for f in range(1, N + 1):
        T["target"].location.x = tx[f - 1]
        T["target"].keyframe_insert("location", index=0, frame=f)
    T["fill"].data.energy = 1500.0

# ----------------------------------------------------------------------------------------------
# render / compositor / audio
# ----------------------------------------------------------------------------------------------
def eevee_id():
    ids = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    for cand in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        if cand in ids:
            return cand
    return "BLENDER_EEVEE"


def setup_render(sc, engine, quality):
    r = sc.render
    r.resolution_x, r.resolution_y = RES
    r.resolution_percentage = 50 if quality == "previz" else 100
    r.fps = FPS
    sc.frame_start, sc.frame_end = 1, N
    r.film_transparent = False
    r.image_settings.file_format = "PNG"
    r.use_motion_blur = False
    final = quality != "previz"
    if engine.upper() == "CYCLES":
        r.engine = "CYCLES"
        cy = sc.cycles
        cy.samples = 96 if final else 10
        cy.use_adaptive_sampling = True
        cy.adaptive_threshold = 0.03 if final else 0.1
        cy.use_denoising = True
        cy.max_bounces = 4 if final else 2
        cy.diffuse_bounces = 2 if final else 0
        cy.glossy_bounces = 2 if final else 1
        cy.transmission_bounces = 2 if final else 0
        cy.volume_bounces = 0
        cy.transparent_max_bounces = 24
        cy.caustics_reflective = False
        cy.caustics_refractive = False
        cy.sample_clamp_indirect = 4.0
        for attr, val in (("volume_step_rate", 2.0), ("volume_max_steps", 64), ("use_light_tree", True)):
            try:
                setattr(cy, attr, val)
            except Exception:
                pass
        try:
            r.use_persistent_data = True
        except Exception:
            pass
    else:
        r.engine = eevee_id()
        ee = sc.eevee
        for attr, val in (("taa_render_samples", 48 if final else 16), ("use_raytracing", True),
                          ("volumetric_tile_size", "4" if final else "8"), ("volumetric_samples", 96 if final else 48),
                          ("volumetric_start", 0.5), ("volumetric_end", 40.0),
                          ("use_volumetric_shadows", True), ("volumetric_shadow_samples", 16),
                          ("use_shadows", True), ("shadow_ray_count", 2), ("shadow_step_count", 6)):
            try:
                setattr(ee, attr, val)
            except Exception:
                pass
    vs = sc.view_settings
    for vt in ("AgX", "Filmic", "Standard"):
        try:
            vs.view_transform = vt
            break
        except Exception:
            continue
    for look in ("AgX - High Contrast", "High Contrast", "AgX - Medium High Contrast", "Medium High Contrast"):
        try:
            vs.look = look
            break
        except Exception:
            continue


def setup_compositor(sc, name, saturation=1.0):
    """bloom (essential for the look) + optional desaturation. Handles the 4.2 / 4.4 / 5.x node APIs."""
    try:
        if hasattr(sc, "compositing_node_group"):                       # 5.0+
            nt = bpy.data.node_groups.new(name, "CompositorNodeTree")
            nt.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
            sc.compositing_node_group = nt
            out = nt.nodes.new("NodeGroupOutput")
        else:
            sc.use_nodes = True
            nt = sc.node_tree
            nt.nodes.clear()
            out = nt.nodes.new("CompositorNodeComposite")
        rl = nt.nodes.new("CompositorNodeRLayers")
        try:
            rl.scene = sc
        except Exception:
            pass
        gl = nt.nodes.new("CompositorNodeGlare")
        if "Type" in gl.inputs:                                        # 4.4+: options are sockets
            for nm, val in (("Type", "Bloom"), ("Quality", "High"), ("Threshold", 1.0), ("Smoothness", 0.4),
                            ("Strength", 0.6), ("Saturation", 1.0), ("Size", 0.5)):
                try:
                    gl.inputs[nm].default_value = val
                except Exception:
                    pass
        else:                                                          # 4.2 / 4.3: options are properties
            for attr, val in (("glare_type", "BLOOM"), ("quality", "HIGH"), ("threshold", 1.0), ("size", 6), ("mix", -0.45)):
                try:
                    setattr(gl, attr, val)
                except Exception:
                    pass
        nt.links.new(rl.outputs["Image"], gl.inputs["Image"])
        last = gl.outputs["Image"]
        if saturation != 1.0:
            hs = nt.nodes.new("CompositorNodeHueSat")
            hs.inputs["Saturation"].default_value = saturation
            nt.links.new(last, hs.inputs["Image"])
            last = hs.outputs["Image"]
        nt.links.new(last, out.inputs[0])
        for i, n in enumerate((rl, gl, out)):
            n.location = (i * 260, 0)
        return True
    except Exception as ex:
        print("[build_scene] compositor not set up (%s) — add a Glare/Bloom node by hand" % ex)
        return False


def add_audio(sc):
    if not os.path.exists(AUDIO):
        print("[build_scene] no audio at", AUDIO)
        return
    se = sc.sequence_editor_create()
    strips = se.strips if hasattr(se, "strips") else se.sequences
    strips.new_sound("MUSIC", AUDIO, 1, 1)
    try:
        sc.sync_mode = "AUDIO_SYNC"
    except Exception:
        pass

# ----------------------------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------------------------
def main():
    prefs = bpy.context.preferences.edit
    old_interp = prefs.keyframe_new_interpolation_type
    prefs.keyframe_new_interpolation_type = "LINEAR"

    hero = purge()
    hero.name = "HERO"
    top = bpy.data.scenes.new("TOP")

    c_set = coll("SET", hero.collection)
    c_books = coll("BOOKS_FLYING", hero.collection)
    c_slots = coll("SLOTS", hero.collection)
    c_proxy = coll("PROXIES", c_slots)
    c_cam = coll("CAMERA", hero.collection)
    c_title = coll("TITLE", hero.collection)
    c_rig = coll("RIG_HERO", hero.collection)
    c_las = coll("LASERS", hero.collection)
    c_top = coll("RIG_TOP", top.collection)
    for c in (c_set, c_books, c_slots, c_cam, c_title):
        top.collection.children.link(c)

    mats = dict(
        marble=mat_principled("MARBLE", (0.80, 0.79, 0.76), rough=0.36, veins=(0.42, 0.42, 0.44), bump=0.04),
        obsidian=mat_principled("OBSIDIAN", (0.035, 0.03, 0.03), rough=0.22, veins=(0.5, 0.36, 0.12), bump=0.03),
        floor=mat_principled("FLOOR", (0.012, 0.013, 0.016), rough=0.14, bump=0.02),
        dark=mat_principled("DARK", (0.012, 0.012, 0.014), rough=0.7),
        paper=mat_principled("PAPER", (0.78, 0.74, 0.64), rough=0.6),
        books=mat_vertex_color("BOOKS", rough=0.5),
        haze=mat_volume("HAZE", HAZE_DENSITY),
    )

    col_x = build_set(c_set, mats)
    grid = build_grid(c_set)
    build_slots(c_slots, c_proxy, mats)
    books = build_flying(c_books, mats)

    cam_data = bpy.data.cameras.new("CAM")
    cam_data.lens = CAM_LENS
    cam_data.sensor_width = 36.0
    cam_data.clip_start, cam_data.clip_end = 0.1, 200.0
    cam = obj("CAM", cam_data, c_cam, CAM_LOC, (radians(90), 0, 0))
    hero.camera = cam
    top.camera = cam

    world = bpy.data.worlds.new("WORLD")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.0, 0.0, 0.0, 1)
        bg.inputs[1].default_value = 0.0
    hero.world = world
    top.world = world

    title = build_title(c_title, cam)
    R = build_hero_rig(c_rig)
    L = build_lasers(c_las, col_x)
    T = build_top_rig(c_top)
    animate_hero(R, L, grid, title, books)
    animate_top(T)

    for sc, sat in ((hero, 1.0), (top, 0.12)):
        setup_render(sc, ARGS["engine"], ARGS["quality"])
        setup_compositor(sc, "COMP_" + sc.name, sat)
    add_audio(hero)
    hero.frame_set(1)
    prefs.keyframe_new_interpolation_type = old_interp

    if ARGS["out"]:
        out = os.path.abspath(ARGS["out"])
        os.makedirs(os.path.dirname(out), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=out)
        print("[build_scene] saved", out)
    print("[build_scene] done: %d objects, beats 0..%d, loop %d frames @ %d fps" % (len(bpy.data.objects), N_BEATS, N, FPS))


main()
