"""
Render one scene of library_loop.blend to a PNG sequence (resumable: existing frames are skipped,
so you can stop and restart, or run two copies at once to use two GPUs / machines).

    blender -b library_loop.blend -P scripts/render.py -- --scene HERO --out renders/hero
    blender -b library_loop.blend -P scripts/render.py -- --scene TOP  --out renders/top

Options
    --engine EEVEE|CYCLES   override the engine stored in the file
    --samples N             override samples
    --res 1920x744          override resolution (100 %)
    --start 1 --end 300     frame range
    --cpu                   no GPU available (headless server): Cycles on CPU + CPU compositor
    --gpu                   Cycles: enable every GPU device Blender can find (OPTIX / CUDA / METAL / HIP / ONEAPI)
    --blend path            open this file first (only needed when run from the bpy Python module)
"""
import bpy, os, sys


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    o = dict(scene="HERO", out="renders/hero", engine=None, samples=None, res=None, start=None, end=None,
             cpu=False, gpu=False, blend=None)
    i = 0
    while i < len(a):
        k = a[i].lstrip("-")
        if k in ("cpu", "gpu"):
            o[k] = True; i += 1
        elif k in o and i + 1 < len(a):
            o[k] = a[i + 1]; i += 2
        else:
            i += 1
    return o


def enable_gpus():
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
    except Exception:
        return False
    for kind in ("OPTIX", "CUDA", "METAL", "HIP", "ONEAPI"):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
            devs = [d for d in prefs.devices if d.type != "CPU"]
            if devs:
                for d in prefs.devices:
                    d.use = d.type != "CPU"
                print("[render] Cycles on", kind, [d.name for d in devs])
                return True
        except Exception:
            continue
    return False


def main():
    o = args()
    if o["blend"]:
        bpy.ops.wm.open_mainfile(filepath=os.path.abspath(o["blend"]))
    sc = bpy.data.scenes[o["scene"]]
    try:                                   # the scene must be the active one or its animation is not evaluated
        bpy.context.window.scene = sc
    except Exception:
        pass
    r = sc.render
    if o["engine"]:
        if o["engine"].upper() == "CYCLES":
            r.engine = "CYCLES"
        else:
            ids = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
            r.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in ids else "BLENDER_EEVEE"
    if o["res"]:
        w, h = o["res"].lower().split("x")
        r.resolution_x, r.resolution_y, r.resolution_percentage = int(w), int(h), 100
    if o["samples"]:
        if r.engine == "CYCLES":
            sc.cycles.samples = int(o["samples"])
        else:
            sc.eevee.taa_render_samples = int(o["samples"])
    if o["start"]:
        sc.frame_start = int(o["start"])
    if o["end"]:
        sc.frame_end = int(o["end"])
    if o["cpu"]:
        if r.engine == "CYCLES":
            sc.cycles.device = "CPU"
        try:
            r.compositor_device = "CPU"
        except Exception:
            pass
    elif r.engine == "CYCLES" and (o["gpu"] or True):
        if enable_gpus():
            sc.cycles.device = "GPU"
    out = os.path.abspath(o["out"])
    os.makedirs(out, exist_ok=True)
    r.filepath = os.path.join(out, "f_")
    r.image_settings.file_format = "PNG"
    r.use_overwrite = False
    r.use_placeholder = True
    r.use_file_extension = True
    print("[render] %s  %s  %dx%d  frames %d-%d  ->  %s" % (sc.name, r.engine, r.resolution_x * r.resolution_percentage // 100,
                                                            r.resolution_y * r.resolution_percentage // 100,
                                                            sc.frame_start, sc.frame_end, out))
    bpy.ops.render.render(animation=True, scene=sc.name)
    print("[render] done", sc.name)


main()
