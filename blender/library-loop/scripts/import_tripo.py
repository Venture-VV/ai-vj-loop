"""
Swap the proxy sculptures for the Tripo models.

Looks in assets/models/ for   hero_1_demon_rising.glb  hero_2_angel_trumpet.glb  hero_3_michael_dragon.glb
                              hero_4_angel_spear.glb   hero_5_lucifer_falling.glb   (+ optional prop_flying_book.glb)
For every file found: import, join into one mesh, turn it to face the camera, put its base centre on the
slot, scale it to the slot's target height, give it the marble / obsidian material, hide the proxy.
Slots without a file keep their proxy, so you can run this after every single download. Safe to re-run.

    blender -b library_loop.blend -P scripts/import_tripo.py            # headless, saves the file
    (or open library_loop.blend, load this script in the Text Editor, Run Script, then Ctrl+S)

Options (after --)
    --models DIR        default: assets/models next to the .blend
    --yaw DEG           turn every model about Z after import. Default -90: Tripo's GLB is documented as
                        "+X forward" and the camera looks from -Y. If your statues face sideways, try 0 / 90 / 180.
    --yaw-N DEG         the same for one slot only, e.g. --yaw-3 180
    --mirror 1,2        mirror these slots left-right (when the pose points the wrong way)
    --keep-materials    keep Tripo's own material / texture instead of the scene marble
    --decimate 0.5      add a Decimate modifier (ratio) to every imported model — viewport relief
    --no-save
"""
import bpy, bmesh, os, sys
from math import radians
from mathutils import Matrix, Vector
import numpy as np


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    o = dict(models=None, yaw=-90.0, mirror="", decimate=None, keep=False, save=True, yaw_slot={})
    i = 0
    while i < len(a):
        k = a[i].lstrip("-")
        if k == "keep-materials":
            o["keep"] = True; i += 1
        elif k == "no-save":
            o["save"] = False; i += 1
        elif k.startswith("yaw-") and i + 1 < len(a):
            o["yaw_slot"][int(k[4:])] = float(a[i + 1]); i += 2
        elif k in ("models", "yaw", "mirror", "decimate") and i + 1 < len(a):
            o[k] = a[i + 1] if k in ("models", "mirror") else float(a[i + 1]); i += 2
        else:
            i += 1
    return o


def find_file(folder, stem):
    for ext in (".glb", ".gltf", ".fbx", ".obj"):
        p = os.path.join(folder, stem + ext)
        if os.path.exists(p):
            return p
    return None


def import_file(path):
    before = set(bpy.data.objects)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    else:
        bpy.ops.wm.obj_import(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def to_single_mesh(new_objs, name, target_coll):
    """bake world transforms, merge everything into one mesh object in target_coll, delete the rest"""
    meshes = [o for o in new_objs if o.type == "MESH"]
    if not meshes:
        return None
    verts, faces, offset = [], [], 0
    dg = bpy.context.evaluated_depsgraph_get()
    mats = []
    for o in meshes:
        me = o.evaluated_get(dg).to_mesh()
        n = len(me.vertices)
        co = np.empty(n * 3, dtype=np.float32)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        m = np.array(o.matrix_world)
        verts.append(co @ m[:3, :3].T + m[:3, 3])
        for p in me.polygons:
            faces.append([v + offset for v in p.vertices])
        offset += n
        for mt in o.data.materials:
            if mt and mt not in mats:
                mats.append(mt)
        o.evaluated_get(dg).to_mesh_clear()
    out = bpy.data.meshes.new(name)
    out.from_pydata(np.concatenate(verts).tolist(), [], faces)
    out.update()
    out.polygons.foreach_set("use_smooth", [True] * len(out.polygons))
    ob = bpy.data.objects.new(name, out)
    target_coll.objects.link(ob)
    for o in new_objs:
        bpy.data.objects.remove(o, do_unlink=True)
    return ob, mats


def fit(ob, height, yaw_deg, mirror):
    """rotate about Z, mirror, scale to `height`, base centre to the object origin (applied to the mesh)"""
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    c, s = np.cos(radians(yaw_deg)), np.sin(radians(yaw_deg))
    co = co @ np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float32).T
    if mirror:
        co[:, 0] *= -1
    lo, hi = co.min(0), co.max(0)
    scale = height / max(1e-6, (hi[2] - lo[2]))
    # centre on the footprint of the lowest 12 % (the plinth), not on the wing span
    base = co[co[:, 2] < lo[2] + 0.12 * (hi[2] - lo[2])]
    cx, cy = (base[:, 0].min() + base[:, 0].max()) / 2, (base[:, 1].min() + base[:, 1].max()) / 2
    co = (co - np.array([cx, cy, lo[2]], dtype=np.float32)) * scale
    me.vertices.foreach_set("co", co.ravel())
    if mirror:
        bm = bmesh.new()
        try:
            bm.from_mesh(me)
            bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
            bm.to_mesh(me)
        finally:
            bm.free()
    me.update()
    return scale


def main():
    o = args()
    root = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.getcwd()
    folder = os.path.abspath(o["models"]) if o["models"] else os.path.join(root, "assets", "models")
    mirror = {int(x) for x in o["mirror"].split(",") if x.strip()}
    slots_coll = bpy.data.collections.get("SLOTS")
    if slots_coll is None:
        sys.exit("this is not a file made by build_scene.py (no SLOTS collection)")
    tri = bpy.data.collections.get("TRIPO")
    if tri is None:
        tri = bpy.data.collections.new("TRIPO")
        slots_coll.children.link(tri)
    done = []
    for e in sorted((x for x in bpy.data.objects if x.name.startswith("SLOT_")), key=lambda x: x.name):
        n = int(e.name.split("_")[1])
        path = find_file(folder, e["asset"])
        if not path:
            print("[import_tripo] slot %d: no %s.glb in %s — proxy kept" % (n, e["asset"], folder))
            continue
        old = bpy.data.objects.get("TRIPO_%d" % n)
        if old:
            bpy.data.objects.remove(old, do_unlink=True)
        res = to_single_mesh(import_file(path), "TRIPO_%d" % n, tri)
        if not res:
            print("[import_tripo] slot %d: %s contains no mesh" % (n, path))
            continue
        ob, own_mats = res
        fit(ob, float(e["target_height"]), o["yaw_slot"].get(n, o["yaw"]), n in mirror)
        ob.parent = e
        ob.matrix_parent_inverse = Matrix.Identity(4)
        ob.location = (0, 0, 0)
        if o["keep"] and own_mats:
            for m in own_mats:
                ob.data.materials.append(m)
        else:
            mat = bpy.data.materials.get("OBSIDIAN" if e.get("side") == "hell" else "MARBLE")
            if mat:
                ob.data.materials.append(mat)
        if o["decimate"]:
            md = ob.modifiers.new("Decimate", "DECIMATE")
            md.ratio = float(o["decimate"])
        for p in e.children:
            if p.name.startswith("PROXY_"):
                p.hide_render = True
                p.hide_viewport = True
        done.append((n, os.path.basename(path), len(ob.data.polygons)))
    # optional: one Tripo book replaces the floating placeholder books
    fb = find_file(folder, "prop_flying_book")
    if fb:
        res = to_single_mesh(import_file(fb), "TRIPO_FLYBOOK_SRC", tri)
        if res:
            src, own_mats = res
            fit(src, 1.0, 0.0, False)
            co = np.empty(len(src.data.vertices) * 3, dtype=np.float32)
            src.data.vertices.foreach_get("co", co)
            co = co.reshape(-1, 3)
            ext = co.max(0) - co.min(0)
            co *= 0.55 / max(ext[0], ext[1], 1e-6)            # longest horizontal side = 55 cm
            src.data.vertices.foreach_set("co", co.ravel())
            src.data.update()
            src.data.materials.append(bpy.data.materials.get("PAPER"))
            k = 0
            for b in bpy.data.objects:
                if b.name.startswith("FLYBOOK_"):
                    b.data = src.data
                    k += 1
            bpy.data.objects.remove(src, do_unlink=True)
            print("[import_tripo] floating books: %d objects now use %s" % (k, os.path.basename(fb)))
    for n, f, polys in done:
        print("[import_tripo] slot %d  <-  %s  (%d faces)" % (n, f, polys))
    if not done:
        print("[import_tripo] nothing imported")
    if o["save"] and bpy.data.filepath and (done or fb):
        bpy.ops.wm.save_mainfile()
        print("[import_tripo] saved", bpy.data.filepath)


main()
